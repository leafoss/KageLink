from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import kage_pilot_dojo
import kage_pilot_loop_v03g as loop_v03g
from pc_agent.kage_pilot.dojo_training import DojoTrainingConfig


class FakeRoundProcess:
    def __init__(self) -> None:
        self.stdout = iter(
            [
                "VICTORY_CHAT / VITORIA_CHAT: Jounin has been Knocked-Out\n",
                "Live stopped / Controle encerrado: result=ready\n",
            ]
        )

    def wait(self):
        return 0


class KagePilotDojoConfigTests(unittest.TestCase):
    def test_repository_default_config_is_loadable_and_matches_safe_baseline(self):
        value = DojoTrainingConfig.load_json(kage_pilot_dojo.DEFAULT_CONFIG_PATH)
        self.assertEqual(value.rounds, 1)
        self.assertEqual(value.dialog_delay, 5.0)
        self.assertEqual(value.spawn_delay, 1.0)
        self.assertEqual(value.round_startup_delay, 0.15)
        self.assertEqual(value.recovery_hp_percent, 90.0)
        self.assertEqual(value.recovery_chakra_percent, 40.0)
        self.assertFalse(value.disable_h)

    def test_cli_overrides_json_without_mutating_other_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dojo.json"
            base = DojoTrainingConfig(
                rounds=2,
                dialog_delay=5,
                spawn_delay=5,
                recovery_hp_percent=90,
                recovery_chakra_percent=40,
            )
            path.write_text(
                json.dumps(base.to_public_dict(), ensure_ascii=False),
                encoding="utf-8",
            )
            args = kage_pilot_dojo.build_parser().parse_args(
                [
                    "--config",
                    str(path),
                    "--dialog-delay",
                    "3",
                    "--recovery-hp-percent",
                    "95",
                    "--disable-h",
                ]
            )
            value = kage_pilot_dojo.resolve_config(args)

        self.assertEqual(value.rounds, 2)
        self.assertEqual(value.dialog_delay, 3)
        self.assertEqual(value.spawn_delay, 5)
        self.assertEqual(value.recovery_hp_percent, 95)
        self.assertEqual(value.recovery_chakra_percent, 40)
        self.assertTrue(value.disable_h)

    def test_loop_forwards_percentages_as_runtime_fractions_and_uses_selected_script(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                combat_seconds=120,
                post_combat_timeout=240,
                round_startup_delay=1,
                chat_poll_seconds=0.15,
                recovery_hp_percent=95,
                recovery_chakra_percent=60,
                leader_threshold=0.88,
                log_dir=Path(directory),
                disable_h=False,
            )
            captured = {}

            def fake_popen(command, **kwargs):
                captured["command"] = list(command)
                captured["kwargs"] = kwargs
                return FakeRoundProcess()

            with patch.object(loop_v03g, "ROUND_SCRIPT_NAME", "kage_pilot_live_v03j_round.py"):
                with patch.object(loop_v03g.subprocess, "Popen", side_effect=fake_popen):
                    self.assertTrue(loop_v03g._run_round(args, round_number=1))

        command = captured["command"]
        self.assertEqual(Path(command[1]).name, "kage_pilot_live_v03j_round.py")
        hp_index = command.index("--recovery-hp") + 1
        chakra_index = command.index("--recovery-chakra") + 1
        self.assertEqual(command[hp_index], "0.95")
        self.assertEqual(command[chakra_index], "0.6")

    def test_direct_loop_accepts_40_and_rejects_values_below_floor(self):
        hp, chakra = loop_v03g._validate_recovery_targets(
            SimpleNamespace(recovery_hp_percent=90, recovery_chakra_percent=40)
        )
        self.assertEqual((hp, chakra), (90.0, 40.0))
        with self.assertRaisesRegex(ValueError, "RECOVERY_CHAKRA_PERCENT_OUT_OF_RANGE"):
            loop_v03g._validate_recovery_targets(
                SimpleNamespace(recovery_hp_percent=90, recovery_chakra_percent=39.9)
            )

    def test_direct_loop_rejects_hp_below_safety_floor(self):
        args = SimpleNamespace(recovery_hp_percent=80, recovery_chakra_percent=40)
        with self.assertRaisesRegex(ValueError, "RECOVERY_HP_PERCENT_OUT_OF_RANGE"):
            loop_v03g._validate_recovery_targets(args)


if __name__ == "__main__":
    unittest.main()
