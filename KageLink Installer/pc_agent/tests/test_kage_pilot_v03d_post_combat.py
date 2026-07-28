from __future__ import annotations

import unittest

from pc_agent.kage_pilot.post_combat_v03d import (
    ConcentricCellRingSearch,
    PostCombatRecoveryEngineV4,
)


class KagePilotV03DPostCombatTests(unittest.TestCase):
    def test_first_ring_is_completed_before_second_ring_begins(self):
        search = ConcentricCellRingSearch(
            pulses_per_cell=1,
            arena_width_cells=30,
            arena_height_cells=24,
        )
        first_ring = [search.next_pulse() for _ in range(9)]
        self.assertEqual(
            first_ring,
            [
                "up",
                "right",
                "down",
                "down",
                "left",
                "left",
                "up",
                "up",
                "right",
            ],
        )
        self.assertEqual(search.completed_rings, 1)
        self.assertEqual(search.radius, 2)
        self.assertEqual(search.next_pulse(), "up")

    def test_known_30_by_24_arena_sets_worst_case_radius_29(self):
        search = ConcentricCellRingSearch(
            pulses_per_cell=4,
            arena_width_cells=30,
            arena_height_cells=24,
        )
        self.assertEqual(search.max_radius, 29)

    def test_each_logical_cell_requires_configured_number_of_dead_man_pulses(self):
        search = ConcentricCellRingSearch(
            pulses_per_cell=3,
            arena_width_cells=30,
            arena_height_cells=24,
            max_radius=1,
        )
        self.assertEqual([search.next_pulse() for _ in range(3)], ["up", "up", "up"])
        self.assertEqual(search.visited_logical_cells, 1)
        self.assertEqual(search.next_pulse(), "right")

    def test_v4_widens_only_post_combat_search_timeout(self):
        engine = PostCombatRecoveryEngineV4(search_timeout_seconds=240.0)
        self.assertEqual(engine.search_timeout_seconds, 240.0)
        self.assertIsInstance(engine.search, ConcentricCellRingSearch)


if __name__ == "__main__":
    unittest.main()
