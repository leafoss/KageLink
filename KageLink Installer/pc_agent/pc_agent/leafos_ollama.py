from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(slots=True)
class OllamaStatus:
    cli_path: str | None
    server_online: bool
    model_available: bool
    models: list[str]


class OllamaManager:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:14b",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    @staticmethod
    def _creationflags() -> int:
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0

    def cli_path(self) -> str | None:
        discovered = shutil.which("ollama")
        if discovered:
            return discovered

        # winget can update the user PATH only for future processes. Check the
        # standard Windows install locations so an in-app installation can be
        # used immediately without asking the user to restart KageLink.
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "ollama.exe",
            Path(os.environ.get("ProgramFiles", "")) / "Ollama" / "ollama.exe",
        ]
        for candidate in candidates:
            if str(candidate) and candidate.is_file():
                return str(candidate)
        return None

    def _models_from_server(self) -> list[str]:
        request = urllib.request.Request(
            f"{self.base_url}/api/tags",
            headers={"User-Agent": "KageLink/3.4.1"},
        )
        with urllib.request.urlopen(request, timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        values = payload.get("models", []) if isinstance(payload, dict) else []
        result: list[str] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                result.append(name)
        return result

    def status(self) -> OllamaStatus:
        cli = self.cli_path()
        try:
            models = self._models_from_server()
            online = True
        except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            models = []
            online = False
        wanted = self.model.lower()
        available = any(
            name.lower() == wanted or name.lower().split(":latest")[0] == wanted
            for name in models
        )
        return OllamaStatus(
            cli_path=cli,
            server_online=online,
            model_available=available,
            models=models,
        )

    def start_server(self, *, timeout_seconds: float = 12.0) -> OllamaStatus:
        current = self.status()
        if current.server_online:
            return current
        if not current.cli_path:
            raise RuntimeError("OLLAMA_NOT_INSTALLED")

        subprocess.Popen(
            [current.cli_path, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=self._creationflags(),
        )
        deadline = time.monotonic() + max(2.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            status = self.status()
            if status.server_online:
                return status
            time.sleep(0.4)
        raise RuntimeError("OLLAMA_START_TIMEOUT")

    def install_with_winget(self, *, timeout_seconds: float = 300.0) -> OllamaStatus:
        winget = shutil.which("winget")
        if not winget:
            raise RuntimeError("WINGET_NOT_AVAILABLE")
        result = subprocess.run(
            [
                winget,
                "install",
                "--id",
                "Ollama.Ollama",
                "-e",
                "--silent",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ],
            capture_output=True,
            text=True,
            timeout=max(30.0, float(timeout_seconds)),
            creationflags=self._creationflags(),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"OLLAMA_INSTALL_FAILED: {detail[-1200:]}")
        return self.start_server(timeout_seconds=20.0)

    def pull_model(
        self,
        *,
        on_output: Callable[[str], None] | None = None,
        timeout_seconds: float = 1800.0,
    ) -> OllamaStatus:
        status = self.start_server()
        cli = status.cli_path or self.cli_path()
        if not cli:
            raise RuntimeError("OLLAMA_NOT_INSTALLED")

        process = subprocess.Popen(
            [cli, "pull", self.model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=self._creationflags(),
        )
        started = time.monotonic()
        assert process.stdout is not None
        for line in process.stdout:
            if on_output is not None:
                on_output(line.rstrip())
            if time.monotonic() - started > timeout_seconds:
                process.kill()
                raise RuntimeError("OLLAMA_PULL_TIMEOUT")
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"OLLAMA_PULL_FAILED: exit={return_code}")

        final = self.status()
        if not final.model_available:
            raise RuntimeError("OLLAMA_MODEL_NOT_AVAILABLE_AFTER_PULL")
        return final
