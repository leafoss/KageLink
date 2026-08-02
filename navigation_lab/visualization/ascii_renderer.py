from __future__ import annotations

from ..mapping import OccupancyGrid
from ..models import CellState, Point


_SYMBOLS = {
    CellState.UNKNOWN: "?",
    CellState.WALKABLE: ".",
    CellState.BLOCKED: "#",
    CellState.TEMPORARY_BLOCK: "X",
    CellState.DANGEROUS: "!",
    CellState.LANDMARK: "L",
    CellState.TRANSITION: "T",
    CellState.DESTINATION: "D",
    CellState.CURRENT_POSITION: "P",
    CellState.PLANNED_PATH: "*",
    CellState.VISITED: ",",
}


def render_ascii(
    grid: OccupancyGrid,
    position: Point | None = None,
    goal: Point | None = None,
    path: list[Point] | None = None,
) -> str:
    path_set = set(path or [])
    lines: list[str] = []
    for y in range(grid.height):
        row: list[str] = []
        for x in range(grid.width):
            point = Point(x, y)
            if position == point:
                row.append("P")
            elif goal == point:
                row.append("G")
            elif point in path_set:
                row.append("*")
            else:
                row.append(_SYMBOLS[grid.get(point).state])
        lines.append("".join(row))
    return "\n".join(lines)
