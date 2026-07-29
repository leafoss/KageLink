from __future__ import annotations

from types import SimpleNamespace
import unittest

import numpy as np

import kage_pilot_live_v03j_round as runtime
from pc_agent.kage_pilot.post_combat_v03b import LeaderMatchV2


class FakeObserver:
    tile_size = 32.0
    grid_origin = (0.0, 0.0)


class FakeLeaderDetector:
    last_raw_score = -1.0
    last_raw_location = None

    def __init__(self, matches):
        self.matches = list(matches)
        self.index = 0
        self._last_visual = None
        self._last_visual_at = -1e9

    def find(self, frame_bgr, *, arena_rect=None, flow=None, now=None):
        del frame_bgr, arena_rect, flow
        if not self.matches:
            return None
        value = self.matches[min(self.index, len(self.matches) - 1)]
        self.index += 1
        if value is not None and value.source == "visual":
            self._last_visual = value
            self._last_visual_at = float(now)
        return value


VISUAL_ABOVE = LeaderMatchV2(
    score=0.998,
    bbox=(144, 115, 32, 45),
    foot=(160.0, 160.0),
    source="visual",
)
MEMORY_ABOVE = LeaderMatchV2(
    score=0.998,
    bbox=(144, 115, 32, 45),
    foot=(160.0, 160.0),
    source="memory",
)
VISUAL_RIGHT = LeaderMatchV2(
    score=0.998,
    bbox=(176, 137, 32, 45),
    foot=(192.0, 176.0),
    source="visual",
)
MEMORY_RIGHT = LeaderMatchV2(
    score=0.998,
    bbox=(176, 137, 32, 45),
    foot=(192.0, 176.0),
    source="memory",
)


