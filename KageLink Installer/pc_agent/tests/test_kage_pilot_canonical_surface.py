from __future__ import annotations

from pathlib import Path
import unittest

import kage_pilot
from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingService


class KagePilotCanonicalSurfaceTests(unittest.TestCase):
    def test_source_service_uses_single_public_command(self):
        service = DojoTrainingService(
            project_dir=Path("C:/KageLink/pc_agent"),
            python_executable="python-test",
        )
        command = service.build_command(DojoTrainingConfig(rounds=2))
        self.assertEqual(command[0], "python-test")
        self.assertEqual(Path(command[1]).name, "kage_pilot.py")
        self.assertEqual(command[2], "dojo")
        self.assertIn("--rounds", command)
        self.assertIn("2", command)

    def test_public_module_exposes_dojo_parser_and_tools(self):
        args = kage_pilot.build_parser().parse_args(["--rounds", "1"])
        self.assertEqual(args.rounds, 1)
        self.assertIn("record", kage_pilot.TOOLS_COMMANDS)
        self.assertIn("pilot-v2", kage_pilot.TOOLS_COMMANDS)

    def test_installer_specs_use_versionless_package_entries(self):
        installer = Path(__file__).resolve().parents[2] / "installer"
        dojo_spec = (installer / "KagePilotDojo.spec").read_text(encoding="utf-8")
        round_spec = (installer / "KagePilotRound.spec").read_text(encoding="utf-8")
        self.assertIn("dojo_entry.py", dojo_spec)
        self.assertNotIn("kage_pilot_loop_v03j.py", dojo_spec)
        self.assertIn("round_entry.py", round_spec)
        self.assertNotIn("kage_pilot_live_v03k_round.py", round_spec)

    def test_duplicate_public_dojo_entry_is_removed(self):
        root = Path(__file__).resolve().parents[1]
        self.assertFalse((root / "kage_pilot_dojo.py").exists())


if __name__ == "__main__":
    unittest.main()
