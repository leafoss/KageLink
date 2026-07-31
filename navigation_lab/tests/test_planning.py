from __future__ import annotations

import unittest

from navigation_lab.mapping import OccupancyGrid
from navigation_lab.models import CellState, Point
from navigation_lab.planning import PathNotFound, astar, nearest_frontier


class PlanningTests(unittest.TestCase):
    def test_astar_avoids_blocked_cells(self) -> None:
        grid = OccupancyGrid(7, 5, default=CellState.WALKABLE)
        for y in range(4):
            grid.set(Point(3, y), CellState.BLOCKED)
        path = astar(grid, Point(1, 1), Point(5, 1))
        self.assertNotIn(Point(3, 1), path)
        self.assertEqual(path[0], Point(1, 1))
        self.assertEqual(path[-1], Point(5, 1))

    def test_astar_reports_missing_route(self) -> None:
        grid = OccupancyGrid(3, 3, default=CellState.WALKABLE)
        grid.set(Point(1, 0), CellState.BLOCKED)
        grid.set(Point(1, 1), CellState.BLOCKED)
        grid.set(Point(1, 2), CellState.BLOCKED)
        with self.assertRaises(PathNotFound):
            astar(grid, Point(0, 1), Point(2, 1))

    def test_nearest_frontier(self) -> None:
        grid = OccupancyGrid(5, 5)
        grid.set(Point(2, 2), CellState.WALKABLE)
        self.assertEqual(nearest_frontier(grid, Point(2, 2)), Point(2, 2))


if __name__ == "__main__":
    unittest.main()
