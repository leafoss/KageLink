from __future__ import annotations

from types import SimpleNamespace
import unittest

from pc_agent.kage_pilot.dojo_chakra_recovery_bridge_v351 import (
    EXITING_MEDITATION,
    MEDITATING,
    install_chakra_recovery_bridge,
)
from pc_agent.kage_pilot.post_combat_v03 import PostCombatDecision


def _fake_engine_type():
    class FakeGuardedEngine:
        def __init__(self, decisions, *, phase=MEDITATING, base_updates=False):
            self._decisions = iter(decisions)
            self.meditation_guard = SimpleNamespace(phase=phase)
            self.health_target = 0.90
            self.chakra_target = 0.40
            self.y_confirm_frames = 2
            self.y_fast_active = False
            self.pending_y_action = None
            self._y_on_hits = 0
            self._y_off_hits = 0
            self.update_calls = 0
            self.base_updates = bool(base_updates)

        def _update_fast_chakra(self, decision) -> None:
            self.update_calls += 1
            if self.pending_y_action is not None:
                return
            health = decision.health
            chakra = decision.chakra
            if health is None or chakra is None:
                return
            hp = float(health)
            ch = float(chakra)
            if self.y_fast_active:
                if ch >= self.chakra_target:
                    self._y_off_hits += 1
                else:
                    self._y_off_hits = 0
                if decision.state == "READY" or self._y_off_hits >= self.y_confirm_frames:
                    self.pending_y_action = "off"
                    self._y_off_hits = 0
                return
            if decision.state == MEDITATING and hp > self.health_target and ch < self.chakra_target:
                self._y_on_hits += 1
            else:
                self._y_on_hits = 0
            if self._y_on_hits >= self.y_confirm_frames:
                self.pending_y_action = "on"
                self._y_on_hits = 0

        def step(self, *args, **kwargs):
            del args, kwargs
            decision = next(self._decisions)
            if self.base_updates:
                self._update_fast_chakra(decision)
            return decision

    return FakeGuardedEngine


class ChakraRecoveryBridgeV351Tests(unittest.TestCase):
    def _install(self):
        events = []
        runtime = SimpleNamespace(
            ClosedLoopVisualRecoveryEngine=_fake_engine_type(),
            _telemetry=lambda event, fields: events.append((event, fields)),
        )
        engine_type = install_chakra_recovery_bridge(runtime)
        return engine_type, events

    def test_low_chakra_queues_y_on_while_guard_is_meditating(self):
        engine_type, events = self._install()
        low = PostCombatDecision(
            state=MEDITATING,
            health=0.95,
            chakra=0.25,
            reason="guarded meditation",
        )
        engine = engine_type([low, low])

        engine.step()
        self.assertIsNone(engine.pending_y_action)
        engine.step()

        self.assertEqual(engine.pending_y_action, "on")
        self.assertEqual(engine.update_calls, 2)
        self.assertTrue(
            any(
                event == "DOJO_FAST_CHAKRA_ACTION_QUEUED"
                and fields.get("action") == "on"
                for event, fields in events
            )
        )

    def test_exit_queues_y_off_before_the_guarded_v_tap(self):
        engine_type, events = self._install()
        exiting = PostCombatDecision(
            state=EXITING_MEDITATION,
            tap_v=True,
            health=0.98,
            chakra=0.25,
            reason="timeout safe exit",
        )
        engine = engine_type([exiting], phase=EXITING_MEDITATION)
        engine.y_fast_active = True

        decision = engine.step()

        self.assertTrue(decision.tap_v)
        self.assertEqual(engine.pending_y_action, "off")
        self.assertTrue(
            any(
                event == "DOJO_FAST_CHAKRA_ACTION_QUEUED"
                and fields.get("action") == "off"
                for event, fields in events
            )
        )

    def test_idle_base_step_is_not_double_updated(self):
        engine_type, _events = self._install()
        decision = PostCombatDecision(
            state=MEDITATING,
            health=0.95,
            chakra=0.25,
        )
        engine = engine_type([decision], phase="IDLE", base_updates=True)

        engine.step()

        self.assertEqual(engine.update_calls, 1)
        self.assertIsNone(engine.pending_y_action)

    def test_install_is_idempotent(self):
        engine_type, events = self._install()
        runtime = SimpleNamespace(
            ClosedLoopVisualRecoveryEngine=engine_type,
            _telemetry=lambda event, fields: events.append((event, fields)),
        )

        self.assertIs(install_chakra_recovery_bridge(runtime), engine_type)
        installed = [event for event, _fields in events if event == "DOJO_FAST_CHAKRA_BRIDGE_INSTALLED"]
        self.assertEqual(len(installed), 1)


if __name__ == "__main__":
    unittest.main()
