from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from pc_agent.kage_pilot import combat_strategy_runtime_v351 as strategy_runtime


class _Base:
    def __init__(self, *args, **kwargs):
        pass

    def reset(self):
        pass


class CombatRuntimeProvenanceV351Tests(unittest.TestCase):
    def setUp(self) -> None:
        strategy_runtime._REGISTRY = strategy_runtime._RuntimeRegistry()
        strategy_runtime._CURRENT_COMMANDS.clear()

    def _runtime_pair(self):
        live = ModuleType("kage_pilot_live_v03")
        live.PersistentBackgroundWaterAwareEntityTracker = type("BaseTracker", (_Base,), {})
        live.ParticleSafeGridTargetObserver = type("BaseObserver", (_Base,), {})
        live.ShadowCombatDecisionEngine = type("BaseEngine", (_Base,), {})
        live.LiveCombatControlPlanner = type("BasePlanner", (_Base,), {})
        live.ChatVictoryWatcher = type("BaseWatcher", (_Base,), {})
        runtime = SimpleNamespace(
            _telemetry=lambda event, fields: None,
            PersistentBackgroundWaterAwareEntityTracker=live.PersistentBackgroundWaterAwareEntityTracker,
            ParticleSafeGridTargetObserver=live.ParticleSafeGridTargetObserver,
            ShadowCombatDecisionEngine=live.ShadowCombatDecisionEngine,
            LiveCombatControlPlanner=live.LiveCombatControlPlanner,
            ChatVictoryWatcher=live.ChatVictoryWatcher,
        )
        return live, runtime

    def test_canonical_install_records_expected_concrete_classes(self):
        live, runtime = self._runtime_pair()
        with patch.dict(sys.modules, {"kage_pilot_live_v03": live}):
            installed = strategy_runtime.install_combat_strategy_runtime(
                runtime,
                strategy_name="grid_focus_v2",
            )
            fields = strategy_runtime.runtime_provenance(runtime)

        self.assertEqual(installed.strategy_name, "grid_focus_v2")
        self.assertEqual(fields["strategy"], "grid_focus_v2")
        self.assertEqual(fields["observer_class"], "CanonicalCombatObserver")
        self.assertIn("CanonicalCombatTracker", fields["tracker_class"])
        self.assertIn("CanonicalCombatDecisionEngine", fields["engine_class"])
        self.assertIn("CanonicalCombatPlanner", fields["planner_class"])
        self.assertIn("GridFocusV2SpatialStrategy", fields["memory_class"])

    def test_install_is_idempotent_and_does_not_stack_classes(self):
        live, runtime = self._runtime_pair()
        with patch.dict(sys.modules, {"kage_pilot_live_v03": live}):
            first = strategy_runtime.install_combat_strategy_runtime(runtime)
            second = strategy_runtime.install_combat_strategy_runtime(runtime)
        self.assertIs(first, second)
        self.assertIs(first.observer_class, second.observer_class)

    def test_provenance_event_is_emitted_once(self):
        live, runtime = self._runtime_pair()
        events = []
        runtime._telemetry = lambda event, fields: events.append((event, fields))
        with patch.dict(sys.modules, {"kage_pilot_live_v03": live}):
            strategy_runtime.install_combat_strategy_runtime(runtime)
            strategy_runtime.emit_runtime_provenance(runtime)
            strategy_runtime.emit_runtime_provenance(runtime)
        emitted = [event for event, _ in events if event == "DOJO_COMBAT_RUNTIME_PROVENANCE"]
        self.assertEqual(emitted, ["DOJO_COMBAT_RUNTIME_PROVENANCE"])

    def test_canonical_round_entry_uses_only_one_combat_installer(self):
        root = Path(__file__).resolve().parents[1]
        content = (root / "kage_pilot_visual_return.py").read_text(encoding="utf-8")
        self.assertIn("install_combat_strategy_runtime(runtime)", content)
        self.assertNotIn("install_combat_target_bridge(runtime)", content)
        self.assertNotIn("install_combat_runtime_hardening(runtime)", content)

    def test_provenance_is_emitted_after_recorder_installation(self):
        root = Path(__file__).resolve().parents[1]
        content = (root / "kage_pilot_visual_return.py").read_text(encoding="utf-8")
        recorder_call = content.index("install_round_video_performance_guard(recorder")
        provenance_call = content.index("emit_runtime_provenance(runtime)")
        self.assertGreater(provenance_call, recorder_call)


if __name__ == "__main__":
    unittest.main()
