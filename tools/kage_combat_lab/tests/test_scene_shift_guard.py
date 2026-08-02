from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from kage_combat_lab.domain import GridCell
from kage_combat_lab.occupancy_model import OccupancyConfig, OccupancyState
from kage_combat_lab.pixel_occupancy import PixelOccupancyMap
from kage_combat_lab.tile_perception import TileClass, TileEvidence


def _evidence(cell: GridCell, *, category: TileClass, similarity: float) -> TileEvidence:
    return TileEvidence(
        cell=cell,
        bbox=(cell.x * 64, cell.y * 64, 64, 64),
        category=category,
        similarity=similarity,
        novelty=0.0,
        known_terrain=True,
        temporal_activity=0.0,
        activity_bbox=None,
        matched_example_id="test",
    )


def _perception(reference: np.ndarray):
    return SimpleNamespace(
        reference_crop=lambda item, prefer_non_danger=False: reference.copy(),
        _terrain_examples=(),
    )


def test_semantic_danger_without_real_pixel_change_is_not_occupancy() -> None:
    floor = np.full((64, 64, 3), 30, dtype=np.uint8)
    occupancy = PixelOccupancyMap(OccupancyConfig())
    occupancy.bind_perception(_perception(floor))
    cell = GridCell(0, 0)

    observed, _ = occupancy.observe(
        frame=floor.copy(),
        state=SimpleNamespace(arena_rect=(0, 0, 64, 64)),
        candidates=(),
        evidence={cell: _evidence(cell, category=TileClass.DANGER, similarity=0.95)},
        danger_fresh=True,
    )

    assert observed[cell].danger_prior == 0.95
    assert observed[cell].true_changed_ratio == 0.0
    assert observed[cell].state is OccupancyState.EMPTY
    assert occupancy.clusters(observed, ()) == ()


def test_full_cell_class_reference_mismatch_has_zero_authority() -> None:
    reference = np.full((64, 64, 3), 30, dtype=np.uint8)
    current = np.full((64, 64, 3), 220, dtype=np.uint8)
    occupancy = PixelOccupancyMap(OccupancyConfig())
    occupancy.bind_perception(_perception(reference))
    cell = GridCell(0, 0)

    observed, _ = occupancy.observe(
        frame=current,
        state=SimpleNamespace(arena_rect=(0, 0, 64, 64)),
        candidates=(),
        evidence={cell: _evidence(cell, category=TileClass.UNKNOWN, similarity=0.70)},
        danger_fresh=False,
    )

    assert observed[cell].true_changed_ratio == 1.0
    assert observed[cell].largest_blob_area == 4096
    assert observed[cell].state is OccupancyState.EMPTY
    assert observed[cell].occupancy_score == 0.0


def test_full_height_boundary_change_invalidates_exact_baselines() -> None:
    rows, columns = 6, 14
    floor = np.full((rows * 64, columns * 64, 3), 30, dtype=np.uint8)
    shifted = floor.copy()
    shifted[:, (columns - 1) * 64 :, :] = 210
    occupancy = PixelOccupancyMap(OccupancyConfig())
    occupancy.bind_perception(_perception(floor[:64, :64]))
    evidence = {}
    for y in range(rows):
        for x in range(columns):
            cell = GridCell(x, y)
            evidence[cell] = _evidence(
                cell,
                category=TileClass.DANGER if x == columns - 1 else TileClass.WALKABLE,
                similarity=0.92 if x == columns - 1 else 0.99,
            )
            occupancy.exact_baselines[cell] = np.full((64, 64, 3), 30, dtype=np.uint8)

    observed, _ = occupancy.observe(
        frame=shifted,
        state=SimpleNamespace(arena_rect=(0, 0, columns * 64, rows * 64)),
        candidates=(),
        evidence=evidence,
        danger_fresh=True,
    )

    boundary = {GridCell(columns - 1, y) for y in range(rows)}
    assert set(occupancy.last_scene_shift_cells) == boundary
    assert occupancy.scene_shift_generation == 1
    assert not boundary & set(occupancy.exact_baselines)
    assert all(observed[cell].state is OccupancyState.EMPTY for cell in boundary)
    assert all(observed[cell].danger_prior == 0.0 for cell in boundary)
