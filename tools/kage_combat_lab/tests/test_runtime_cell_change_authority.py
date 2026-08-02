from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from kage_combat_lab.domain import (
    CandidateObservation,
    GridCell,
    ObservationKind,
)
from kage_combat_lab.occupancy_model import DiffSource, OccupancyState
from kage_combat_lab.pre_ok_baseline import inpaint_player_core_from_cell
from kage_combat_lab.runtime_cell_change_authority import (
    build_cell_change_components,
    candidate_matches_cell_change,
    player_capsule_mask,
)


def _cell(
    cell: GridCell,
    *,
    bbox: tuple[int, int, int, int],
    blob_bbox: tuple[int, int, int, int],
    state: OccupancyState = OccupancyState.OCCUPIED,
    ratio: float = 0.16,
    area: int = 300,
    width: int = 18,
    height: int = 32,
):
    mask = np.zeros((64, 64), dtype=np.uint8)
    left, top, component_width, component_height = blob_bbox
    mask[top : top + component_height, left : left + component_width] = 255
    return SimpleNamespace(
        cell=cell,
        evidence=SimpleNamespace(bbox=bbox),
        state=state,
        diff_source=DiffSource.EXACT_CELL_BASELINE,
        true_changed_ratio=ratio,
        bbox_coverage_ratio=0.0,
        largest_blob_area=area,
        blob_width=width,
        blob_height=height,
        occupancy_score=0.72,
        danger_prior=0.0,
        persistence=2,
        crop=None,
        baseline=None,
        diff=None,
        mask=mask,
        blob_bbox=blob_bbox,
        player_masked_pixels=0,
        reference_authoritative=True,
    )


def _candidate(
    track_id: int,
    *,
    cell: GridCell,
    bbox: tuple[int, int, int, int],
    foot: tuple[float, float],
):
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
        identity_score=0.84,
        appearance_score=0.78,
        position_score=0.82,
        shape_similarity=0.76,
        motion_score=0.70,
        background_probability=0.05,
    )


def test_adjacent_cells_remain_independent_authority_components() -> None:
    left = _cell(
        GridCell(5, 2),
        bbox=(320, 128, 64, 64),
        blob_bbox=(46, 18, 18, 32),
    )
    right = _cell(
        GridCell(6, 2),
        bbox=(384, 128, 64, 64),
        blob_bbox=(0, 16, 16, 34),
    )

    components = build_cell_change_components(
        {left.cell: left, right.cell: right},
        (),
    )

    assert len(components) == 2
    assert all(len(component.cells) == 1 for component in components)
    assert components[0].bbox == (366, 146, 18, 32)
    assert components[1].bbox == (384, 144, 16, 34)


def test_raw_body_binds_only_to_overlapping_changed_cell() -> None:
    first = _cell(
        GridCell(5, 2),
        bbox=(320, 128, 64, 64),
        blob_bbox=(8, 14, 20, 36),
    )
    second = _cell(
        GridCell(6, 2),
        bbox=(384, 128, 64, 64),
        blob_bbox=(36, 14, 20, 36),
    )
    body = _candidate(
        41,
        cell=GridCell(5, 2),
        bbox=(326, 140, 24, 42),
        foot=(338.0, 182.0),
    )

    assert candidate_matches_cell_change(body, first)
    assert not candidate_matches_cell_change(body, second)

    components = build_cell_change_components(
        {first.cell: first, second.cell: second},
        (body,),
    )
    assert components[0].raw_track_ids == frozenset({41})
    assert components[1].raw_track_ids == frozenset()


def test_fragmented_weak_cell_is_recovered_only_with_same_cell_body() -> None:
    item = _cell(
        GridCell(6, 2),
        bbox=(384, 128, 64, 64),
        blob_bbox=(2, 18, 10, 20),
        state=OccupancyState.WEAK,
        ratio=0.03,
        area=74,
        width=10,
        height=20,
    )
    body = _candidate(
        7,
        cell=GridCell(6, 2),
        bbox=(383, 142, 18, 38),
        foot=(392.0, 180.0),
    )

    assert build_cell_change_components({item.cell: item}, ()) == ()
    components = build_cell_change_components(
        {item.cell: item},
        (body,),
        weak_ratio=0.04,
        blob_area_min=180,
    )
    assert len(components) == 1
    assert components[0].cells == frozenset({GridCell(6, 2)})
    assert components[0].raw_track_ids == frozenset({7})


def test_player_capsule_does_not_erase_full_overlap_rectangle() -> None:
    mask = player_capsule_mask(
        (64, 64),
        cell_left=384,
        cell_top=128,
        player_rect=(420, 140, 38, 58),
    )

    assert mask[41, 55] == 255  # compact player center
    assert mask[41, 37] == 0  # left-side enemy pixels survive
    assert mask[15, 55] == 0  # enemy pixels arriving from above survive
    assert np.count_nonzero(mask) < 700


def test_pretrainer_baseline_inpaints_only_player_core() -> None:
    crop = np.zeros((64, 64, 3), dtype=np.uint8)
    crop[:, :] = (30, 50, 70)
    crop[20:54, 26:42] = (220, 220, 220)

    cleaned, changed = inpaint_player_core_from_cell(
        crop,
        cell_bbox=(384, 128, 64, 64),
        player_rect=(410, 148, 22, 42),
    )

    assert changed
    assert np.array_equal(cleaned[0, 0], crop[0, 0])
    assert not np.array_equal(cleaned[40, 36], crop[40, 36])
