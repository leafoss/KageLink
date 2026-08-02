from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from kage_combat_lab.domain import CandidateObservation, GridCell, ObservationKind
from kage_combat_lab.runtime_visual_target_authority import (
    dominant_cluster_geometry,
    dominant_terrain_component,
    latched_cluster_has_current_body,
    strict_candidate_matches_cell_change,
)


def _item(
    *,
    cell: GridCell = GridCell(4, 1),
    component_bbox=(8, 10, 20, 42),
    ratio=0.18,
    blob=620,
):
    mask = np.zeros((64, 64), dtype=np.uint8)
    left, top, width, height = component_bbox
    mask[top : top + height, left : left + width] = 255
    return SimpleNamespace(
        cell=cell,
        evidence=SimpleNamespace(
            bbox=(cell.x * 64, cell.y * 64, 64, 64),
        ),
        blob_bbox=component_bbox,
        mask=mask,
        true_changed_ratio=ratio,
        largest_blob_area=blob,
    )


def _candidate(*, bbox, foot, cell=GridCell(4, 1), track_id=7):
    return CandidateObservation(
        track_id=track_id,
        anchor_cell=cell,
        kind=ObservationKind.CLEAN_BODY,
        visible=True,
        body_like=True,
        confidence=0.90,
        cells_touched=frozenset({cell}),
        bbox=bbox,
        foot_point=foot,
    )


def test_same_cell_without_component_overlap_does_not_bind_identity() -> None:
    item = _item(component_bbox=(8, 10, 18, 42))
    candidate = _candidate(
        bbox=(4 * 64 + 42, 1 * 64 + 8, 18, 44),
        foot=(4 * 64 + 51.0, 1 * 64 + 52.0),
    )
    assert candidate.anchor_cell == item.cell
    assert not strict_candidate_matches_cell_change(candidate, item)


def test_body_overlapping_changed_pixels_binds_identity() -> None:
    item = _item(component_bbox=(8, 10, 20, 42))
    candidate = _candidate(
        bbox=(4 * 64 + 9, 1 * 64 + 11, 18, 40),
        foot=(4 * 64 + 18.0, 1 * 64 + 51.0),
    )
    assert strict_candidate_matches_cell_change(candidate, item)


def test_physical_43x64_high_ratio_field_is_terrain() -> None:
    item = _item(
        component_bbox=(0, 0, 43, 64),
        ratio=0.6599,
        blob=2703,
    )
    assert dominant_terrain_component(item)


def test_physical_64x23_horizontal_field_is_terrain() -> None:
    item = _item(
        component_bbox=(0, 18, 64, 23),
        ratio=0.6599,
        blob=1472,
    )
    assert dominant_terrain_component(item)


def test_latched_visual_requires_current_raw_body() -> None:
    rawless = SimpleNamespace(
        bbox=(256, 64, 43, 64),
        true_changed_ratio=0.6599,
        largest_blob_area=2703,
        raw_track_ids=frozenset(),
    )
    body = SimpleNamespace(
        bbox=(456, 128, 24, 44),
        true_changed_ratio=0.14,
        largest_blob_area=560,
        raw_track_ids=frozenset({17}),
    )
    assert dominant_cluster_geometry(rawless)
    assert not latched_cluster_has_current_body(rawless)
    assert latched_cluster_has_current_body(body)
