from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pc_agent.kage_pilot.dojo_training import (
    DojoTrainingConfig,
    DojoTrainingPhase,
)
from pc_agent.kage_pilot.dojo_training_service import DojoTrainingService


class FakeProcess:
    def __init__(self, lines, return_code=0) -> None:
        self.stdout = iter(lines)
        self.return_code = int(return_code)
        self.signals = []
        self.terminated = False
        self.killed = False

    def wait(self, timeout=None):
        del timeout
        return self.return_code

    def poll(self):
        return None

    def send_signal(self, value):
        self.signals.append(value)

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class KagePilotDojoServiceTests(unittest.TestCase):
    def test_config_has_safe_one_round_default_and_continuous_zero(self):
        self.assertEqual(DojoTrainingConfig().normalized().rounds, 1)
        self.assertEqual(DojoTrainingConfig().normalized().recovery_chakra_percent, 40.0)
        self.assertEqual(DojoTrainingConfig(rounds=0).normalized().rounds, 0)
        self.assertEqual(DojoTrainingConfig(rounds=-5).normalized().rounds, 0)

    def test_config_normalizes_general_thresholds_and_timeouts(self):
        value = DojoTrainingConfig(
            combat_seconds=0,
            post_combat_timeout=0,
            dialog_timeout=0,
            leader_threshold=5.0,
            chat_poll_seconds=0,
        ).normalized()
        self.assertEqual(value.combat_seconds, 5.0)
        self.assertEqual(value.post_combat_timeout, 15.0)
        self.assertEqual(value.dialog_timeout, 0.5)
        self.assertEqual(value.leader_threshold, 0.999)
        self.assertEqual(value.chat_poll_seconds, 0.10)

    def test_recovery_thresholds_cannot_weaken_validated_safety_floor(self):
        with self.assertRaisesRegex(ValueError, "RECOVERY_HP_PERCENT_OUT_OF_RANGE"):
            DojoTrainingConfig(recovery_hp_percent=89).normalized()
        with self.assertRaisesRegex(ValueError, "RECOVERY_CHAKRA_PERCENT_OUT_OF_RANGE"):
            DojoTrainingConfig(recovery_chakra_percent=39).normalized()
        with self.assertRaisesRegex(ValueError, "RECOVERY_HP_PERCENT_OUT_OF_RANGE"):
            DojoTrainingConfig(recovery_hp_percent=101).normalized()
        self.assertEqual(
            DojoTrainingConfig(recovery_chakra_percent=40).normalized().recovery_chakra_percent,
            40.0,
        )

    def test_json_contract_loads_human_editable_timing_and_recovery(self):
        payload = {
            "schema_version": 1,
            "rounds": 3,
            "timing": {
                "after_trainer_click_seconds": 4,
                "after_dialog_ok_seconds": 6,
                "combat_timeout_seconds": 150,
                "post_combat_timeout_seconds": 300,
                "trainer_search_timeout_seconds": 80,
                "dialog_find_timeout_seconds": 7,
                "round_startup_delay_seconds": 2,
                "chat_poll_seconds": 0.2,
            },
            "recovery": {"hp_percent": 95, "chakra_percent": 60},
            "combat": {"h_enabled": False},
            "detection": {"leader_threshold": 0.9},
            "logging": {"directory": "logs-test"},
        }
        value = DojoTrainingConfig.from_dict(payload)
        self.assertEqual(value.rounds, 3)
        self.assertEqual(value.dialog_delay, 4)
        self.assertEqual(value.spawn_delay, 6)
        self.assertEqual(value.recovery_hp_percent, 95)
        self.assertEqual(value.recovery_chakra_percent, 60)
        self.assertTrue(value.disable_h)
        self.assertEqual(value.log_dir, Path("logs-test"))
        self.assertEqual(value.to_public_dict()["recovery"]["hp_percent"], 95)

    def test_json_contract_requires_real_boolean_for_h_enabled(self):
        with self.assertRaisesRegex(ValueError, "DOJO_CONFIG_EXPECTED_BOOLEAN"):
            DojoTrainingConfig.from_dict(
                {
                    "recovery": {"hp_percent": 90, "chakra_percent": 40},
                    "combat": {"h_enabled": "false"},
                }
            )

    def test_json_contract_rejects_unknown_keys(self):
        with self.assertRaisesRegex(ValueError, "DOJO_CONFIG_UNKNOWN_KEYS:timing"):
            DojoTrainingConfig.from_dict(
                {
                    "timing": {"unknown_wait": 5},
                    "recovery": {"hp_percent": 90, "chakra_percent": 40},
                }
            )

    def test_public_command_targets_canonical_loop_and_forwards_recovery(self):
        service = DojoTrainingService(
            project_dir=Path("C:/KageLink/pc_agent"),
            python_executable="python-test",
        )
        command = service.build_command(
            DojoTrainingConfig(
                rounds=0,
                recovery_hp_percent=95,
                recovery_chakra_percent=60,
                disable_h=True,
            )
        )
        self.assertEqual(command[0], "python-test")
        self.assertEqual(Path(command[1]).name, "kage_pilot_loop.py")
        self.assertIn("--rounds", command)
        self.assertIn("0", command)
        self.assertIn("--recovery-hp-percent", command)
        self.assertIn("95.0", command)
        self.assertIn("--recovery-chakra-percent", command)
        self.assertIn("60.0", command)
        self.assertIn("--disable-h", command)
        self.assertNotIn("--interaction-attempts", command)

    def test_load_json_reports_invalid_json_with_location(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dojo.json"
            path.write_text('{"timing": ', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DOJO_CONFIG_INVALID_JSON"):
                DojoTrainingConfig.load_json(path)

    def test_phase_parser_exposes_app_friendly_lifecycle(self):
        phase = DojoTrainingPhase.STARTING
        phase = DojoTrainingService.phase_for_line(
            "ROUND 1: SEARCH AND REQUEST TAIJUTSU DOJO SPAR", phase
        )
        self.assertEqual(phase, DojoTrainingPhase.REQUESTING)
        phase = DojoTrainingService.phase_for_line("ROUND 1: START COMBAT RUNTIME", phase)
        self.assertEqual(phase, DojoTrainingPhase.COMBAT)
        phase = DojoTrainingService.phase_for_line(
            "VICTORY_CHAT / VITORIA_CHAT: Jounin has been Knocked-Out", phase
        )
        self.assertEqual(phase, DojoTrainingPhase.VICTORY)
        phase = DojoTrainingService.phase_for_line(
            "POST_COMBAT / POS-COMBATE: SEEK_DOJO_LEADER", phase
        )
        self.assertEqual(phase, DojoTrainingPhase.RECOVERY)
        phase = DojoTrainingService.phase_for_line("ROUND 1: COMPLETE / CONCLUIDA", phase)
        self.assertEqual(phase, DojoTrainingPhase.READY)
        phase = DojoTrainingService.phase_for_line("DOJO_LOOP_STOPPED completed=1", phase)
        self.assertEqual(phase, DojoTrainingPhase.STOPPED)

    def test_service_tracks_a_complete_validated_round_without_importing_runtime(self):
        lines = [
            "ROUND 1: SEARCH AND REQUEST TAIJUTSU DOJO SPAR\n",
            "ROUND 1: START COMBAT RUNTIME / INICIAR COMBATE\n",
            "VICTORY_CHAT / VITORIA_CHAT: Jounin has been Knocked-Out\n",
            "POST_COMBAT / POS-COMBATE: SEEK_DOJO_LEADER\n",
            "ROUND 1: COMPLETE / CONCLUIDA\n",
            "DOJO_LOOP_STOPPED completed=1 / LOOP_ENCERRADO concluidas=1\n",
        ]
        fake = FakeProcess(lines)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "kage_pilot_loop.py").write_text("# test\n", encoding="utf-8")
            service = DojoTrainingService(
                project_dir=root,
                python_executable="python-test",
                popen_factory=lambda *args, **kwargs: fake,
            )
            emitted = []
            self.assertTrue(service.start(DojoTrainingConfig(), on_output=emitted.append))
            snapshot = service.wait(timeout=2.0)

        self.assertFalse(snapshot.running)
        self.assertEqual(snapshot.phase, DojoTrainingPhase.STOPPED)
        self.assertEqual(snapshot.current_round, 1)
        self.assertEqual(snapshot.completed_rounds, 1)
        self.assertEqual(snapshot.return_code, 0)
        self.assertEqual(len(emitted), len(lines))

    def test_error_output_is_not_reported_as_success(self):
        service = DojoTrainingService(project_dir=Path("C:/KageLink/pc_agent"))
        service._consume_output_line("ROUND 1: DOJO_REQUEST_FAILED: DOJO_DIALOG_NOT_FOUND")
        snapshot = service.snapshot()
        self.assertEqual(snapshot.phase, DojoTrainingPhase.ERROR)
        self.assertIn("DOJO_REQUEST_FAILED", snapshot.last_error)


if __name__ == "__main__":
    unittest.main()
