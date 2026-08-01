from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from pc_agent.kage_pilot.dojo_debug_v351 import (
    DojoDebugSettings,
    read_debug_settings,
    write_debug_settings,
)
from pc_agent.kage_pilot.dojo_meditation_timeout_v351 import (
    MIN_SAFE_MEDITATION_TIMEOUT_SECONDS,
    ensure_safe_meditation_timeout,
    install_meditation_timeout_bridge,
)
from pc_agent.kage_pilot.meditation_guard_v351 import MeditationTransitionGuard


class DojoMeditationTimeoutV351Tests(unittest.TestCase):
    def test_missing_or_legacy_setting_is_persisted_as_180_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dojo_debug.json"
            migrated = ensure_safe_meditation_timeout(path)
            persisted = read_debug_settings(path)

        self.assertEqual(
            migrated.meditation_timeout_seconds,
            MIN_SAFE_MEDITATION_TIMEOUT_SECONDS,
        )
        self.assertEqual(
            persisted.meditation_timeout_seconds,
            MIN_SAFE_MEDITATION_TIMEOUT_SECONDS,
        )

    def test_existing_120_second_setting_is_migrated(self):
        events: list[tuple[str, dict[str, object]]] = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dojo_debug.json"
            write_debug_settings(
                DojoDebugSettings(meditation_timeout_seconds=120.0),
                path,
            )
            ensure_safe_meditation_timeout(
                path,
                telemetry=lambda event, fields: events.append((event, fields)),
            )
            persisted = read_debug_settings(path)

        self.assertEqual(persisted.meditation_timeout_seconds, 180.0)
        self.assertEqual(events[0][0], "DOJO_MEDITATION_TIMEOUT_MIGRATED")
        self.assertEqual(events[0][1]["reason"], "legacy_120_hp_gate")

    def test_user_value_above_safety_floor_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dojo_debug.json"
            write_debug_settings(
                DojoDebugSettings(meditation_timeout_seconds=240.0),
                path,
            )
            loaded = ensure_safe_meditation_timeout(path)

        self.assertEqual(loaded.meditation_timeout_seconds, 240.0)

    def test_runtime_bridge_prevents_stale_refresh_from_restoring_120(self):
        events: list[tuple[str, dict[str, object]]] = []

        class FakeEngine:
            def __init__(self) -> None:
                self.meditation_guard = SimpleNamespace(timeout_seconds=120.0)

            def _refresh_meditation_settings(self) -> None:
                self.meditation_guard.timeout_seconds = 120.0

        runtime = SimpleNamespace(
            ClosedLoopVisualRecoveryEngine=FakeEngine,
            _telemetry=lambda event, fields: events.append((event, fields)),
        )
        install_meditation_timeout_bridge(runtime)
        engine = runtime.ClosedLoopVisualRecoveryEngine()
        self.assertEqual(engine.meditation_guard.timeout_seconds, 180.0)

        engine._refresh_meditation_settings()
        self.assertEqual(engine.meditation_guard.timeout_seconds, 180.0)
        self.assertTrue(
            any(event == "DOJO_MEDITATION_TIMEOUT_EXTENDED" for event, _ in events)
        )

    def test_round_five_timing_does_not_timeout_at_old_120_second_boundary(self):
        guard = MeditationTransitionGuard(timeout_seconds=180.0)
        self.assertTrue(guard.request_enter(0.0))
        self.assertEqual(guard.advance(5.5), "entered")

        # Physical round 5 enabled Y close to 120 seconds. The guard must keep
        # meditating there instead of requesting an immediate timeout exit.
        self.assertFalse(guard.timed_out(120.1))
        self.assertFalse(guard.timed_out(179.9))
        self.assertTrue(guard.timed_out(180.0))

    def test_fast_chakra_hp_gate_remains_unchanged(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "pc_agent"
            / "kage_pilot"
            / "dojo_chakra_recovery_bridge_v351.py"
        ).read_text(encoding="utf-8")
        self.assertIn("hp_target = float(getattr(self, \"health_target\", 0.90))", source)
        self.assertIn("checker(hp, hp_target, \"health\")", source)
        self.assertNotIn("health_target = 0.80", source)


if __name__ == "__main__":
    unittest.main()
