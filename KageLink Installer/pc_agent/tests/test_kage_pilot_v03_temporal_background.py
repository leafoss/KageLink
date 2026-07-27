from __future__ import annotations

import unittest

from pc_agent.kage_pilot.entity_observer import Candidate
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.water_filter_v03c import TemporalRecurrenceDynamicBackground


def candidate(x: float, y: float, *, w: int = 42, h: int = 12) -> Candidate:
    return Candidate(
        bbox=(round(x - w / 2), round(y - h / 2), w, h),
        center=(x, y),
        contour_area=float(w * h * 0.65),
        motion_energy=0.32,
        edge_density=0.18,
        shape_score=0.35,
    )


def vertical_character(x: float, y: float) -> Candidate:
    return candidate(x, y, w=18, h=38)


class KagePilotV03TemporalBackgroundTests(unittest.TestCase):
    def test_spread_water_contours_mature_without_local_neighbor_clusters(self):
        config = V03ObserverConfig(
            background_cell_size=32,
            background_neighbor_radius=58,
            background_min_neighbors=3,
            background_min_dense_hits=5,
            background_min_age=0.5,
            background_similarity=0.88,
            background_player_guard=50,
        ).normalized()
        memory = TemporalRecurrenceDynamicBackground(config)
        player = (480.0, 300.0)

        # Every contour is more than 58 px from the next one. The old local-density
        # learner could never learn this layout, which mirrors the real water band.
        base_x = (60.0, 160.0, 260.0, 360.0)
        signatures = [(1.0, 0.0, 0.0, 0.0)] * 4
        filtered = []
        for frame_index in range(10):
            jitter = float((frame_index % 3) - 1) * 3.0
            group = [candidate(x + jitter, 55.0 + (frame_index % 2) * 2.0) for x in base_x]
            filtered, _ = memory.observe_and_filter(
                group,
                signatures,
                player_center=player,
                now=frame_index * 0.15,
            )

        self.assertGreater(memory.mature_cells, 0)
        self.assertGreater(memory.suppressed_last_frame, 0)
        self.assertLess(len(filtered), 4)

    def test_single_vertical_character_does_not_become_background_on_quiet_frames(self):
        config = V03ObserverConfig(
            background_min_neighbors=3,
            background_min_dense_hits=3,
            background_min_age=0.2,
            background_player_guard=40,
        ).normalized()
        memory = TemporalRecurrenceDynamicBackground(config)
        player = (20.0, 200.0)
        signature = [(1.0, 0.0, 0.0, 0.0)]

        for frame_index in range(20):
            filtered, _ = memory.observe_and_filter(
                [vertical_character(240.0, 100.0)],
                signature,
                player_center=player,
                now=frame_index * 0.1,
            )
            self.assertEqual(len(filtered), 1)

        self.assertEqual(memory.mature_cells, 0)
        self.assertEqual(memory.suppressed_last_frame, 0)


if __name__ == "__main__":
    unittest.main()
