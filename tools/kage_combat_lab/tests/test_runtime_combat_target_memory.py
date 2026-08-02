from __future__ import annotations

from types import SimpleNamespace

from kage_combat_lab.domain import (
    CandidateObservation,
    GridCell,
    ObservationKind,
)
from kage_combat_lab.occupancy_model import DiffSource
from kage_combat_lab.runtime_combat_target_memory import (
    capsule_reid_matches,
    cluster_reid_matches,
    contact_player_rect,
    progressive_reid_radius,
)


def test_progressive_reid_never_exceeds_d3() -> None:
    assert progressive_reid_radius(0.0) == 1
    assert progressive_reid_radius(2.5) == 1
    assert progressive_reid_radius(2.6) == 2
    assert progressive_reid_radius(7.0) == 2
    assert progressive_reid_radius(7.1) == 3
    assert progressive_reid_radius(900.0) == 3


def test_contact_player_mask_is_small_22x42_core() -> None:
    state = SimpleNamespace(player_center=(448.0, 208.0))
    assert contact_player_rect(state) == (437, 187, 22, 42)


def _capsule_candidate(cell: GridCell, *, appearance: float = 0.72):
    return CandidateObservation(
        track_id=17,
        anchor_cell=cell,
        kind=ObservationKind.REIDENTIFIED_BODY,
        visible=True,
        body_like=True,
        confidence=0.88,
        bbox=(580, 188, 19, 32),
        foot_point=(590.0, 220.0),
        identity_score=0.84,
        appearance_score=appearance,
        position_score=0.80,
        shape_similarity=0.70,
        motion_score=0.62,
        background_probability=0.08,
        reidentified=True,
    )


def test_target_capsule_can_rebind_latched_enemy_inside_d3() -> None:
    candidate = _capsule_candidate(GridCell(9, 2))
    assert capsule_reid_matches(
        candidate,
        player_cell=GridCell(6, 2),
        predicted_foot=(570.0, 220.0),
        radius_cells=3,
    )


def test_target_capsule_never_reacquires_outside_d3() -> None:
    candidate = _capsule_candidate(GridCell(10, 2))
    assert not capsule_reid_matches(
        candidate,
        player_cell=GridCell(6, 2),
        predicted_foot=(590.0, 220.0),
        radius_cells=3,
    )


def test_target_capsule_requires_real_appearance_evidence() -> None:
    candidate = _capsule_candidate(GridCell(9, 2), appearance=0.30)
    assert not capsule_reid_matches(
        candidate,
        player_cell=GridCell(6, 2),
        predicted_foot=(590.0, 220.0),
        radius_cells=3,
    )


def _cluster(*, cell: GridCell, bbox, occupancy=0.54, ratio=0.096, area=120):
    return SimpleNamespace(
        local_id=1,
        cells=frozenset({cell}),
        bbox=bbox,
        foot_point=(float(bbox[0] + bbox[2] / 2.0), float(bbox[1] + bbox[3])),
        foot_cell=cell,
        occupancy_score=occupancy,
        true_changed_ratio=ratio,
        largest_blob_area=area,
        raw_track_ids=frozenset(),
        cell_observations=(
            SimpleNamespace(diff_source=DiffSource.EXACT_CELL_BASELINE),
        ),
    )


def test_log_fragment_19x32_can_reidentify_only_latched_target() -> None:
    cluster = _cluster(
        cell=GridCell(9, 2),
        bbox=(604, 189, 19, 32),
    )
    assert cluster_reid_matches(
        cluster,
        player_cell=GridCell(6, 2),
        predicted_foot=(590.0, 221.0),
        previous_bbox=(444, 41, 28, 78),
        radius_cells=3,
    )


def test_wide_field_cannot_reidentify_latched_target() -> None:
    cluster = _cluster(
        cell=GridCell(7, 1),
        bbox=(410, 42, 128, 64),
        occupancy=0.79,
        ratio=0.33,
        area=2500,
    )
    assert not cluster_reid_matches(
        cluster,
        player_cell=GridCell(6, 2),
        predicted_foot=(458.0, 119.0),
        previous_bbox=(444, 41, 28, 78),
        radius_cells=1,
    )
