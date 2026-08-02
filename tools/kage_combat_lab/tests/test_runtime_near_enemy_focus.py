from __future__ import annotations

from types import SimpleNamespace

from kage_combat_lab.domain import GridCell
from kage_combat_lab.occupancy_model import DiffSource
from kage_combat_lab.runtime_near_enemy_focus import (
    cluster_distance_cells,
    near_vertical_body_evidence,
    within_player_search_radius,
)


def _cluster(
    *,
    cells,
    bbox,
    ratio,
    occupancy,
    area,
):
    return SimpleNamespace(
        local_id=1,
        cells=frozenset(cells),
        bbox=bbox,
        foot_point=(bbox[0] + bbox[2] / 2.0, bbox[1] + bbox[3]),
        foot_cell=next(iter(cells)),
        occupancy_score=occupancy,
        true_changed_ratio=ratio,
        largest_blob_area=area,
        raw_track_ids=frozenset(),
        cell_observations=(
            SimpleNamespace(
                diff_source=DiffSource.EXACT_CELL_BASELINE,
                reference_authoritative=True,
            ),
        ),
    )


def test_cluster_distance_uses_nearest_cluster_cell() -> None:
    player = GridCell(6, 2)
    cluster = _cluster(
        cells={GridCell(0, 0), GridCell(5, 1)},
        bbox=(0, 0, 128, 64),
        ratio=0.20,
        occupancy=0.70,
        area=500,
    )
    assert cluster_distance_cells(cluster, player) == 1


def test_initial_enemy_search_is_limited_to_three_cells() -> None:
    player = GridCell(6, 2)
    assert within_player_search_radius({GridCell(3, 5)}, player)
    assert not within_player_search_radius({GridCell(2, 6)}, player)


def test_physical_log_25x44_near_body_is_confirmable_without_raw_id() -> None:
    player = GridCell(6, 2)
    cluster = _cluster(
        cells={GridCell(6, 1)},
        bbox=(459, 105, 25, 44),
        ratio=0.139,
        occupancy=0.68,
        area=569,
    )
    assert near_vertical_body_evidence(cluster, player)


def test_physical_log_128x64_field_is_not_a_near_vertical_body() -> None:
    player = GridCell(6, 2)
    cluster = _cluster(
        cells={GridCell(6, 0), GridCell(7, 0)},
        bbox=(410, 42, 128, 64),
        ratio=0.498,
        occupancy=0.76,
        area=2040,
    )
    assert within_player_search_radius(cluster, player)
    assert not near_vertical_body_evidence(cluster, player)


def test_vertical_body_outside_d3_has_no_acquisition_authority() -> None:
    player = GridCell(6, 2)
    cluster = _cluster(
        cells={GridCell(10, 6)},
        bbox=(640, 384, 25, 44),
        ratio=0.139,
        occupancy=0.68,
        area=569,
    )
    assert not near_vertical_body_evidence(cluster, player)