class KagePilotV03JSelfOcclusionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = np.zeros((320, 320, 3), dtype=np.uint8)
        self.observer = FakeObserver()
        self.state_below = SimpleNamespace(
            arena_rect=(0, 0, 320, 320),
            player_center=(160.0, 192.0),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0),
        )
        self.state_left = SimpleNamespace(
            arena_rect=(0, 0, 320, 320),
            player_center=(160.0, 176.0),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0),
        )

    @staticmethod
    def _engine(matches, **kwargs):
        return runtime.SelfOcclusionFastChakraRecoveryEngine(
            leader_detector=FakeLeaderDetector(matches),
            leader_confirm_frames=2,
            adjacent_memory_reacquire_seconds=1.0,
            search_delay_seconds=0.25,
            search_timeout_seconds=10.0,
            search_pulses_per_tile=2,
            search_max_radius_tiles=2,
            self_occlusion_visual_recency_seconds=3.0,
            self_occlusion_settle_seconds=0.65,
            **kwargs,
        )

    def test_player_below_trainer_gets_one_lateral_escape_never_up(self):
        engine = self._engine([VISUAL_ABOVE, MEMORY_ABOVE, MEMORY_ABOVE, MEMORY_ABOVE])

        first_visual = engine.step(self.frame, self.state_below, self.observer, now=1.0)
        memory_hold = engine.step(self.frame, self.state_below, self.observer, now=1.1)
        escape = engine.step(self.frame, self.state_below, self.observer, now=2.2)
        settle = engine.step(self.frame, self.state_below, self.observer, now=2.3)

        self.assertFalse(first_visual.tap_v)
        self.assertFalse(memory_hold.tap_v)
        self.assertEqual(escape.state, "SELF_OCCLUSION_ESCAPE")
        self.assertIn(escape.move_pulse, {"left", "right"})
        self.assertNotEqual(escape.move_pulse, "up")
        self.assertFalse(escape.tap_v)
        self.assertIn("POSSIBLE_SELF_OCCLUSION", escape.reason)
        self.assertEqual(settle.state, "SELF_OCCLUSION_WAIT")
        self.assertIsNone(settle.move_pulse)
        self.assertFalse(settle.tap_v)

    def test_escape_is_emitted_only_once_before_general_reacquisition(self):
        engine = self._engine(
            [VISUAL_ABOVE, MEMORY_ABOVE, MEMORY_ABOVE, MEMORY_ABOVE, MEMORY_ABOVE]
        )

        decisions = [
            engine.step(self.frame, self.state_below, self.observer, now=1.0),
            engine.step(self.frame, self.state_below, self.observer, now=1.1),
            engine.step(self.frame, self.state_below, self.observer, now=2.2),
            engine.step(self.frame, self.state_below, self.observer, now=2.3),
            engine.step(self.frame, self.state_below, self.observer, now=3.0),
        ]

        escapes = [decision for decision in decisions if decision.state == "SELF_OCCLUSION_ESCAPE"]
        self.assertEqual(len(escapes), 1)
        self.assertEqual(decisions[-1].state, "REACQUIRE_LEADER_VISUAL")
        self.assertFalse(any(decision.tap_v for decision in decisions))

    def test_two_current_visuals_after_escape_authorize_v(self):
        engine = self._engine(
            [VISUAL_ABOVE, MEMORY_ABOVE, MEMORY_ABOVE, VISUAL_ABOVE, VISUAL_ABOVE]
        )

        engine.step(self.frame, self.state_below, self.observer, now=1.0)
        engine.step(self.frame, self.state_below, self.observer, now=1.1)
        escape = engine.step(self.frame, self.state_below, self.observer, now=2.2)
        first_visual = engine.step(self.frame, self.state_below, self.observer, now=2.3)
        second_visual = engine.step(self.frame, self.state_below, self.observer, now=2.4)

        self.assertEqual(escape.state, "SELF_OCCLUSION_ESCAPE")
        self.assertFalse(first_visual.tap_v)
        self.assertTrue(second_visual.tap_v)
        self.assertEqual(second_visual.state, "START_MEDITATION")

    def test_trainer_to_right_uses_vertical_perpendicular_escape(self):
        engine = self._engine([VISUAL_RIGHT, MEMORY_RIGHT, MEMORY_RIGHT])

        engine.step(self.frame, self.state_left, self.observer, now=1.0)
        engine.step(self.frame, self.state_left, self.observer, now=1.1)
        escape = engine.step(self.frame, self.state_left, self.observer, now=2.2)

        self.assertEqual(escape.state, "SELF_OCCLUSION_ESCAPE")
        self.assertIn(escape.move_pulse, {"up", "down"})
        self.assertNotEqual(escape.move_pulse, "right")

    def test_without_recent_visual_memory_uses_existing_bounded_search(self):
        engine = self._engine([MEMORY_ABOVE, MEMORY_ABOVE, MEMORY_ABOVE])

        initial = engine.step(self.frame, self.state_below, self.observer, now=1.0)
        reacquire = engine.step(self.frame, self.state_below, self.observer, now=2.2)

        self.assertEqual(initial.state, "SEEK_LEADER")
        self.assertEqual(reacquire.state, "REACQUIRE_VISUAL_WAIT")
        self.assertNotEqual(reacquire.state, "SELF_OCCLUSION_ESCAPE")
        self.assertFalse(reacquire.tap_v)

    def test_blocked_perpendicular_directions_fall_back_without_forcing_movement(self):
        engine = self._engine([VISUAL_ABOVE, MEMORY_ABOVE, MEMORY_ABOVE])
        engine._blocked_until["left"] = 100.0
        engine._blocked_until["right"] = 100.0

        engine.step(self.frame, self.state_below, self.observer, now=1.0)
        engine.step(self.frame, self.state_below, self.observer, now=1.1)
        decision = engine.step(self.frame, self.state_below, self.observer, now=2.2)

        self.assertEqual(decision.state, "REACQUIRE_VISUAL_WAIT")
        self.assertIsNone(decision.move_pulse)
        self.assertFalse(decision.tap_v)


if __name__ == "__main__":
    unittest.main()
