from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from kage_combat_lab.domain import GridCell, ObservationKind
from kage_combat_lab.occupancy_model import DiffSource
from kage_combat_lab.runtime_acquisition_liveness import (
    camera_static_hold_allowed,
    exact_cell_supports_weak_body,
)
from kage_combat_lab.runtime_pretrainer_coverage import robust_cell_baseline


def _item(mask: np.ndarray):
    ys, xs = np.where(mask > 0)
    left = int(xs.min())
    top = int(ys.min())
    width = int(xs.max() - left + 1)
    height = int(ys.max() - top + 1)
    return SimpleNamespace(
        diff_source=DiffSource.EXACT_CELL_BASELINE,
        true_changed_ratio=float(np.count_nonzero(mask)) / float(mask.size),
        largest_blob_area=int(np.count_nonzero(mask)),
        blob_bbox=(left, top, width, height),
        mask=mask,
        evidence=SimpleNamespace(bbox=(0, 0, 64, 64)),
    )


def _candidate(*, bbox, foot, offset, confidence=0.30, motion=0.50):
    return SimpleNamespace(
        track_id=7,
        visible=True,
        body_like=False,
        bbox=bbox,
        foot_point=foot,
        relative_offset_px=offset,
        confidence=confidence,
        motion_score=motion,
        cells_touched=frozenset({GridCell(0, 0)}),
        anchor_cell=GridCell(0, 0),
        kind=ObservationKind.CONTAMINATED_ACTIVITY,
    )


def test_physical_low_response_static_camera_remains_authoritative() -> None:
    assert camera_static_hold_allowed((0.0, 0.0), (0.0, 0.0), 0.144)
    assert camera_static_hold_allowed((3.0, -1.0), (4.0, -1.0), 0.084)


def test_low_response_large_camera_jump_is_still_rejected() -> None:
    assert not camera_static_hold_allowed((0.0, 0.0), (-11.0, 29.0), 0.100)
    assert not camera_static_hold_allowed((0.0, 0.0), (0.0, 0.0), 0.010)


def test_robust_baseline_uses_median_instead_of_resetting_on_one_animation() -> None:
    floor = np.full((64, 64, 3), 120, dtype=np.uint8)
    samples = [floor.copy() for _ in range(8)]
    samples.append(np.full((64, 64, 3), 240, dtype=np.uint8))
    baseline, deviation = robust_cell_baseline(samples)
    assert int(np.median(baseline)) == 120
    assert deviation == 0.0


def test_exact_changed_pixels_can_promote_fresh_weak_raw_body() -> None:
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[12:54, 29:47] = 255
    item = _item(mask)
    candidate = _candidate(
        bbox=(28, 10, 20, 46),
        foot=(38.0, 54.0),
        offset=(27.0, 1.0),
    )
    assert exact_cell_supports_weak_body(candidate, item)


def test_same_cell_without_pixel_overlap_is_not_identity() -> None:
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[10:50, 38:52] = 255
    item = _item(mask)
    candidate = _candidate(
        bbox=(2, 8, 12, 28),
        foot=(8.0, 36.0),
        offset=(30.0, 0.0),
    )
    assert not exact_cell_supports_weak_body(candidate, item)


def test_player_center_track_cannot_be_promoted_as_enemy() -> None:
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[12:54, 29:47] = 255
    item = _item(mask)
    candidate = _candidate(
        bbox=(28, 10, 20, 46),
        foot=(38.0, 54.0),
        offset=(4.0, 3.0),
    )
    assert not exact_cell_supports_weak_body(candidate, item)
