from __future__ import annotations

import unittest

from pc_agent.kage_pilot.entity_observer import Candidate
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
    PersistentBackgroundWaterAwareEntityTracker,
)
from pc_agent.kage_pilot.water_filter_v03 import OccupancyDynamicBackground


def water_candidate(x: float, y: float, *, w: int = 34, h: int = 10) -> Candidate:
    return Candidate(
        bbox=(round(x - w / 2), round(y - h / 2), w, h),
        center=(x, y),
        contour_area=float(w * h * 0.65),
        motion_energy=0.42,
        edge_density=0.18,
        shape_score=0.45,
    )


class KagePilotV03WaterFilterTests(unittest.TestCase):
    def test_dense_shifting_water_band_becomes_dynamic_background(self):
        config = V03ObserverConfig(
            background_min_neighbors=2,
            background_min_dense_hits=5,
            background_min_age=0.4,
            background_similarity=0.88,
            background_player_guard=40,
        ).normalized()
        memory = OccupancyDynamicBackground(config)
        player = (20.0, 180.0)

        last_filtered = []
        for frame in range(14):
            shift = float((frame % 3) * 4)
            group = [
                water_candidate(200 + shift, 55),
                water_candidate(228 + shift, 57),
                water_candidate(256 + shift, 54),
            ]
            # Similar but not identical signatures mimic changing animated texture.
            if frame % 2:
                signatures = [(0.86, 0.34, 0.10, 0.05)] * 3
            else:
                signatures = [(0.91, 0.28, 0.08, 0.04)] * 3
            last_filtered, _ = memory.observe_and_filter(
                group,
                signatures,
                player_center=player,
                now=frame * 0.10,
            )

        self.assertGreater(memory.mature_cells, 0)
        self.assertGreater(memory.suppressed_last_frame, 0)
        self.assertLess(len(last_filtered), 3)

    def test_mature_water_region_does_not_suppress_player_contact_zone(self):
        config = V03ObserverConfig(
            background_min_neighbors=2,
            background_min_dense_hits=4,
            background_min_age=0.3,
            background_player_guard=70,
        ).normalized()
        memory = OccupancyDynamicBackground(config)
        signatures = [(0.9, 0.3, 0.1, 0.05)] * 3
        group = [water_candidate(200, 60), water_candidate(228, 60), water_candidate(256, 60)]

        for frame in range(10):
            memory.observe_and_filter(
                group,
                signatures,
                player_center=(20.0, 180.0),
                now=frame * 0.10,
            )

        filtered, _ = memory.observe_and_filter(
            group,
            signatures,
            player_center=(228.0, 60.0),
            now=1.2,
        )
        self.assertEqual(len(filtered), 3)

    def test_player_recalibration_reset_preserves_background_memory(self):
        config = V03ObserverConfig(
            background_min_neighbors=2,
            background_min_dense_hits=4,
            background_min_age=0.3,
            background_player_guard=40,
        ).normalized()
        tracker = PersistentBackgroundWaterAwareEntityTracker(config)
        signatures = [(0.9, 0.3, 0.1, 0.05)] * 3
        group = [water_candidate(200, 60), water_candidate(228, 60), water_candidate(256, 60)]

        for frame in range(10):
            tracker.background.observe_and_filter(
                group,
                signatures,
                player_center=(20.0, 180.0),
                now=frame * 0.10,
            )

        before = tracker.background.mature_cells
        self.assertGreater(before, 0)
        tracker.reset()
        self.assertEqual(tracker.background.mature_cells, before)

    def test_explicit_full_reset_clears_background_memory(self):
        config = V03ObserverConfig(
            background_min_neighbors=2,
            background_min_dense_hits=4,
            background_min_age=0.3,
            background_player_guard=40,
        ).normalized()
        tracker = PersistentBackgroundWaterAwareEntityTracker(config)
        signatures = [(0.9, 0.3, 0.1, 0.05)] * 3
        group = [water_candidate(200, 60), water_candidate(228, 60), water_candidate(256, 60)]

        for frame in range(10):
            tracker.background.observe_and_filter(
                group,
                signatures,
                player_center=(20.0, 180.0),
                now=frame * 0.10,
            )

        self.assertGreater(tracker.background.mature_cells, 0)
        tracker.full_reset()
        self.assertEqual(tracker.background.mature_cells, 0)


if __name__ == "__main__":
    unittest.main()
