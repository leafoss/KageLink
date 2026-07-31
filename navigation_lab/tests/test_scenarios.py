from __future__ import annotations

import unittest

from navigation_lab.simulator import SCENARIOS, SimulatorEngine


class ScenarioTests(unittest.TestCase):
    def test_all_required_scenarios_arrive_or_fail_safely(self) -> None:
        required = [scenario_id for scenario_id in sorted(SCENARIOS) if scenario_id[:2].isdigit()]
        self.assertEqual(len(required), 16)
        failures: list[str] = []
        for scenario_id in required:
            with self.subTest(scenario=scenario_id):
                result = SimulatorEngine(SCENARIOS[scenario_id]).run()
                if result.outcome not in {"arrived", "paused"}:
                    failures.append(f"{scenario_id}:{result.outcome}")
                self.assertLessEqual(result.steps, SCENARIOS[scenario_id].max_steps)
        self.assertEqual(failures, [])

    def test_dynamic_block_causes_replan(self) -> None:
        result = SimulatorEngine(SCENARIOS["12_route_replanning"]).run()
        self.assertEqual(result.outcome, "arrived")
        self.assertGreaterEqual(result.replans, 2)

    def test_landmark_restores_confidence(self) -> None:
        result = SimulatorEngine(SCENARIOS["05_landmark_relocalization"]).run()
        sources = [snapshot.pose.source for snapshot in result.snapshots]
        self.assertIn("landmark_relocalization", sources)


if __name__ == "__main__":
    unittest.main()
