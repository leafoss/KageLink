from __future__ import annotations

import unittest

from navigation_lab.models import NavigationState
from navigation_lab.state_machine import InvalidTransition, NavigationStateMachine


class StateMachineTests(unittest.TestCase):
    def test_valid_navigation_flow(self) -> None:
        machine = NavigationStateMachine()
        machine.transition(NavigationState.PLANNING, "route requested")
        machine.transition(NavigationState.NAVIGATING, "route available")
        machine.transition(NavigationState.VERIFYING_PROGRESS, "movement sent")
        machine.transition(NavigationState.ARRIVED, "destination confirmed")
        self.assertEqual(machine.state, NavigationState.ARRIVED)

    def test_invalid_transition_is_rejected(self) -> None:
        machine = NavigationStateMachine()
        with self.assertRaises(InvalidTransition):
            machine.transition(NavigationState.ARRIVED, "invalid shortcut")


if __name__ == "__main__":
    unittest.main()
