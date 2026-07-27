from __future__ import annotations

import unittest

from pc_agent.kage_pilot.entity_observer import Candidate, FlowEstimate
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.water_filter_v03b import CombatSelectiveWaterAwareEntityTracker


def candidate(x: float, y: float, *, w: int = 18, h: int = 38) -> Candidate:
    return Candidate(
        bbox=(round(x - w / 2), round(y - h / 2), w, h),
        center=(x, y),
        contour_area=float(w * h * 0.62),
        motion_energy=0.35,
        edge_density=0.22,
        shape_score=0.92,
    )


class KagePilotV03CombatSelectiveWaterTests(unittest.TestCase):
    def test_close_track_is_protected_from_background_pruning(self):
        config = V03ObserverConfig(background_player_guard=70).normalized()
        tracker = CombatSelectiveWaterAwareEntityTracker(config)
        player = (100.0, 100.0)

        tracker.update([candidate(135.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.0)
        self.assertEqual(len(tracker.tracks), 1)

    def test_far_slow_track_is_not_combat_protected(self):
        config = V03ObserverConfig(background_player_guard=70).normalized()
        tracker = CombatSelectiveWaterAwareEntityTracker(config)
        player = (20.0, 180.0)

        tracker.update([candidate(220.0, 60.0, w=34, h=10)], flow=FlowEstimate(), player_center=player, now=0.0)
        track_id = tracker.tracks[0].track_id
        self.assertFalse(tracker._combat_like(track_id, player))


if __name__ == "__main__":
    unittest.main()
