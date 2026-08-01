from __future__ import annotations

import unittest

from pc_agent.kage_pilot.meditation_guard_v351 import (
    ENTERING_MEDITATION,
    EXITING_MEDITATION,
    IDLE,
    MEDITATING,
    MeditationTransitionGuard,
)


class MeditationTransitionGuardTests(unittest.TestCase):
    def test_second_v_is_blocked_until_minimum_duration(self):
        guard = MeditationTransitionGuard(
            enter_delay_seconds=5.5,
            exit_delay_seconds=5.5,
            minimum_duration_seconds=5.5,
            timeout_seconds=120.0,
        )

        self.assertTrue(guard.request_enter(10.0))
        self.assertEqual(guard.phase, ENTERING_MEDITATION)
        self.assertFalse(guard.request_enter(10.1))
        self.assertFalse(guard.request_exit(10.1))
        self.assertGreater(guard.cooldown_remaining(10.1), 5.0)

        self.assertIsNone(guard.advance(15.49))
        self.assertEqual(guard.phase, ENTERING_MEDITATION)
        self.assertEqual(guard.advance(15.5), "entered")
        self.assertEqual(guard.phase, MEDITATING)
        self.assertTrue(guard.request_exit(15.5))
        self.assertEqual(guard.phase, EXITING_MEDITATION)

    def test_combat_remains_blocked_until_exit_delay_completes(self):
        guard = MeditationTransitionGuard(
            enter_delay_seconds=5.5,
            exit_delay_seconds=5.5,
            minimum_duration_seconds=5.5,
        )
        guard.request_enter(1.0)
        self.assertFalse(guard.combat_allowed)
        guard.advance(6.5)
        self.assertFalse(guard.combat_allowed)
        guard.request_exit(6.5)
        self.assertFalse(guard.combat_allowed)
        self.assertIsNone(guard.advance(11.99))
        self.assertEqual(guard.advance(12.0), "exited")
        self.assertEqual(guard.phase, IDLE)
        self.assertTrue(guard.combat_allowed)

    def test_configured_delays_never_drop_below_five_seconds(self):
        guard = MeditationTransitionGuard(
            enter_delay_seconds=0.1,
            exit_delay_seconds=1.0,
            minimum_duration_seconds=0.2,
        )
        self.assertEqual(guard.enter_delay_seconds, 5.0)
        self.assertEqual(guard.exit_delay_seconds, 5.0)
        self.assertEqual(guard.minimum_duration_seconds, 5.0)

    def test_timeout_requires_safe_exit_and_never_allows_combat(self):
        guard = MeditationTransitionGuard(timeout_seconds=15.0)
        guard.request_enter(0.0)
        guard.advance(5.5)
        self.assertTrue(guard.timed_out(15.0))
        self.assertTrue(guard.request_exit(15.0, abort_after_exit=True))
        self.assertFalse(guard.combat_allowed)
        guard.advance(20.5)
        self.assertFalse(guard.combat_allowed)
        self.assertTrue(guard.abort_after_exit)


if __name__ == "__main__":
    unittest.main()
