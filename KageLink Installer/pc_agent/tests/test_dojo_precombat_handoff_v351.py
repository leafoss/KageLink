from __future__ import annotations

import unittest

from pc_agent.kage_pilot import dojo_precombat_guard_v351 as guard


class _Controller:
    def __init__(self) -> None:
        self.repeat_keys = set()
        self.events = []

    def apply_keys(self, keys) -> None:
        self.events.append(("keys", tuple(keys)))

    def release_all(self) -> None:
        self.events.append(("release",))


class DojoPrecombatHandoffV351Tests(unittest.TestCase):
    def tearDown(self) -> None:
        guard.release_precombat_handoff("unit_test_cleanup")

    def test_parent_controller_keeps_r_until_child_handoff_release(self):
        controller = _Controller()
        guarded = guard._GuardedRequestController(controller, wait_fn=lambda _seconds: None)
        guarded.arm_after_ok()
        guard._install_precombat_handoff(guarded, controller)

        self.assertTrue(guard.precombat_handoff_active())
        self.assertEqual(controller.repeat_keys, {"r"})
        self.assertNotIn(("release",), controller.events)

        self.assertTrue(guard.release_precombat_handoff("round_child_armed"))
        self.assertFalse(guard.precombat_handoff_active())
        # The validated controller owner does not call a public close() method.
        # It releases keys, stops its repeat worker and deactivates the core.
        self.assertGreaterEqual(controller.events.count(("release",)), 2)

    def test_releasing_without_active_handoff_is_safe(self):
        guard.release_precombat_handoff("initial_cleanup")
        self.assertFalse(guard.release_precombat_handoff("nothing_active"))


if __name__ == "__main__":
    unittest.main()
