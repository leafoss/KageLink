from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from kage_combat_lab.domain import GridCell
from kage_combat_lab.occupancy_model import DiffSource, OccupancyConfig, OccupancyState
from kage_combat_lab.pixel_occupancy import PixelOccupancyMap
from kage_combat_lab.tile_perception import TileClass, TileEvidence


class _Perception:
    def __init__(self, reference: np.ndarray) -> None:
        self.reference = reference

    def reference_crop(self, evidence, *, prefer_non_danger=False):
        return self.reference.copy()


def _evidence(cell: GridCell, category=TileClass.WALKABLE, similarity=0.98):
    return TileEvidence(
        cell=cell,
        bbox=(cell.x * 64, cell.y * 64, 64, 64),
        category=category,
        similarity=similarity,
        novelty=1.0 - similarity,
        known_terrain=category is not TileClass.UNKNOWN,
        temporal_activity=0.0,
        activity_bbox=None,
        matched_example_id="floor",
    )


def _setup(columns: int, rows: int = 1):
    baseline = np.full((64, 64, 3), 30, dtype=np.uint8)
    frame = np.full((rows * 64, columns * 64, 3), 30, dtype=np.uint8)
    occupancy = PixelOccupancyMap(OccupancyConfig(baseline_samples=3))
    occupancy.bind_perception(_Perception(baseline))
    evidence = {
        GridCell(x, y): _evidence(GridCell(x, y))
        for y in range(rows)
        for x in range(columns)
    }
    for cell in evidence:
        occupancy.exact_baselines[cell] = baseline.copy()
    state = SimpleNamespace(
        arena_rect=(0, 0, columns * 64, rows * 64),
        player_center=(-500.0, -500.0),
    )
    return occupancy, frame, evidence, state


def _observe(occupancy, frame, evidence, state, *, player_rect=None):
    cells, _ = occupancy.observe(
        frame=frame,
        state=state,
        candidates=(),
        evidence=evidence,
        danger_fresh=True,
        player_rect=player_rect,
    )
    return cells, occupancy.clusters(cells, ())


def test_adjacent_cells_without_mask_contact_stay_separate() -> None:
    occupancy, frame, evidence, state = _setup(2)
    frame[18:48, 8:30] = (40, 180, 40)
    frame[18:48, 64 + 34 : 64 + 58] = (40, 180, 40)

    _, clusters = _observe(occupancy, frame, evidence, state)

    assert len(clusters) == 2
    assert all(len(cluster.cells) == 1 for cluster in clusters)


def test_shared_edge_mask_contact_forms_one_two_cell_cluster() -> None:
    occupancy, frame, evidence, state = _setup(2)
    frame[18:48, 38:64] = (40, 180, 40)
    frame[18:48, 64:90] = (40, 180, 40)

    _, clusters = _observe(occupancy, frame, evidence, state)

    assert len(clusters) == 1
    assert len(clusters[0].cells) == 2
    assert clusters[0].mask_contact_edges >= 1
    assert clusters[0].bbox[2] < 2 * 64


def test_diagonal_cells_never_merge_without_cardinal_contact() -> None:
    occupancy, frame, evidence, state = _setup(2, 2)
    frame[38:64, 38:64] = (40, 180, 40)
    frame[64:90, 64:90] = (40, 180, 40)

    _, clusters = _observe(occupancy, frame, evidence, state)

    assert len(clusters) == 2


def test_player_pixels_are_removed_before_component_and_cluster_creation() -> None:
    occupancy, frame, evidence, state = _setup(1)
    frame[8:56, 16:48] = (40, 180, 40)

    cells, clusters = _observe(
        occupancy,
        frame,
        evidence,
        state,
        player_rect=(10, 4, 44, 56),
    )

    item = cells[GridCell(0, 0)]
    assert item.player_masked_pixels > 0
    assert item.largest_blob_area == 0
    assert item.state is OccupancyState.EMPTY
    assert clusters == ()


def test_class_reference_is_weak_attention_and_never_a_cluster_seed() -> None:
    baseline = np.full((64, 64, 3), 30, dtype=np.uint8)
    frame = baseline.copy()
    frame[8:56, 16:48] = (40, 180, 40)
    occupancy = PixelOccupancyMap(OccupancyConfig(baseline_samples=3))
    occupancy.bind_perception(_Perception(baseline))
    cell = GridCell(0, 0)
    evidence = {cell: _evidence(cell, TileClass.DANGER, 0.95)}
    state = SimpleNamespace(arena_rect=(0, 0, 64, 64), player_center=(-500.0, -500.0))

    cells, clusters = _observe(occupancy, frame, evidence, state)

    assert cells[cell].diff_source is DiffSource.CLASS_REFERENCE
    assert cells[cell].state is OccupancyState.WEAK
    assert not cells[cell].reference_authoritative
    assert cells[cell].occupancy_score <= occupancy.config.class_reference_score_cap
    assert clusters == ()


def test_large_connected_field_is_split_by_humanoid_geometry_limits() -> None:
    occupancy, frame, evidence, state = _setup(3, 4)
    for y in range(4):
        for x in range(3):
            left = x * 64
            top = y * 64
            frame[top + 8 : top + 56, left : left + 64] = (40, 180, 40)

    _, clusters = _observe(occupancy, frame, evidence, state)

    assert clusters
    for cluster in clusters:
        xs = [cell.x for cell in cluster.cells]
        ys = [cell.y for cell in cluster.cells]
        assert len(cluster.cells) <= occupancy.config.cluster_max_cells
        assert max(xs) - min(xs) + 1 <= occupancy.config.cluster_max_width_cells
        assert max(ys) - min(ys) + 1 <= occupancy.config.cluster_max_height_cells
