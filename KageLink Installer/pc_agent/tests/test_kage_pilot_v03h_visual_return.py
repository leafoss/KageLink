from __future__ import annotations

import unittest
from unittest.mock import patch

from pc_agent.kage_pilot.post_combat_v03 import PostCombatDecision
from pc_agent.kage_pilot.post_combat_v03h import VisualProgressPostCombatRecoveryEngine


class FakeDetector:
    last_raw_score = -1.0
    last_raw_location = None
    _last_visual = None

    def find(self, *args, **kwargs):
        del args, kwargs
        return None


class KagePilotV03HVisualReturnTests(unittest.TestCase):
    def _engine(self):
        return VisualProgressPostCombatRecoveryEngine(
            leader_detector=FakeDetector(),
            search_timeout_seconds=45.0,
            search_pulses_per_tile=1,
        )

    def test_shorter_visual_distance_clears_false_block_and_keeps_direct_route(self):
        engine = self._engine()
        engine._last_visual_distance = 3
        engine.last_movement_direction = "up"
        engine.last_movement_detected = False
        engine._blocked_until["up"] = 100.0

        direct = PostCombatDecision(
            state="SEEK_LEADER",
            move_pulse="up",
            leader_score=0.937,
            leader_distance=2,
            reason="return toward trainer (visual) / retornar ao treinador (visual): up",
        )
        with patch(
            "pc_agent.kage_pilot.post_combat_v03h.PostCombatRecoveryEngineV4.step",
            return_value=direct,
        ):
            result = engine.step(None, None, None, now=1.0)

        self.assertEqual(result.move_pulse, "up")
        self.assertFalse(engine._is_blocked("up", now=1.0))
        self.assertTrue(engine.last_movement_detected)

    def test_visual_no_progress_still_uses_safe_detour_after_confirmed_block(self):
        engine = self._engine()
        engine._last_visual_distance = 3
        engine.last_movement_direction = "up"
        engine.last_movement_detected = False
        engine._blocked_until["up"] = 100.0

        direct = PostCombatDecision(
            state="SEEK_LEADER",
            move_pulse="up",
            leader_score=0.937,
            leader_distance=3,
            reason="return toward trainer (visual) / retornar ao treinador (visual): up",
        )
        with patch(
            "pc_agent.kage_pilot.post_combat_v03h.PostCombatRecoveryEngineV4.step",
            return_value=direct,
        ):
            result = engine.step(None, None, None, now=1.0)

        self.assertEqual(result.state, "OBSTACLE_DETOUR")
        self.assertNotEqual(result.move_pulse, "up")


if __name__ == "__main__":
    unittest.main()
