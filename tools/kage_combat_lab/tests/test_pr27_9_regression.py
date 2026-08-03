from __future__ import annotations

import cv2
import numpy as np

from kage_combat_lab.pr27_9_analyze import analyze_rows
from kage_combat_lab.pr27_camera_motion import CameraMotionEstimator
from kage_combat_lab.pr27_fixed_grid import DEFAULT_FIXED_GRID, NativeRect
from kage_combat_lab.pr27_fixed_self import FixedSelfDetector, SelfVisualState


def test_stationary_perception_rejects_32_pixel_shift() -> None:
    rng = np.random.default_rng(7)
    base = rng.integers(0, 255, size=(360, 640, 3), dtype=np.uint8)
    shifted = cv2.warpAffine(base, np.float32([[1, 0, 32], [0, 1, 0]]), (640, 360), borderMode=cv2.BORDER_REFLECT)
    estimator = CameraMotionEstimator(downsample=1.0, minimum_confidence=0.10)
    estimator.observe(base, stationary_mode=True)
    result = estimator.observe(shifted, stationary_mode=True)
    assert not result.shift_accepted
    assert (result.dx_px, result.dy_px) == (0.0, 0.0)
    assert result.shift_rejection_reason == "CAMERA_SHIFT_REJECTED_STATIONARY_MODE"


def test_stationary_camera_accepts_subpixel_or_one_pixel_jitter() -> None:
    rng = np.random.default_rng(8)
    base = rng.integers(0, 255, size=(360, 640, 3), dtype=np.uint8)
    shifted = cv2.warpAffine(base, np.float32([[1, 0, 1], [0, 1, 0]]), (640, 360), borderMode=cv2.BORDER_REFLECT)
    estimator = CameraMotionEstimator(downsample=1.0, minimum_confidence=0.10)
    estimator.observe(base, stationary_mode=True)
    result = estimator.observe(shifted, stationary_mode=True)
    assert result.shift_accepted
    assert abs(result.dx_px) <= 2.0


def test_self_score_0324_is_preserved_not_lost() -> None:
    detector = FixedSelfDetector(DEFAULT_FIXED_GRID)
    detector.last_bbox = NativeRect(982, 391, 1005, 456)
    detector.last_anchor = (993.5, 455.0)
    detector.last_confirmed_frame = 127
    detector.last_template_id = 1
    detector.missing_frames = 1
    observation = detector._preserved_observation(
        score=0.324,
        state=SelfVisualState.SELF_PRESERVED_LOW_SCORE,
        reason="regression frame 128",
    )
    assert observation.found
    assert observation.state is SelfVisualState.SELF_PRESERVED_LOW_SCORE
    assert observation.template_score == 0.324
    assert not observation.template_update_allowed


def test_analyzer_flags_frame_84_128_132_and_144() -> None:
    rows = []
    for frame in (84, 128, 132, 144):
        candidates = []
        if frame == 144:
            candidates = [
                {
                    "candidate_id": index,
                    "class": "UNKNOWN_VISUAL_CHANGE",
                    "rejection_reason": "BODY_CORE_TOO_FEW_PIXELS",
                }
                for index in range(26)
            ]
        score = 0.324 if frame in {128, 132} else 0.70
        rows.append(
            {
                "frame_index": frame,
                "self_body_found": True,
                "self_state": "SELF_PRESERVED_LOW_SCORE" if frame in {128, 132} else "SELF_TRACKED",
                "self_template_score": score,
                "self": {"matched_template_id": 1},
                "camera": {
                    "phase_dx": 32.7 if frame == 84 else 0.0,
                    "phase_dy": 0.0,
                    "accepted_dx": 0.0,
                    "accepted_dy": 0.0,
                    "accepted": frame != 84,
                    "rejection_reason": "CAMERA_SHIFT_REJECTED_STATIONARY_MODE" if frame == 84 else None,
                },
                "trainer": {"entity_detection_mask_pixels": 0},
                "entity_candidates": candidates,
                "object_tracks": [],
                "cell_activity": [],
                "raw_active_pixels": 100,
                "noise_gated_active_pixels": 20,
            }
        )
    summary, _tables, flags = analyze_rows(rows)
    text = "\n".join(flags)
    assert "frame 000084" in text and "outlier" in text
    assert "frame 000128" in text and "preserved near threshold" in text
    assert "frame 000132" in text
    assert "frame 000144" in text and "burst" in text
    assert summary["trainer_blind_mask_violations"] == 0
