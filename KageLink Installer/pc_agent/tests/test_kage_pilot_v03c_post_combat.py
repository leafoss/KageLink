from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np

from pc_agent.kage_pilot.post_combat_v03b import LeaderMatchV2
from pc_agent.kage_pilot.post_combat_v03c import (
    ExpandingSquareSearch,
    PostCombatRecoveryEngineV3,
)


class FakeObserver:
    tile_size = 32.0
    grid_origin = (0.0, 0.0)


class FakeLeaderDetector:
    def __init__(self, matches):
        self.matches = list(matches)
        self.index = 0

    def find(self, frame_bgr, *, arena_rect=None, flow=None, now=None):
        del frame_bgr, arena_rect, flow, now
        if not self.matches:
            return None
        value = self.matches[min(self.index, len(self.matches) - 1)]
        self.index += 1
        return value


class KagePilotV03CPostCombatTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((320, 320, 3), dtype=np.uint8)
        self.state = SimpleNamespace(
            arena_rect=(0, 0, 320, 320),
            player_center=(160.0, 160.0),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0),
        )
        self.observer = FakeObserver()

    def test_expanding_square_search_is_bounded_and_dead_man(self):
        search = ExpandingSquareSearch(pulses_per_tile=2, max_radius_tiles=2)
        pulses = []
        while True:
            pulse = search.next_pulse()
            if pulse is None:
                break
            pulses.append(pulse)
        self.assertEqual(pulses[:4], ["up", "up", "right", "right"])
        self.assertIn("down", pulses)
        self.assertIn("left", pulses)
        self.assertTrue(search.exhausted)

    def test_no_anchor_waits_then_starts_bounded_search(self):
        engine = PostCombatRecoveryEngineV3(
            leader_detector=FakeLeaderDetector([None, None]),
            search_delay_seconds=0.25,
            search_timeout_seconds=10.0,
            search_pulses_per_tile=2,
            search_max_radius_tiles=2,
        )
        waiting = engine.step(self.frame, self.state, self.observer, now=1.0)
        searching = engine.step(self.frame, self.state, self.observer, now=1.3)
        self.assertEqual(waiting.state, "SEARCH_WAIT")
        self.assertIsNone(waiting.move_pulse)
        self.assertEqual(searching.state, "SEARCH_LEADER")
        self.assertEqual(searching.move_pulse, "up")

    def test_memory_returns_toward_trainer_but_never_taps_v(self):
        memory = LeaderMatchV2(
            score=0.98,
            bbox=(245, 120, 32, 45),
            foot=(261.0, 160.0),
            source="memory",
        )
        engine = PostCombatRecoveryEngineV3(leader_detector=FakeLeaderDetector([memory]))
        decision = engine.step(self.frame, self.state, self.observer, now=1.0)
        self.assertEqual(decision.state, "RETURN_TO_LEADER")
        self.assertEqual(decision.move_pulse, "right")
        self.assertFalse(decision.tap_v)

    def test_adjacent_memory_holds_until_two_visual_confirmations(self):
        memory = LeaderMatchV2(0.98, (160, 120, 32, 45), (176.0, 160.0), "memory")
        visual = LeaderMatchV2(0.99, (160, 120, 32, 45), (176.0, 160.0), "visual")
        engine = PostCombatRecoveryEngineV3(
            leader_detector=FakeLeaderDetector([memory, visual, visual]),
            leader_confirm_frames=2,
        )
        remembered = engine.step(self.frame, self.state, self.observer, now=1.0)
        first_visual = engine.step(self.frame, self.state, self.observer, now=1.1)
        second_visual = engine.step(self.frame, self.state, self.observer, now=1.2)
        self.assertFalse(remembered.tap_v)
        self.assertFalse(first_visual.tap_v)
        self.assertTrue(second_visual.tap_v)
        self.assertEqual(second_visual.state, "START_MEDITATION")

    def test_combat_observation_primes_anchor_without_changing_phase(self):
        visual = LeaderMatchV2(0.99, (200, 120, 32, 45), (216.0, 160.0), "visual")
        engine = PostCombatRecoveryEngineV3(leader_detector=FakeLeaderDetector([visual]))
        observed = engine.observe_world(self.frame, self.state, self.observer, now=1.0)
        self.assertIs(observed, visual)
        self.assertIs(engine.last_combat_anchor, visual)
        self.assertFalse(engine.post_started)
        self.assertEqual(engine.state, "SEEK_LEADER")


if __name__ == "__main__":
    unittest.main()
