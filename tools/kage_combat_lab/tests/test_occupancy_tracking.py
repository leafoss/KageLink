from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from kage_combat_lab.domain import CandidateObservation, GridCell, ObservationKind
from kage_combat_lab.occupancy_tracking import (
    DiffSource,
    OccupancyConfig,
    PR26ControlMode,
    PR26OccupancyTracker,
)
from kage_combat_lab.tile_perception import TileClass, TileEvidence


def _config(tmp_path, *, mode: str = "PERCEPTION_ONLY") -> OccupancyConfig:
    return OccupancyConfig(
        danger_confidence=0.80,
        danger_strong_confidence=0.90,
        weak_ratio=0.04,
        suspect_ratio=0.08,
        strong_ratio=0.12,
        blob_area_min=180,
        blob_area_strong=250,
        blob_width_min=8,
        blob_height_min=14,
        blob_height_strong=18,
        pixel_delta_threshold=18.0,
        baseline_samples=3,
        baseline_stability=0.012,
        danger_memory_seconds=2.5,
        danger_memory_frames=12,
        max_speed_cells_per_second=3.5,
        evidence_votes=2,
        evidence_window=3,
        face_deadzone_px=12.0,
        approach_step_min_px=4.0,
        approach_reductions=3,
        approach_total_px=32.0,
        contact_distance_px=96.0,
        non_aggressive_seconds=3.0,
        overlay_enabled=False,
        evidence_save_seconds=999.0,
        evidence_root=tmp_path / "evidence",
    )


class _Perception:
    def __init__(self, reference: np.ndarray) -> None:
        self.reference = reference

    def reference_crop(self, evidence, *, prefer_non_danger=False):
        return self.reference.copy()


def _evidence(
    cell: GridCell,
    category: TileClass,
    confidence: float,
) -> TileEvidence:
    return TileEvidence(
        cell=cell,
        bbox=(cell.x * 64, cell.y * 64, 64, 64),
        category=category,
        similarity=confidence,
        novelty=1.0 - confidence,
        known_terrain=category is not TileClass.UNKNOWN,
        temporal_activity=0.0,
        activity_bbox=None,
        matched_example_id="floor",
    )


def _state_observer():
    return (
        SimpleNamespace(arena_rect=(0, 0, 256, 128), player_center=(32.0, 96.0)),
        SimpleNamespace(grid_origin=(0.0, 0.0)),
    )


def _raw_candidate(cell: GridCell, *, track_id: int = 7) -> CandidateObservation:
    return CandidateObservation(
        track_id=track_id,
        anchor_cell=cell,
        kind=ObservationKind.CLEAN_BODY,
        visible=True,
        body_like=True,
        confidence=0.9,
        cells_touched=frozenset({cell}),
        bbox=(cell.x * 64 + 8, cell.y * 64 + 4, 48, 56),
        foot_point=(cell.x * 64 + 32.0, cell.y * 64 + 60.0),
    )


def _changed_frame(cell: GridCell) -> np.ndarray:
    frame = np.zeros((128, 256, 3), dtype=np.uint8)
    frame[:] = 30
    x0 = cell.x * 64 + 14
    y0 = cell.y * 64 + 8
    frame[y0 : y0 + 48, x0 : x0 + 32] = (40, 180, 40)
    return frame


def _exact(tracker: PR26OccupancyTracker, baseline: np.ndarray, *cells: GridCell) -> None:
    for cell in cells:
        tracker.map.exact_baselines[cell] = baseline.copy()


def test_bbox_coverage_never_masquerades_as_true_pixel_difference(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "PERCEPTION_ONLY")
    baseline = np.zeros((64, 64, 3), dtype=np.uint8)
    baseline[:] = 30
    tracker = PR26OccupancyTracker(_config(tmp_path))
    tracker.bind_perception(_Perception(baseline))
    state, observer = _state_observer()
    cell = GridCell(1, 0)
    frame = np.zeros((128, 256, 3), dtype=np.uint8)
    frame[:] = 30

    result = tracker.filter_candidates(
        frame_bgr=frame,
        state=state,
        observer=observer,
        candidates=(_raw_candidate(cell),),
        evidence={cell: _evidence(cell, TileClass.WALKABLE, 0.98)},
        now=1.0,
    )

    observed = tracker.last_cells[cell]
    assert result == ()
    assert observed.diff_source is DiffSource.CLASS_REFERENCE
    assert observed.true_changed_ratio == 0.0
    assert observed.bbox_coverage_ratio > 0.50


