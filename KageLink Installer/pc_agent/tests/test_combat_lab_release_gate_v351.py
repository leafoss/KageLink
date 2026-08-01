from __future__ import annotations

import json
import unittest

from pc_agent.kage_pilot.combat_lab.replay import CombatReplay
from pc_agent.kage_pilot.combat_lab.runner import run_all_scenarios
from pc_agent.kage_pilot.combat_lab.scenarios_incremental_v351 import all_scenarios
from pc_agent.kage_pilot.combat_strategy_v351 import load_combat_strategy_config


class CombatLabReleaseGateV351Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = all_scenarios()
        cls.report = run_all_scenarios(cls.scenarios)
        print(
            "COMBAT_LAB_REPORT "
            + json.dumps(cls.report.summary(), sort_keys=True, separators=(",", ":"))
        )

    def test_01_grid_focus_v2_passes_every_synthetic_scenario(self):
        failures = [
            (result.scenario, result.failures)
            for result in self.report.by_strategy("grid_focus_v2")
            if result.outcome != "PASS"
        ]
        self.assertEqual(failures, [])

    def test_02_grid_focus_v2_has_zero_false_rebinds(self):
        total = sum(
            int(result.metrics.get("false_rebinds", 0) or 0)
            for result in self.report.by_strategy("grid_focus_v2")
        )
        self.assertEqual(total, 0)

    def test_03_grid_focus_v2_never_promotes_multi_cell_blobs(self):
        total = sum(
            int(result.metrics.get("multi_cell_blobs_promoted", 0) or 0)
            for result in self.report.by_strategy("grid_focus_v2")
        )
        self.assertEqual(total, 0)

    def test_04_grid_focus_v2_has_no_post_ko_targets(self):
        total = sum(
            int(result.metrics.get("post_ko_targets", 0) or 0)
            for result in self.report.by_strategy("grid_focus_v2")
        )
        self.assertEqual(total, 0)

    def test_05_melee_lock_never_survives_without_clean_visual(self):
        total = sum(
            float(result.metrics.get("time_in_melee_lock_without_clean_visual", 0.0) or 0.0)
            for result in self.report.by_strategy("grid_focus_v2")
        )
        self.assertEqual(total, 0.0)

    def test_06_prediction_never_jumps_multiple_cells_within_one_target(self):
        total = sum(
            int(result.metrics.get("prediction_cell_jumps", 0) or 0)
            for result in self.report.by_strategy("grid_focus_v2")
        )
        self.assertEqual(total, 0)

    def test_07_replay_is_deterministic_for_every_scenario(self):
        for scenario in self.scenarios:
            with self.subTest(scenario=scenario.name):
                CombatReplay(scenario.frames).assert_deterministic(
                    "grid_focus_v2",
                    repeats=3,
                )

    def test_08_default_remains_persistent_hardened_until_physical_approval(self):
        self.assertEqual(load_combat_strategy_config().strategy, "persistent_hardened")

    def test_09_all_three_strategies_remain_comparable(self):
        expected = len(self.scenarios)
        self.assertEqual(len(self.report.by_strategy("legacy_safe")), expected)
        self.assertEqual(len(self.report.by_strategy("persistent_hardened")), expected)
        self.assertEqual(len(self.report.by_strategy("grid_focus_v2")), expected)

    def test_10_incident_approximation_is_part_of_the_gate(self):
        names = {scenario.name for scenario in self.scenarios}
        self.assertIn("incident_20260731_lock_starvation_approximation", names)
        self.assertIn("visible_tracker_without_combat_lock", names)
        self.assertIn("player_only_d0", names)


if __name__ == "__main__":
    unittest.main()
