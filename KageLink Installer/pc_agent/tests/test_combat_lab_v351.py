from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from pc_agent.kage_pilot.combat_lab.black_box import (
    BlackBoxRecord,
    CombatBlackBoxRecorder,
)
from pc_agent.kage_pilot.combat_lab.replay import CombatReplay
from pc_agent.kage_pilot.combat_lab.runner import run_all_scenarios, run_scenario
from pc_agent.kage_pilot.combat_lab.scenarios import frame, observation
from pc_agent.kage_pilot.combat_lab.scenarios_incremental_v351 import all_scenarios
from pc_agent.kage_pilot.combat_strategy_v351 import GridFocusV2Strategy


class CombatLabV351Tests(unittest.TestCase):
    def test_all_required_scenarios_are_present(self):
        names = {scenario.name for scenario in all_scenarios()}
        required = {
            "enemy_right",
            "enemy_left",
            "enemy_up",
            "enemy_down",
            "enemy_diagonal_up_left",
            "enemy_diagonal_up_right",
            "enemy_diagonal_down_left",
            "enemy_diagonal_down_right",
            "enemy_stationary",
            "enemy_crosses_player",
            "confirmed_enemy_d0_overlap",
            "enemy_missing_three_frames",
            "enemy_missing_ten_frames",
            "horizontal_effect_covers_player_and_enemy",
            "large_blob_three_cells",
            "false_blob_next_to_player",
            "false_blob_at_previous_enemy_cell",
            "track_id_changes_same_cell",
            "track_id_changes_impossible_cell",
            "two_candidates_same_region",
            "camera_shift",
            "player_knockback",
            "ko_ends_round",
            "new_blob_after_ko",
            "second_enemy_after_real_first_loss",
            "visible_tracker_without_combat_lock",
            "rejected_primary_valid_secondary",
            "player_only_d0",
            "false_blob_near_player_far_from_prediction",
            "same_track_short_occlusion",
            "same_track_impossible_cell_jump",
            "missing_appearance_evidence",
            "incident_20260731_lock_starvation_approximation",
        }
        self.assertTrue(required.issubset(names))

    def test_grid_focus_v2_passes_all_deterministic_scenarios(self):
        report = run_all_scenarios(strategies=("grid_focus_v2",))
        failures = [
            (result.scenario, result.failures)
            for result in report.results
            if result.outcome != "PASS"
        ]
        self.assertEqual(failures, [])

    def test_comparison_runs_same_scenarios_for_all_strategies(self):
        scenarios = all_scenarios()
        report = run_all_scenarios(scenarios)
        self.assertEqual(len(report.results), len(scenarios) * 3)
        for strategy in ("legacy_safe", "persistent_hardened", "grid_focus_v2"):
            self.assertEqual(len(report.by_strategy(strategy)), len(scenarios))

    def test_multi_cell_scenario_never_promoted_by_grid_focus(self):
        scenario = next(item for item in all_scenarios() if item.name == "large_blob_three_cells")
        result = run_scenario(scenario, "grid_focus_v2")
        self.assertEqual(result.metrics["multi_cell_blobs_promoted"], 0)
        self.assertEqual(result.outcome, "PASS")

    def test_post_ko_scenario_never_creates_target(self):
        scenario = next(item for item in all_scenarios() if item.name == "new_blob_after_ko")
        result = run_scenario(scenario, "grid_focus_v2")
        self.assertEqual(result.metrics["post_ko_targets"], 0)
        self.assertEqual(result.outcome, "PASS")

    def test_replay_is_repeatable(self):
        scenario = next(item for item in all_scenarios() if item.name == "track_id_changes_same_cell")
        replay = CombatReplay(scenario.frames)
        first = replay.assert_deterministic("grid_focus_v2", repeats=4)
        second = replay.run("grid_focus_v2")
        self.assertEqual(first, second)

    def test_incident_approximation_replay_is_repeatable(self):
        scenario = next(
            item
            for item in all_scenarios()
            if item.name == "incident_20260731_lock_starvation_approximation"
        )
        replay = CombatReplay(scenario.frames)
        first = replay.assert_deterministic("grid_focus_v2", repeats=5)
        second = replay.run("grid_focus_v2")
        self.assertEqual(first, second)
        self.assertIsNotNone(second[-1]["combat_target_id"])

    def test_replay_round_trip_preserves_decisions(self):
        scenario = next(item for item in all_scenarios() if item.name == "enemy_crosses_player")
        replay = CombatReplay(scenario.frames)
        with tempfile.TemporaryDirectory() as folder:
            path = replay.write(Path(folder) / "replay.json")
            restored = CombatReplay.read(path)
            self.assertEqual(
                replay.run("grid_focus_v2"),
                restored.run("grid_focus_v2"),
            )

    def test_report_writers_are_deterministic(self):
        report = run_all_scenarios(
            scenarios=all_scenarios()[:2],
            strategies=("grid_focus_v2",),
        )
        with tempfile.TemporaryDirectory() as folder:
            first = report.write_json(Path(folder) / "report1.json").read_text(encoding="utf-8")
            second = report.write_json(Path(folder) / "report2.json").read_text(encoding="utf-8")
            self.assertEqual(first, second)
            text = report.write_text(Path(folder) / "report.txt").read_text(encoding="utf-8")
            self.assertIn("Scenario: enemy_right", text)
            self.assertIn("outcome=PASS", text)

    def test_black_box_append_does_not_materialize_in_hot_path(self):
        strategy = GridFocusV2Strategy()
        snapshot = strategy.update(frame(0, (0, 0), observation(0, 1, (1, 0))))
        with tempfile.TemporaryDirectory() as folder:
            recorder = CombatBlackBoxRecorder(max_frames=16, root=folder)
            started = time.perf_counter()
            accepted = recorder.append(
                BlackBoxRecord(
                    timestamp=0.0,
                    frame_index=0,
                    raw_arena=np.zeros((32, 32, 3), dtype=np.uint8),
                    player_anchor=(16.0, 16.0),
                    player_cell=(0, 0),
                    grid_origin=(0.0, 0.0),
                    tile_size=32.0,
                    raw_candidates=(),
                    filtered_candidates=(),
                    tracks=(),
                    observations=(),
                    snapshot=snapshot,
                )
            )
            elapsed = time.perf_counter() - started
            self.assertTrue(accepted)
            self.assertLess(elapsed, 0.05)
            self.assertEqual(list(Path(folder).iterdir()), [])
            recorder.close()

    def test_black_box_materializes_only_when_requested(self):
        strategy = GridFocusV2Strategy()
        snapshot = strategy.update(frame(0, (0, 0), observation(0, 1, (1, 0))))
        with tempfile.TemporaryDirectory() as folder:
            recorder = CombatBlackBoxRecorder(max_frames=16, root=folder)
            recorder.append(
                BlackBoxRecord(
                    timestamp=0.0,
                    frame_index=0,
                    raw_arena=np.zeros((8, 8, 3), dtype=np.uint8),
                    player_anchor=(4.0, 4.0),
                    player_cell=(0, 0),
                    grid_origin=(0.0, 0.0),
                    tile_size=32.0,
                    raw_candidates=(),
                    filtered_candidates=(),
                    tracks=(),
                    observations=(),
                    snapshot=snapshot,
                )
            )
            self.assertTrue(recorder.request_materialization("test_failure"))
            deadline = time.time() + 3.0
            while recorder.stats().materialized < 1 and time.time() < deadline:
                time.sleep(0.02)
            recorder.close()
            packages = list(Path(folder).iterdir())
            self.assertEqual(len(packages), 1)
            self.assertTrue((packages[0] / "raw_arena_frames.npz").exists())
            self.assertTrue((packages[0] / "replay.json").exists())


if __name__ == "__main__":
    unittest.main()