def test_danger_identity_moves_to_unknown_occupied_cell(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "FACE_ONLY")
    baseline = np.zeros((64, 64, 3), dtype=np.uint8)
    baseline[:] = 30
    tracker = PR26OccupancyTracker(_config(tmp_path))
    tracker.bind_perception(_Perception(baseline))
    state, observer = _state_observer()
    first = GridCell(2, 0)
    second = GridCell(1, 0)
    _exact(tracker, baseline, first, second)

    first_result = tracker.filter_candidates(
        frame_bgr=_changed_frame(first),
        state=state,
        observer=observer,
        candidates=(_raw_candidate(first, track_id=1),),
        evidence={
            first: _evidence(first, TileClass.DANGER, 0.94),
            second: _evidence(second, TileClass.WALKABLE, 0.98),
        },
        now=1.0,
    )
    second_result = tracker.filter_candidates(
        frame_bgr=_changed_frame(second),
        state=state,
        observer=observer,
        candidates=(_raw_candidate(second, track_id=99),),
        evidence={
            first: _evidence(first, TileClass.WALKABLE, 0.98),
            second: _evidence(second, TileClass.UNKNOWN, 0.70),
        },
        now=1.2,
    )

    assert first_result == ()
    assert len(second_result) == 1
    assert tracker.last_snapshot.face_only_lock
    assert tracker.last_snapshot.cell == second
    assert tracker.last_snapshot.danger_score >= 0.80
    assert second_result[0].track_id >= 2_000_000


def test_perception_only_never_exports_cluster_candidate(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "PERCEPTION_ONLY")
    baseline = np.zeros((64, 64, 3), dtype=np.uint8)
    baseline[:] = 30
    tracker = PR26OccupancyTracker(_config(tmp_path))
    tracker.bind_perception(_Perception(baseline))
    state, observer = _state_observer()
    cell = GridCell(2, 0)
    _exact(tracker, baseline, cell)

    for index in range(3):
        result = tracker.filter_candidates(
            frame_bgr=_changed_frame(cell),
            state=state,
            observer=observer,
            candidates=(_raw_candidate(cell),),
            evidence={cell: _evidence(cell, TileClass.DANGER, 0.94)},
            now=1.0 + index * 0.1,
        )
        assert result == ()

    assert tracker.last_snapshot.face_only_lock
    assert tracker.mode is PR26ControlMode.PERCEPTION_ONLY


def test_full_combat_waits_for_pixel_approach_and_contact(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "FULL_COMBAT")
    baseline = np.zeros((64, 64, 3), dtype=np.uint8)
    baseline[:] = 30
    tracker = PR26OccupancyTracker(_config(tmp_path))
    tracker.bind_perception(_Perception(baseline))
    state, observer = _state_observer()
    cells = [
        GridCell(3, 0),
        GridCell(3, 0),
        GridCell(2, 0),
        GridCell(1, 0),
        GridCell(0, 0),
    ]
    _exact(tracker, baseline, *set(cells))
    exported = ()
    for index, cell in enumerate(cells):
        category = TileClass.DANGER if index == 0 else TileClass.UNKNOWN
        confidence = 0.94 if index == 0 else 0.70
        exported = tracker.filter_candidates(
            frame_bgr=_changed_frame(cell),
            state=state,
            observer=observer,
            candidates=(_raw_candidate(cell, track_id=10 + index),),
            evidence={cell: _evidence(cell, category, confidence)},
            now=1.0 + index * 0.4,
        )
        if index < len(cells) - 1:
            assert exported == ()

    assert tracker.last_snapshot.combat_lock
    assert tracker.last_snapshot.hostility_state.value == "HOSTILE_CONFIRMED"
    assert len(exported) == 1
