from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from typing import Callable


class HuntingPhase(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    SEARCHING = "searching"
    ACQUIRING = "acquiring"
    COMBAT = "combat"
    RECOVERY = "recovery"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class HuntingConfig:
    walk_seconds: float = 1.40
    combat_timeout_seconds: float = 300.0
    recovery_timeout_seconds: float = 600.0
    recovery_hp_percent: float = 90.0
    recovery_stamina_percent: float = 90.0
    chat_poll_seconds: float = 0.10
    fps: float = 12.0

    def normalized(self) -> "HuntingConfig":
        return replace(
            self,
            walk_seconds=max(0.50, min(10.0, float(self.walk_seconds))),
            combat_timeout_seconds=max(30.0, min(900.0, float(self.combat_timeout_seconds))),
            recovery_timeout_seconds=max(30.0, min(1800.0, float(self.recovery_timeout_seconds))),
            recovery_hp_percent=max(90.0, min(100.0, float(self.recovery_hp_percent))),
            recovery_stamina_percent=max(90.0, min(100.0, float(self.recovery_stamina_percent))),
            chat_poll_seconds=max(0.08, min(1.0, float(self.chat_poll_seconds))),
            fps=max(4.0, min(20.0, float(self.fps))),
        )

    def to_cli_args(self, stop_file: Path) -> list[str]:
        value = self.normalized()
        return [
            "--walk-seconds", str(value.walk_seconds),
            "--combat-timeout", str(value.combat_timeout_seconds),
            "--recovery-timeout", str(value.recovery_timeout_seconds),
            "--recovery-hp", str(value.recovery_hp_percent / 100.0),
            "--recovery-stamina", str(value.recovery_stamina_percent / 100.0),
            "--chat-poll-seconds", str(value.chat_poll_seconds),
            "--fps", str(value.fps),
            "--stop-file", str(stop_file),
        ]


@dataclass(frozen=True, slots=True)
class HuntingSnapshot:
    phase: HuntingPhase = HuntingPhase.IDLE
    running: bool = False
    kills: int = 0
    direction: str = "-"
    last_enemy: str = ""
    health: float | None = None
    stamina: float | None = None
    stamina_calibrated: bool = False
    last_line: str = ""
    last_error: str = ""
    return_code: int | None = None


OutputCallback = Callable[[str], None]
StatusCallback = Callable[[HuntingSnapshot], None]


class HuntingService:
    _PHASE_RE = re.compile(r"\bHUNTING_PHASE\s+phase=([a-z_]+)", re.IGNORECASE)
    _KILLS_RE = re.compile(r"\bkills=(\d+)\b", re.IGNORECASE)
    _DIRECTION_RE = re.compile(r"\bdirection=([a-z-]+)\b", re.IGNORECASE)
    _ENEMY_RE = re.compile(r"\bHUNTING_ENEMY\s+clan=(.*?)\s+name=(.*?)\s*$", re.IGNORECASE)
    _RESOURCE_RE = re.compile(
        r"\bHUNTING_RESOURCES\s+hp=([^\s]+)\s+stamina=([^\s]+)\s+stamina_calibrated=(true|false)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        project_dir: Path | None = None,
        python_executable: str | Path | None = None,
        popen_factory=subprocess.Popen,
    ) -> None:
        self.project_dir = (
            Path(project_dir).resolve()
            if project_dir is not None
            else Path(__file__).resolve().parents[2]
        )
        self.python_executable = str(python_executable or sys.executable)
        self._popen_factory = popen_factory
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._process = None
        self._snapshot = HuntingSnapshot()
        self._on_output: OutputCallback | None = None
        self._on_status: StatusCallback | None = None
        self._stop_requested = False
        self._stop_file = Path(tempfile.gettempdir()) / "kagelink_hunting.stop"

    @property
    def is_frozen_runtime(self) -> bool:
        return bool(getattr(sys, "frozen", False))

    @property
    def packaged_helper_path(self) -> Path:
        return Path(sys.executable).resolve().with_name("KagePilotRound.exe")

    @property
    def script_path(self) -> Path:
        if self.is_frozen_runtime:
            return self.packaged_helper_path
        return self.project_dir / "kage_pilot_round.py"

    def runtime_available(self) -> bool:
        return self.script_path.exists()

    def build_command(self, config: HuntingConfig) -> list[str]:
        args = ["--hunting", *config.normalized().to_cli_args(self._stop_file)]
        if self.is_frozen_runtime:
            return [str(self.packaged_helper_path), *args]
        return [self.python_executable, str(self.script_path), *args]

    def snapshot(self) -> HuntingSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def is_running(self) -> bool:
        return self.snapshot().running

    def _publish(self, snapshot: HuntingSnapshot) -> None:
        callback = None
        with self._lock:
            self._snapshot = snapshot
            callback = self._on_status
        if callback is not None:
            try:
                callback(snapshot)
            except Exception:
                pass

    def _consume_line(self, line: str) -> None:
        clean = str(line).rstrip("\r\n")
        old = self.snapshot()
        phase = old.phase
        error = old.last_error
        match = self._PHASE_RE.search(clean)
        if match:
            try:
                phase = HuntingPhase(match.group(1).lower())
            except ValueError:
                pass
        if "HUNTING_RUNTIME_ERROR" in clean:
            phase = HuntingPhase.ERROR
            error = clean

        kills = old.kills
        kill_match = self._KILLS_RE.search(clean)
        if kill_match:
            kills = max(kills, int(kill_match.group(1)))

        direction = old.direction
        direction_match = self._DIRECTION_RE.search(clean)
        if direction_match:
            direction = direction_match.group(1).lower()

        last_enemy = old.last_enemy
        enemy_match = self._ENEMY_RE.search(clean)
        if enemy_match:
            last_enemy = f"{enemy_match.group(1).strip()}, {enemy_match.group(2).strip()}"

        health = old.health
        stamina = old.stamina
        stamina_calibrated = old.stamina_calibrated
        resource_match = self._RESOURCE_RE.search(clean)
        if resource_match:
            hp_raw, stamina_raw, calibrated_raw = resource_match.groups()
            health = None if hp_raw == "-" else float(hp_raw)
            stamina = None if stamina_raw == "-" else float(stamina_raw)
            stamina_calibrated = calibrated_raw.casefold() == "true"

        self._publish(
            replace(
                old,
                phase=phase,
                running=phase not in {HuntingPhase.STOPPED, HuntingPhase.ERROR},
                kills=kills,
                direction=direction,
                last_enemy=last_enemy,
                health=health,
                stamina=stamina,
                stamina_calibrated=stamina_calibrated,
                last_line=clean,
                last_error=error,
            )
        )
        callback = self._on_output
        if callback is not None:
            try:
                callback(clean)
            except Exception:
                pass

    def start(
        self,
        config: HuntingConfig | None = None,
        *,
        on_output: OutputCallback | None = None,
        on_status: StatusCallback | None = None,
    ) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            if not self.runtime_available():
                self._snapshot = replace(
                    self._snapshot,
                    phase=HuntingPhase.ERROR,
                    running=False,
                    last_error="HUNTING_RUNTIME_NOT_INSTALLED",
                )
                return False
            self._stop_requested = False
            self._on_output = on_output
            self._on_status = on_status
            self._stop_file.unlink(missing_ok=True)
            self._snapshot = HuntingSnapshot(phase=HuntingPhase.STARTING, running=True)
            thread = threading.Thread(
                target=self._run,
                args=((config or HuntingConfig()).normalized(),),
                name="KageLinkHunting",
                daemon=True,
            )
            self._thread = thread
            thread.start()
        return True

    def _run(self, config: HuntingConfig) -> None:
        command = self.build_command(config)
        creationflags = 0
        if os.name == "nt":
            creationflags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            if self.is_frozen_runtime:
                creationflags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            process = self._popen_factory(
                command,
                cwd=str(self.script_path.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            with self._lock:
                self._process = process
            for line in process.stdout or ():
                self._consume_line(line)
            return_code = int(process.wait())
            previous = self.snapshot()
            if self._stop_requested or return_code == 0:
                phase = HuntingPhase.STOPPED
                error = previous.last_error
            else:
                phase = HuntingPhase.ERROR
                error = previous.last_error or f"HUNTING_PROCESS_EXIT:{return_code}"
            self._publish(
                replace(previous, phase=phase, running=False, return_code=return_code, last_error=error)
            )
        except Exception as exc:
            previous = self.snapshot()
            self._publish(
                replace(
                    previous,
                    phase=HuntingPhase.ERROR,
                    running=False,
                    last_error=f"{type(exc).__name__}:{exc}",
                )
            )
        finally:
            self._stop_file.unlink(missing_ok=True)
            with self._lock:
                self._process = None

    def stop(self, *, timeout: float = 8.0) -> bool:
        with self._lock:
            process = self._process
            thread = self._thread
            if thread is None or not thread.is_alive():
                return False
            self._stop_requested = True
        previous = self.snapshot()
        self._publish(replace(previous, phase=HuntingPhase.STOPPING, running=True))
        try:
            self._stop_file.write_text("stop\n", encoding="ascii")
        except Exception:
            pass

        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=max(1.0, min(5.0, float(timeout))))
            except Exception:
                pid = int(getattr(process, "pid", 0) or 0)
                if os.name == "nt" and pid > 0:
                    try:
                        subprocess.run(
                            ["taskkill", "/PID", str(pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=3.0,
                            check=False,
                            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
                        )
                    except Exception:
                        pass
                else:
                    try:
                        process.terminate()
                    except Exception:
                        pass

        thread.join(timeout=max(1.0, float(timeout)))
        return True


__all__ = [
    "HuntingConfig",
    "HuntingPhase",
    "HuntingService",
    "HuntingSnapshot",
]
