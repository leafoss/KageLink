from __future__ import annotations

from ..mapping import OccupancyGrid
from ..models import CellState, Point


def frontier_cells(grid: OccupancyGrid) -> list[Point]:
    frontiers: list[Point] = []
    for point, cell in grid.iter_points():
        if cell.state == CellState.UNKNOWN:
            continue
        if cell.state in {CellState.BLOCKED, CellState.TEMPORARY_BLOCK, CellState.DANGEROUS}:
            continue
        if any(grid.get(neighbor).state == CellState.UNKNOWN for neighbor in grid.neighbors(point)):
            frontiers.append(point)
    return frontiers


def nearest_frontier(grid: OccupancyGrid, origin: Point) -> Point | None:
    candidates = frontier_cells(grid)
    if not candidates:
        return None
    return min(candidates, key=origin.manhattan)
