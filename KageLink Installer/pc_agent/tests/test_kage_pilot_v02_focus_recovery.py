from __future__ import annotations

import unittest

from pc_agent.kage_pilot.pilot_v2 import TemporalCombatPilot


class RecoveryAwareController:
    def __init__(self) -> None:
        self.recover_foreground = False
        self.debug = False

    def activate(self) -> None: pass
    def apply_keys(self, keys) -> None: pass
    def release_all(self) -> None: pass
    def tap(self, key, duration=0.08) -> None: pass
    def click_normalized(self, x, y) -> None: pass


class KagePilotV02FocusRecoveryTests(unittest.TestCase):
    def test_v02_enables_safe_foreground_recovery_on_capable_controller(self):
        controller = RecoveryAwareController()
        TemporalCombatPilot(
            model=object(),
            frame_source=object(),
            controller=controller,
            debug=True,
            startup_delay_seconds=0.0,
        )
        self.assertTrue(controller.recover_foreground)
        self.assertTrue(controller.debug)


if __name__ == "__main__":
    unittest.main()
