from __future__ import annotations

import unittest

from pc_agent.kage_pilot.entity_observer import Candidate, FlowEstimate
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.water_filter_v03 import WaterAwareEntityTracker


def candidate(x: float, y: float, *, w: int = 34, h: int = 10) -> Candidate:
    return Candidate(
        bbox=(round(x - w / 2), round(y - h / 2), w, h),
        center=(x, y),
        contour_area=float(w * h * 0.65),
        motion_energy=0.42,
        edge_density=0.18,
        shape_score=0.45,
    )


class KagePilotV03BackgroundPruningTests(unittest.TestCase):
    def test_mature_dynamic_region_prevents_new_false_track(self):
        config = V03ObserverConfig(
            background_min_neighbors=2,
            background_min_dense_hits=4,
            background_min_age=0.3,
            background_player_guard=40,
            background_similarity=0.82,
        ).normalized()
        tracker = WaterAwareEntityTracker(config)
        player = (20.0, 180.0)
        group = [candidate(200, 60), candidate(228, 60), candidate(256, 60)]
        signatures = [(0.9, 0.3, 0.1, 0.05)] * 3

        for frame in range(10):
            tracker.background.observe_and_filter(
                group,
                signatures,
                player_center=player,
                now=frame * 0.10,
            )

        self.assertGreater(tracker.background.mature_cells, 0)
        tracker.update(group, flow=FlowEstimate(), player_center=player, now=1.2)
        self.assertLess(len(tracker.tracks), len(group))

    def test_near_player_candidate_is_protected_from_dynamic_background(self):
        config = V03ObserverConfig(
            background_min_neighbors=2,
            background_min_dense_hits=4,
            background_min_age=0.3,
            background_player_guard=70,
        ).normalized()
        tracker = WaterAwareEntityTracker(config)
        far_player = (20.0, 180.0)
        group = [candidate(200, 60), candidate(228, 60), candidate(256, 60)]
        signatures = [(0.9, 0.3, 0.1, 0.05)] * 3

        for frame in range(10):
            tracker.background.observe_and_filter(
                group,
                signatures,
                player_center=far_player,
                now=frame * 0.10,
            )

        close_player = (228.0, 60.0)
        tracker.update([candidate(250, 60, w=18, h=38)], flow=FlowEstimate(), player_center=close_player, now=1.2)
        self.assertEqual(len(tracker.tracks), 1)


if __name__ == "__main__":
    unittest.main()
