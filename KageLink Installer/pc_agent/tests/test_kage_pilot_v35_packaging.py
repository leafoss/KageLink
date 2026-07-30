from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import kage_pilot_loop
from pc_agent.dojo_api import DojoStartRequest, dojo_status_payload, install_game_control_interlock
from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingService


class _GameRuntimeStub:
    def __init__(self) -> None:
        self.activated = 0
        self.applied = 0
        self.clicked = 0

    def activate_control(self):
        self.activated += 1
        return True

    def apply_keys(self, pressed):
        self.applied += 1
        return list(pressed)

    def click_game_center(self):
        self.clicked += 1
        return True


class _FrozenProcessStub:
    def __init__(self, lines=(), return_code=0, pid=4321) -> None:
        self.stdout = iter(lines)
        self.return_code = int(return_code)
        self.pid = int(pid)
        self.killed = False

    def wait(self, timeout=None):
        del timeout
        return self.return_code

    def poll(self):
        return None

    def kill(self):
        self.killed = True


class _ThreadStub:
    def __init__(self) -> None:
        self.joined = False

    def is_alive(self):
        return True

    def join(self, timeout=None):
        del timeout
        self.joined = True


class KagePilotV35PackagingTests(unittest.TestCase):
    def test_frozen_service_uses_sibling_dojo_helper(self):
        service = DojoTrainingService(project_dir=Path("C:/source/pc_agent"))
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(
            sys,
            "executable",
            "C:/Program Files/KageLink/KageLink.exe",
        ):
            command = service.build_command(DojoTrainingConfig(rounds=7))
        self.assertEqual(command[0], str(Path("C:/Program Files/KageLink/KagePilotDojo.exe")))
        self.assertIn("--rounds", command)
        self.assertIn("7", command)
        self.assertNotIn("kage_pilot_loop_v03j.py", " ".join(command))

    def test_source_service_uses_canonical_python_runtime(self):
        service = DojoTrainingService(
            project_dir=Path("C:/source/pc_agent"),
            python_executable="C:/Python/python.exe",
        )
        with mock.patch.object(sys, "frozen", False, create=True):
            command = service.build_command(DojoTrainingConfig(rounds=2))
        self.assertEqual(command[0], "C:/Python/python.exe")
        self.assertTrue(command[1].endswith("kage_pilot_loop.py"))
        self.assertNotIn("v03", Path(command[1]).name)

    def test_frozen_service_hides_helper_console(self):
        captured = {}
        process = _FrozenProcessStub()

        def popen_factory(command, **kwargs):
            captured["command"] = command
            captured.update(kwargs)
            return process

        service = DojoTrainingService(
            project_dir=Path("C:/source/pc_agent"),
            popen_factory=popen_factory,
        )
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(
            sys,
            "executable",
            "C:/Program Files/KageLink/KageLink.exe",
        ), mock.patch.object(
            __import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0x200, create=True
        ), mock.patch.object(
            __import__("subprocess"), "CREATE_NO_WINDOW", 0x8000000, create=True
        ):
            service._run(DojoTrainingConfig(rounds=1))

        self.assertEqual(
            captured["command"][0],
            str(Path("C:/Program Files/KageLink/KagePilotDojo.exe")),
        )
        self.assertEqual(captured["cwd"], str(Path("C:/Program Files/KageLink")))
        self.assertEqual(captured["creationflags"], 0x8000200)

    def test_frozen_stop_kills_complete_helper_tree(self):
        process = _FrozenProcessStub(pid=9876)
        thread = _ThreadStub()
        service = DojoTrainingService(project_dir=Path("C:/source/pc_agent"))
        service._process = process
        service._thread = thread

        with mock.patch.object(sys, "frozen", True, create=True), mock.patch(
            "pc_agent.kage_pilot.dojo_training_service.os.name", "nt"
        ), mock.patch(
            "pc_agent.kage_pilot.dojo_training_service.subprocess.run"
        ) as run, mock.patch.object(
            __import__("subprocess"), "CREATE_NO_WINDOW", 0x8000000, create=True
        ):
            self.assertTrue(service.stop(timeout=3.0))

        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "9876", "/T", "/F"])
        self.assertTrue(thread.joined)

    def test_frozen_loop_uses_sibling_round_helper(self):
        args = Namespace(
            log_dir=Path("logs"),
            combat_seconds=120.0,
            post_combat_timeout=240.0,
            round_startup_delay=1.0,
            chat_poll_seconds=0.15,
            recovery_hp_percent=90.0,
            recovery_chakra_percent=50.0,
            leader_threshold=0.88,
            disable_h=False,
        )
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(
            sys,
            "executable",
            "C:/Program Files/KageLink/KagePilotDojo.exe",
        ):
            command, cwd = kage_pilot_loop._round_command(args, round_number=3)
        self.assertEqual(command[0], str(Path("C:/Program Files/KageLink/KagePilotRound.exe")))
        self.assertEqual(cwd, Path("C:/Program Files/KageLink"))
        self.assertIn(str(Path("logs/round_003.jsonl")), command)

    def test_source_loop_uses_canonical_round_script(self):
        args = Namespace(
            log_dir=Path("logs"),
            combat_seconds=120.0,
            post_combat_timeout=240.0,
            round_startup_delay=1.0,
            chat_poll_seconds=0.15,
            recovery_hp_percent=90.0,
            recovery_chakra_percent=50.0,
            leader_threshold=0.88,
            disable_h=False,
        )
        with mock.patch.object(sys, "frozen", False, create=True):
            command, _ = kage_pilot_loop._round_command(args, round_number=1)
        self.assertEqual(Path(command[1]).name, "kage_pilot_round.py")

    def test_dojo_request_preserves_validated_safety_floors(self):
        config = DojoStartRequest(
            rounds=10,
            recovery_hp_percent=90,
            recovery_chakra_percent=50,
        ).to_config()
        self.assertEqual(config.rounds, 10)
        self.assertEqual(config.recovery_hp_percent, 90.0)
        self.assertEqual(config.recovery_chakra_percent, 50.0)

    def test_manual_game_control_is_blocked_while_dojo_runs(self):
        service = mock.Mock()
        service.is_running = True
        runtime = _GameRuntimeStub()
        install_game_control_interlock(service, runtime)
        with self.assertRaisesRegex(RuntimeError, "DOJO_TRAINING_ACTIVE"):
            runtime.activate_control()
        with self.assertRaisesRegex(RuntimeError, "DOJO_TRAINING_ACTIVE"):
            runtime.apply_keys(["r"])
        with self.assertRaisesRegex(RuntimeError, "DOJO_TRAINING_ACTIVE"):
            runtime.click_game_center()

        service.is_running = False
        self.assertTrue(runtime.activate_control())
        self.assertEqual(runtime.apply_keys(["r"]), ["r"])
        self.assertTrue(runtime.click_game_center())

    def test_status_payload_exposes_installation_and_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "kage_pilot_loop.py").write_text("# test", encoding="utf-8")
            service = DojoTrainingService(project_dir=project)
            payload = dojo_status_payload(service)
        self.assertTrue(payload["available"])
        self.assertFalse(payload["running"])
        self.assertEqual(payload["phase"], "idle")
        self.assertIn("defaults", payload)


if __name__ == "__main__":
    unittest.main()
