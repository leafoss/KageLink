from __future__ import annotations

from heapq import heappop, heappush
from itertools import count

from ..mapping import OccupancyGrid
from ..models import CellState, Point


class PathNotFound(RuntimeError):
    pass


def _movement_cost(grid: OccupancyGrid, point: Point) -> float:
    cell = grid.get(point)
    if cell.state == CellState.UNKNOWN:
        return 2.5
    if cell.state == CellState.VISITED:
        return 0.9
    if cell.state in {CellState.LANDMARK, CellState.TRANSITION, CellState.DESTINATION}:
        return 0.8
    return 1.0


def astar(grid: OccupancyGrid, start: Point, goal: Point, allow_unknown: bool = False) -> list[Point]:
    if not grid.in_bounds(start) or not grid.in_bounds(goal):
        raise PathNotFound("Start or goal is outside the grid")
    sequence = count()
    open_set: list[tuple[float, int, Point]] = [(0.0, next(sequence), start)]
    came_from: dict[Point, Point] = {}
    g_score: dict[Point, float] = {start: 0.0}
    closed: set[Point] = set()
    while open_set:
        _, _, current = heappop(open_set)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return list(reversed(path))
        if current in closed:
            continue
        closed.add(current)
        for neighbor in grid.neighbors(current):
            if neighbor != goal and not grid.is_walkable(neighbor, allow_unknown=allow_unknown):
                continue
            if grid.get(neighbor).state in {CellState.BLOCKED, CellState.TEMPORARY_BLOCK, CellState.DANGEROUS}:
                continue
            tentative = g_score[current] + _movement_cost(grid, neighbor)
            if tentative < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                priority = tentative + neighbor.manhattan(goal)
                heappush(open_set, (priority, next(sequence), neighbor))
    raise PathNotFound(f"No route from {start} to {goal}")
