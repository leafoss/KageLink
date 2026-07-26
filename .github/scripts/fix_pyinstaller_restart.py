from pathlib import Path

root = Path.cwd()
launcher = root / "KageLink Installer" / "pc_agent" / "unified_launcher.py"
test_file = root / "KageLink Installer" / "pc_agent" / "tests" / "test_unified_launcher_shutdown.py"

text = launcher.read_text(encoding="utf-8")
old = "        executable = _self_command(); legacy.KageLinkAgentUI.shutdown(self, prompt=False); subprocess.Popen(executable, cwd=PROJECT_DIR); self.root.destroy()"
new = """        executable = _self_command()
        legacy.KageLinkAgentUI.shutdown(self, prompt=False)
        restart_env = os.environ.copy()
        if getattr(sys, \"frozen\", False):
            restart_env[\"PYINSTALLER_RESET_ENVIRONMENT\"] = \"1\"
        subprocess.Popen(executable, cwd=PROJECT_DIR, env=restart_env)
        self.root.destroy()"""
if old not in text:
    raise RuntimeError("restart line not found")
launcher.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

text = test_file.read_text(encoding="utf-8")
marker = "    def test_shutdown_failure_does_not_claim_finalization(self) -> None:\n"
block = '''    @patch.object(unified_launcher.subprocess, "Popen")
    def test_frozen_restart_resets_pyinstaller_environment(self, popen) -> None:
        ui = self._ui()
        ui._finalize_for_shutdown = MagicMock(return_value=True)

        with patch.object(unified_launcher.sys, "frozen", True, create=True), patch.object(
            unified_launcher.legacy.KageLinkAgentUI,
            "shutdown",
        ):
            ui._restart_application()

        popen.assert_called_once()
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [unified_launcher.sys.executable])
        self.assertEqual(kwargs["cwd"], unified_launcher.PROJECT_DIR)
        self.assertEqual(kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        ui.root.destroy.assert_called_once()

'''
if "test_frozen_restart_resets_pyinstaller_environment" not in text:
    if marker not in text:
        raise RuntimeError("test insertion marker not found")
    text = text.replace(marker, block + marker, 1)
test_file.write_text(text, encoding="utf-8", newline="\n")
print("restart fix applied")
