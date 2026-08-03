from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from kage_combat_lab.pr27_camera_motion import CameraMotionEstimator, CameraMotionResult
from kage_combat_lab.pr27_entity_validation import (
    CandidateClass,
    EntityCandidate,
    EntityValidator,
)
from kage_combat_lab.pr27_fixed_grid import (
    DEFAULT_FIXED_GRID,
    FixedNativeGridCalibration,
    NativeRect,
    PR278CalibrationMismatch,
)
from kage_combat_lab.pr27_fixed_perception import (
    FixedPerceptionSystem,
    SelfVisualObservation,
    SelfVisualState,
)
from kage_combat_lab.pr27_hostility import HostilityEvaluator, HostilityState
from kage_combat_lab.pr27_replay import _audit_frame_24_roi
from kage_combat_lab.pr27_trainer_mask import TrainerMaskTracker, output_bbox_to_native


def native_frame(background: tuple[int, int, int] = (90, 115, 90)) -> np.ndarray:
    frame = np.empty((1037, 1920, 3), dtype=np.uint8)
    frame[:] = background
    return frame


def draw_self(frame: np.ndarray) -> None:
    # Body extends slightly above the fixed cell, while the feet anchor remains
    # inside [960,405,1024,469), matching the game's sprite layering.
    cv2.rectangle(frame, (982, 391), (1004, 449), (30, 30, 220), -1)
    cv2.rectangle(frame, (976, 407), (1010, 440), (220, 220, 220), 2)
    cv2.rectangle(frame, (985, 445), (992, 455), (20, 20, 20), -1)
    cv2.rectangle(frame, (996, 445), (1003, 455), (20, 20, 20), -1)


def humanoid_candidate(candidate_id: int, feet: tuple[float, float]) -> EntityCandidate:
    left = int(feet[0] - 10)
    bottom = int(feet[1] + 1)
    bbox = NativeRect(left, bottom - 42, left + 20, bottom)
    descriptor = np.zeros(32, dtype=np.float32)
    descriptor[3] = 1.0
    cell = DEFAULT_FIXED_GRID.cell_for_native_point(*feet)
    return EntityCandidate(
        candidate_id=candidate_id,
        bbox=bbox,
        feet_anchor=feet,
        relative_cell=None if cell is None else cell.relative_key,
        area=840,
        component_pixels=380,
        occupancy=0.45,
        aspect_ratio=20 / 42,
        solidity=0.75,
        vertical_score=0.75,
        feet_support_score=0.45,
        rigidity_score=0.85,
        entity_confidence=0.80,
        humanoid_confidence=0.82,
        candidate_class=CandidateClass.HUMANOID_CANDIDATE,
        descriptor=descriptor,
    )


def test_fixed_grid_uses_exact_native_calibration() -> None:
    grid = DEFAULT_FIXED_GRID
    assert (grid.native_width, grid.native_height) == (1920, 1037)
    assert grid.cell_size == 64
    assert (grid.offset_x, grid.offset_y) == (0, 21)
    assert (grid.self_row, grid.self_column) == (6, 15)
    assert grid.self_cell_rect() == NativeRect(960, 405, 1024, 469)
    assert len(grid.roi_cells()) == 49


def test_fixed_grid_never_recenters_on_body_or_enemy() -> None:
    grid = FixedNativeGridCalibration()
    before = grid.self_cell_rect()
    assert not hasattr(grid, "update_center")
    assert not hasattr(grid, "calibrate_to_body")
    assert before == grid.self_cell_rect()
    assert grid.relative_cell(6, 15) == (0, 0)
    assert grid.relative_cell(5, 17) == (-1, 2)


def test_native_to_arena_conversion_does_not_rephase() -> None:
    arena = NativeRect(77, 41, 1843, 892)
    local = DEFAULT_FIXED_GRID.native_to_arena(DEFAULT_FIXED_GRID.self_cell_rect(), arena)
    assert local == NativeRect(883, 364, 947, 428)
    assert DEFAULT_FIXED_GRID.arena_to_native(local, arena) == DEFAULT_FIXED_GRID.self_cell_rect()


def test_resolution_mismatch_aborts() -> None:
    with pytest.raises(PR278CalibrationMismatch, match="PR27_CALIBRATION_MISMATCH"):
        DEFAULT_FIXED_GRID.validate_native_shape((997, 1920, 3))


def test_self_search_is_restricted_to_fixed_cell_margin() -> None:
    frame = native_frame()
    draw_self(frame)
    system = FixedPerceptionSystem()
    observed = system.self_detector.observe(frame)
    assert observed.found
    assert observed.state is SelfVisualState.SELF_TRACKED
    assert observed.feet_anchor is not None
    assert DEFAULT_FIXED_GRID.self_cell_rect().contains(observed.feet_anchor)
    assert observed.anchor_inside_fixed_cell


def test_missing_self_blocks_every_planned_action() -> None:
    system = FixedPerceptionSystem()
    missing = SelfVisualObservation(
        found=False,
        bbox=None,
        feet_anchor=None,
        anchor_inside_fixed_cell=False,
        template_score=0.0,
        confidence=0.0,
        state=SelfVisualState.SELF_LOST_CRITICAL,
        reason="test",
    )
    action, reason = system._plan(missing, (), CameraMotionResult(compensated=True))
    assert action == "NONE"
    assert reason == "SELF_NOT_CONFIRMED"


