from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pc_agent.kage_pilot.hunting_service import HuntingConfig, HuntingPhase, HuntingService


class FakeProcess:
    def __init__(self, lines, return_code=0):
        self.stdout = iter(lines)
        self._return_code = return_code
        self.pid = 123

    def wait(self, timeout=None):
        return self._return_code

    def poll(self):
        return self._return_code


class HuntingServiceTests(unittest.TestCase):
    def test_source_command_reuses_canonical_round_entrypoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "kage_pilot_round.py").write_text("print('stub')\n", encoding="utf-8")
            service = HuntingService(project_dir=root, python_executable="python")
            command = service.build_command(HuntingConfig())
        self.assertEqual(command[0], "python")
        self.assertTrue(command[1].endswith("kage_pilot_round.py"))
        self.assertEqual(command[2], "--hunting")
        self.assertIn("--recovery-stamina", command)

    def test_status_parser_tracks_search_combat_enemy_and_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "kage_pilot_round.py").write_text("print('stub')\n", encoding="utf-8")
            lines = [
                "HUNTING_PHASE phase=searching direction=up kills=0\n",
                "HUNTING_ENEMY clan=Inuzuka name=Sadao\n",
                "HUNTING_PHASE phase=combat direction=- kills=0\n",
                "HUNTING_VICTORY kills=1 text=Inuzuka, Sadao has been knocked unconscious\n",
                "HUNTING_PHASE phase=recovery direction=- kills=1\n",
                "HUNTING_RESOURCES hp=0.9500 stamina=- stamina_calibrated=false\n",
                "HUNTING_PHASE phase=stopped direction=- kills=1\n",
            ]
            service = HuntingService(
                project_dir=root,
                python_executable="python",
                popen_factory=lambda *args, **kwargs: FakeProcess(lines),
            )
            self.assertTrue(service.start(HuntingConfig()))
            service._thread.join(timeout=2.0)
            snapshot = service.snapshot()
        self.assertEqual(snapshot.phase, HuntingPhase.STOPPED)
        self.assertEqual(snapshot.kills, 1)
        self.assertEqual(snapshot.last_enemy, "Inuzuka, Sadao")
        self.assertAlmostEqual(snapshot.health or 0.0, 0.95)
        self.assertIsNone(snapshot.stamina)
        self.assertFalse(snapshot.stamina_calibrated)

    def test_recovery_config_never_relabels_chakra_as_stamina(self):
        config = HuntingConfig(recovery_hp_percent=90, recovery_stamina_percent=90).normalized()
        self.assertEqual(config.recovery_hp_percent, 90)
        self.assertEqual(config.recovery_stamina_percent, 90)
        args = config.to_cli_args(Path("stop.flag"))
        self.assertIn("--recovery-stamina", args)
        self.assertNotIn("--recovery-chakra", args)


if __name__ == "__main__":
    unittest.main()
