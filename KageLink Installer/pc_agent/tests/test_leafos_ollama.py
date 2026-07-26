from __future__ import annotations

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from pc_agent.leafos_ollama import OllamaManager


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class OllamaManagerTests(unittest.TestCase):
    @patch("pc_agent.leafos_ollama.shutil.which", return_value="C:/Ollama/ollama.exe")
    @patch("pc_agent.leafos_ollama.urllib.request.urlopen")
    def test_status_reports_server_and_model(self, urlopen, _which) -> None:
        urlopen.return_value = _Response({"models": [{"name": "qwen3:14b"}]})
        status = OllamaManager(model="qwen3:14b").status()
        self.assertTrue(status.server_online)
        self.assertTrue(status.model_available)
        self.assertEqual(status.cli_path, "C:/Ollama/ollama.exe")

    @patch("pc_agent.leafos_ollama.shutil.which", return_value=None)
    @patch("pc_agent.leafos_ollama.urllib.request.urlopen", side_effect=OSError("offline"))
    def test_status_reports_missing_installation(self, _urlopen, _which) -> None:
        status = OllamaManager().status()
        self.assertFalse(status.server_online)
        self.assertFalse(status.model_available)
        self.assertIsNone(status.cli_path)

    @patch("pc_agent.leafos_ollama.OllamaManager.status")
    @patch("pc_agent.leafos_ollama.subprocess.Popen")
    def test_pull_model_uses_ollama_cli_without_powershell(self, popen, status_method) -> None:
        status_method.side_effect = [
            type("S", (), {"server_online": True, "cli_path": "ollama", "model_available": False, "models": []})(),
            type("S", (), {"server_online": True, "cli_path": "ollama", "model_available": True, "models": ["qwen3:14b"]})(),
        ]
        process = MagicMock()
        process.stdout = io.StringIO("pulling manifest\nsuccess\n")
        process.wait.return_value = 0
        popen.return_value = process

        final = OllamaManager(model="qwen3:14b").pull_model()

        self.assertTrue(final.model_available)
        command = popen.call_args.args[0]
        self.assertEqual(command, ["ollama", "pull", "qwen3:14b"])
        self.assertNotIn("powershell", " ".join(command).lower())


if __name__ == "__main__":
    unittest.main()
