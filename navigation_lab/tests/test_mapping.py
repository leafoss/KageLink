from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from navigation_lab.mapping import OccupancyGrid, Region, RegionConnection, WorldGraph
from navigation_lab.models import CellState, Point
from navigation_lab.storage import JsonRepository


class MappingTests(unittest.TestCase):
    def test_grid_observation_and_round_trip(self) -> None:
        grid = OccupancyGrid(5, 4)
        grid.observe(Point(2, 1), CellState.WALKABLE, 0.8, "road")
        payload = grid.to_dict()
        restored = OccupancyGrid.from_dict(payload)
        cell = restored.get(Point(2, 1))
        self.assertEqual(cell.state, CellState.WALKABLE)
        self.assertIn("road", cell.labels)

    def test_world_graph_prefers_reliable_route(self) -> None:
        graph = WorldGraph()
        for region_id in ("dojo", "forest", "gate", "konoha"):
            graph.add_region(Region(region_id, region_id, region_id))
        graph.connect(RegionConnection("dojo", "konoha", cost=1, reliability=0.1))
        graph.connect(RegionConnection("dojo", "forest", cost=1, reliability=1))
        graph.connect(RegionConnection("forest", "gate", cost=1, reliability=1))
        graph.connect(RegionConnection("gate", "konoha", cost=1, reliability=1))
        self.assertEqual(graph.route("dojo", "konoha"), ["dojo", "forest", "gate", "konoha"])

    def test_repository_persists_grid_and_world(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = JsonRepository(Path(temp_dir), "test")
            grid = OccupancyGrid(3, 3)
            grid.set(Point(1, 1), CellState.LANDMARK, label="gate")
            repo.save_grid("forest", grid)
            self.assertEqual(repo.load_grid("forest").get(Point(1, 1)).state, CellState.LANDMARK)
            graph = WorldGraph()
            graph.add_region(Region("forest", "Floresta", "Forest"))
            graph.add_region(Region("konoha", "Konoha", "Konoha"))
            graph.connect(RegionConnection("forest", "konoha"))
            repo.save_world(graph)
            self.assertEqual(repo.load_world().route("forest", "konoha"), ["forest", "konoha"])


if __name__ == "__main__":
    unittest.main()