def test_camera_translation_is_estimated_and_compensated() -> None:
    rng = np.random.default_rng(42)
    base = rng.integers(0, 255, size=(300, 500, 3), dtype=np.uint8)
    matrix = np.float32([[1, 0, 16], [0, 1, -8]])
    shifted = cv2.warpAffine(base, matrix, (500, 300), borderMode=cv2.BORDER_REFLECT)
    estimator = CameraMotionEstimator(downsample=1.0, minimum_confidence=0.10)
    estimator.observe(base)
    result = estimator.observe(shifted)
    assert result.compensated
    assert result.dx_px == pytest.approx(16, abs=2.0)
    assert result.dy_px == pytest.approx(-8, abs=2.0)


def test_wide_water_patch_cannot_be_humanoid_or_enemy() -> None:
    frame = native_frame()
    residual = np.zeros(frame.shape[:2], dtype=np.uint8)
    # Wide animated-water-like region: deliberately fails BODY_CORE width.
    cv2.rectangle(residual, (700, 250), (770, 300), 255, -1)
    validator = EntityValidator(DEFAULT_FIXED_GRID)
    candidates = validator.detect(frame, residual)
    assert candidates
    candidate = max(candidates, key=lambda item: item.component_pixels)
    assert candidate.candidate_class is CandidateClass.UNKNOWN_VISUAL_CHANGE
    assert candidate.rejection_reason in {"BODY_CORE_WIDTH_OUT_OF_RANGE", "BODY_CORE_TOO_MANY_PIXELS"}
    evaluator = HostilityEvaluator(opponent_confirm_frames=2)
    for index in range(8):
        tracks = evaluator.update(candidates, frame_index=index, self_anchor=(992.0, 455.0))
    assert not tracks
    assert not evaluator.hostile_tracks()


def test_movement_and_persistence_alone_do_not_confirm_hostility() -> None:
    evaluator = HostilityEvaluator(opponent_confirm_frames=3, approach_confirm_frames=3)
    self_anchor = (992.0, 455.0)
    for frame_index in range(6):
        # Moves sideways at constant distance; this is an entity, not evidence
        # that it is hostile.
        candidate = humanoid_candidate(frame_index + 1, (1120.0, 400.0 + frame_index * 2.0))
        tracks = evaluator.update(
            (candidate,),
            frame_index=frame_index,
            self_anchor=self_anchor,
            player_stationary=True,
        )
    assert tracks
    assert all(track.hostility_state is not HostilityState.HOSTILE_CONFIRMED for track in tracks)
    assert any("NO_EXPLICIT_HOSTILITY_EVIDENCE" in track.hostility_evidence for track in tracks)


def test_consistent_approach_can_confirm_hostility() -> None:
    evaluator = HostilityEvaluator(opponent_confirm_frames=2, approach_confirm_frames=3)
    self_anchor = (992.0, 455.0)
    tracks = ()
    for frame_index, x in enumerate((1160.0, 1140.0, 1120.0, 1100.0, 1080.0, 1060.0)):
        candidate = humanoid_candidate(frame_index + 1, (x, 455.0))
        tracks = evaluator.update(
            (candidate,),
            frame_index=frame_index,
            self_anchor=self_anchor,
            player_stationary=True,
        )
    assert any(track.hostility_state is HostilityState.HOSTILE_CONFIRMED for track in tracks)
    assert any("CONSISTENT_APPROACH_TO_FIXED_SELF" in track.hostility_evidence for track in tracks)


def test_trainer_mask_does_not_modify_rgb_frame() -> None:
    frame = native_frame()
    cv2.rectangle(frame, (1082, 272), (1157, 341), (80, 20, 180), -1)
    original = frame.copy()
    tracker = TrainerMaskTracker(NativeRect(1082, 272, 1158, 342))
    evidence = tracker.update(frame)
    mask = tracker.mask(frame.shape[:2], evidence)
    assert np.array_equal(frame, original)
    assert np.count_nonzero(mask) > 0
    assert evidence.mask_only
    assert not evidence.rgb_replaced


def test_output_bbox_to_native_matches_1037_letterbox_mapping() -> None:
    rect = output_bbox_to_native((541, 147, 38, 35))
    assert rect == NativeRect(1082, 272, 1158, 342)


def test_process_result_preserves_original_rgb() -> None:
    frame = native_frame()
    draw_self(frame)
    before = frame.copy()
    result = FixedPerceptionSystem().process_native(
        frame,
        trainer_bbox=NativeRect(1082, 272, 1158, 342),
    )
    assert np.array_equal(result.original_bgr, before)
    assert not result.trainer_rgb_replaced
    assert result.trainer_mask_only
    assert result.fixed_self_bbox == NativeRect(960, 405, 1024, 469)


def test_frame_24_roi_audit_rejects_legacy_water_lock(tmp_path: Path) -> None:
    image = np.zeros((560, 560, 3), dtype=np.uint8)
    # Recreate the old red lock around a wide patch.
    cv2.rectangle(image, (183, 96), (247, 158), (0, 0, 255), 2)
    path = tmp_path / "frame_000024_LOCAL_VISUAL_OCCLUSION_ROI.png"
    assert cv2.imwrite(str(path), image)
    audit = _audit_frame_24_roi([path])
    assert audit["available"]
    assert audit["passes_pr278_body_core"] is False
    assert "NON_HUMANOID" in str(audit["classification"])
