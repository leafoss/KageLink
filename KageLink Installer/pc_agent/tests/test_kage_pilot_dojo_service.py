from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pc_agent.kage_pilot.dojo_training import (
    DojoTrainingConfig,
    DojoTrainingPhase,
    DojoTrainingService,
)


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
        self.assertEqual(DojoTrainingConfig(rounds=0).normalized().rounds, 0)
        self.assertEqual(DojoTrainingConfig(rounds=-5).normalized().rounds, 0)

    def test_config_normalizes_thresholds_and_timeouts(self):
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

    def test_public_command_targets_validated_v03i_loop(self):
        service = DojoTrainingService(
            project_dir=Path("C:/KageLink/pc_agent"),
            python_executable="python-test",
        )
        command = service.build_command(DojoTrainingConfig(rounds=0, disable_h=True))
        self.assertEqual(command[0], "python-test")
        self.assertEqual(Path(command[1]).name, "kage_pilot_loop_v03i.py")
        self.assertIn("--rounds", command)
        self.assertIn("0", command)
        self.assertIn("--disable-h", command)
        self.assertNotIn("--interaction-attempts", command)

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
            (root / "kage_pilot_loop_v03i.py").write_text("# test\n", encoding="utf-8")
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
