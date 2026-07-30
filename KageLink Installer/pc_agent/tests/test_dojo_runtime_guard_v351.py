from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from pc_agent.kage_pilot.dojo_debug_v351 import DojoDebugSettings
from pc_agent.kage_pilot.dojo_runtime_guard_v351 import install_runtime_guard
from pc_agent.kage_pilot.post_combat_v03 import PostCombatDecision, ResourceLevels


class FakeOverlay:
    control_path = "debug.json"

    def start(self):
        return False

    def close(self):
        return None

    def publish(self, snapshot):
        self.snapshot = snapshot


class FakeResourceReader:
    def __init__(self, levels):
        self.levels = list(levels)
        self.index = 0

    def read(self, frame):
        del frame
        value = self.levels[min(self.index, len(self.levels) - 1)]
        self.index += 1
        return value


class FakePosition:
    def snapshot(self):
        return SimpleNamespace(
            state=SimpleNamespace(value="KNOWN"),
            x=0.0,
            y=0.0,
            confidence=1.0,
        )


class FakeBaseRecoveryEngine:
    def __init__(self, *args, resource_reader=None, **kwargs):
        del args, kwargs
        self.resource_reader = resource_reader
        self.health_target = 0.90
        self.chakra_target = 0.50
        self.recovery_confirm_frames = 2
        self.state = "SEEK_LEADER"
        self.position = FakePosition()
        self.leader_detector = SimpleNamespace(_last_visual=None)
        self._legacy_started = False

    def begin_post_combat(self):
        self.state = "SEEK_LEADER"
        self._legacy_started = False

    def observe_world(self, frame_bgr, observer_state, observer, *, now):
        del frame_bgr, observer_state, observer, now
        return None

    def step(self, frame_bgr, observer_state, observer, *, now):
        del frame_bgr, observer_state, observer, now
        if not self._legacy_started:
            self._legacy_started = True
            self.state = "MEDITATING"
            return PostCombatDecision(
                state="START_MEDITATION",
                tap_v=True,
                leader_score=0.99,
                leader_distance=1,
            )
        return PostCombatDecision(state=self.state)


class RuntimeMeditationGuardTests(unittest.TestCase):
    def _engine(self, levels):
        events = []
        runtime = SimpleNamespace(
            ClosedLoopVisualRecoveryEngine=FakeBaseRecoveryEngine,
            live_runtime=SimpleNamespace(PostCombatRecoveryEngine=None),
            _telemetry=lambda event, fields: events.append((event, fields)),
        )
        settings = DojoDebugSettings(
            meditation_enter_delay_seconds=5.5,
            meditation_exit_delay_seconds=5.5,
            meditation_timeout_seconds=120.0,
        )
        with patch(
            "pc_agent.kage_pilot.dojo_runtime_guard_v351.read_debug_settings",
            return_value=settings,
        ), patch(
            "pc_agent.kage_pilot.dojo_runtime_guard_v351.DojoDebugOverlay.from_environment",
            return_value=FakeOverlay(),
        ):
            engine_type = install_runtime_guard(runtime)
            engine = engine_type(resource_reader=FakeResourceReader(levels))
        return engine, events

    @staticmethod
    def _inputs():
        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        state = SimpleNamespace(
            arena_rect=(0, 0, 960, 540),
            player_center=(480.0, 270.0),
        )
        observer = SimpleNamespace()
        return frame, state, observer

    def test_exact_hp_over_90_chakra_50_regression_skips_meditation(self):
        threshold = ResourceLevels(0.96, 0.50, 44, 22)
        engine, events = self._engine([threshold])
        frame, state, observer = self._inputs()

        decision = engine.step(frame, state, observer, now=10.0)

        self.assertEqual(decision.state, "READY")
        self.assertFalse(decision.tap_v)
        self.assertTrue(engine.can_start_next_combat()[0])
        self.assertTrue(any(name == "DOJO_MEDITATION_SKIPPED" for name, _ in events))

    def test_low_chakra_blocks_second_v_and_next_combat(self):
        low = ResourceLevels(0.96, 0.40, 44, 18)
        ready = ResourceLevels(0.97, 0.60, 45, 27)
        engine, events = self._engine([low, low, ready, ready, ready])
        frame, state, observer = self._inputs()

        enter = engine.step(frame, state, observer, now=10.0)
        too_early = engine.step(frame, state, observer, now=10.1)
        entered = engine.step(frame, state, observer, now=15.5)
        exit_request = engine.step(frame, state, observer, now=15.6)
        exiting = engine.step(frame, state, observer, now=16.0)
        ready_decision = engine.step(frame, state, observer, now=21.1)

        self.assertEqual(enter.state, "ENTERING_MEDITATION")
        self.assertTrue(enter.tap_v)
        self.assertEqual(too_early.state, "ENTERING_MEDITATION")
        self.assertFalse(too_early.tap_v)
        self.assertEqual(entered.state, "MEDITATING")
        self.assertFalse(entered.tap_v)
        self.assertEqual(exit_request.state, "EXITING_MEDITATION")
        self.assertTrue(exit_request.tap_v)
        self.assertEqual(exiting.state, "EXITING_MEDITATION")
        self.assertFalse(exiting.tap_v)
        self.assertEqual(ready_decision.state, "READY")
        self.assertTrue(engine.can_start_next_combat()[0])
        self.assertTrue(any(name == "DOJO_COMBAT_START_BLOCKED" for name, _ in events))

    def test_resources_already_ready_skip_meditation_without_v(self):
        ready = ResourceLevels(0.96, 0.60, 45, 27)
        engine, events = self._engine([ready])
        frame, state, observer = self._inputs()
        decision = engine.step(frame, state, observer, now=1.0)
        self.assertEqual(decision.state, "READY")
        self.assertFalse(decision.tap_v)
        self.assertTrue(engine.can_start_next_combat()[0])
        self.assertTrue(any(name == "DOJO_MEDITATION_SKIPPED" for name, _ in events))


if __name__ == "__main__":
    unittest.main()
