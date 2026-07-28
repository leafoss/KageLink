from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
from typing import Callable, Iterable


OutputCallback = Callable[[str], None]
StatusCallback = Callable[["DojoTrainingSnapshot"], None]


class DojoTrainingPhase(str, Enum):
    """Stable public phases for CLI, desktop UI and future Game-tab integration."""

    IDLE = "idle"
    STARTING = "starting"
    REQUESTING = "requesting"
    COMBAT = "combat"
    VICTORY = "victory"
    RECOVERY = "recovery"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DojoTrainingConfig:
    """Public configuration contract for the validated v0.3i Dojo loop.

    ``rounds=0`` means continuous training until stop() or F12. The safe default remains one
    round. Values are normalized before process creation so UI callers cannot accidentally pass
    negative delays, zero timeouts or unsupported thresholds.
    """

    rounds: int = 1
    combat_seconds: float = 120.0
    post_combat_timeout: float = 240.0
    dialog_delay: float = 5.0
    dialog_timeout: float = 6.0
    spawn_delay: float = 5.0
    trainer_search_timeout: float = 90.0
    leader_threshold: float = 0.88
    round_startup_delay: float = 1.0
    chat_poll_seconds: float = 0.15
    log_dir: Path = Path("kage_pilot_loop_logs")
    disable_h: bool = False

    def normalized(self) -> "DojoTrainingConfig":
        return replace(
            self,
            rounds=max(0, int(self.rounds)),
            combat_seconds=max(5.0, min(900.0, float(self.combat_seconds))),
            post_combat_timeout=max(15.0, min(1800.0, float(self.post_combat_timeout))),
            dialog_delay=max(0.0, min(30.0, float(self.dialog_delay))),
            dialog_timeout=max(0.5, min(30.0, float(self.dialog_timeout))),
            spawn_delay=max(0.0, min(30.0, float(self.spawn_delay))),
            trainer_search_timeout=max(5.0, min(600.0, float(self.trainer_search_timeout))),
            leader_threshold=max(0.50, min(0.999, float(self.leader_threshold))),
            round_startup_delay=max(0.0, min(30.0, float(self.round_startup_delay))),
            chat_poll_seconds=max(0.10, min(2.0, float(self.chat_poll_seconds))),
            log_dir=Path(self.log_dir),
            disable_h=bool(self.disable_h),
        )

    def to_cli_args(self) -> list[str]:
        value = self.normalized()
        args = [
            "--rounds", str(value.rounds),
            "--combat-seconds", str(value.combat_seconds),
            "--post-combat-timeout", str(value.post_combat_timeout),
            "--dialog-delay", str(value.dialog_delay),
            "--dialog-timeout", str(value.dialog_timeout),
            "--spawn-delay", str(value.spawn_delay),
            "--trainer-search-timeout", str(value.trainer_search_timeout),
            "--leader-threshold", str(value.leader_threshold),
            "--round-startup-delay", str(value.round_startup_delay),
            "--chat-poll-seconds", str(value.chat_poll_seconds),
            "--log-dir", str(value.log_dir),
        ]
        if value.disable_h:
            args.append("--disable-h")
        return args


@dataclass(frozen=True, slots=True)
class DojoTrainingSnapshot:
    phase: DojoTrainingPhase = DojoTrainingPhase.IDLE
    running: bool = False
    current_round: int = 0
    completed_rounds: int = 0
    last_line: str = ""
    last_error: str = ""
    return_code: int | None = None


class DojoTrainingService:
    """Thread-safe process facade around the real-Windows-validated v0.3i loop.

    This class intentionally runs the validated loop in a separate process instead of importing
    its versioned monkey-patch modules into the long-lived PC Agent. That isolates runtime globals,
    makes start/stop deterministic and gives the future Game-tab toggle a small stable API.

    The service does not modify the app UI. A future toggle should call start() with rounds=0 when
    enabled and stop() when disabled, while rendering snapshot().phase as status.
    """

    _ROUND_RE = re.compile(r"\bROUND\s+(\d+):", re.IGNORECASE)
    _COMPLETED_RE = re.compile(r"\bcompleted=(\d+)\b", re.IGNORECASE)

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
        self._stop_requested = False
        self._snapshot = DojoTrainingSnapshot()
        self._on_output: OutputCallback | None = None
        self._on_status: StatusCallback | None = None

    @property
    def script_path(self) -> Path:
        return self.project_dir / "kage_pilot_loop_v03i.py"

    def build_command(self, config: DojoTrainingConfig) -> list[str]:
        return [self.python_executable, str(self.script_path), *config.normalized().to_cli_args()]

    def snapshot(self) -> DojoTrainingSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def is_running(self) -> bool:
        return self.snapshot().running

    def _publish(self, snapshot: DojoTrainingSnapshot) -> None:
        callback = None
        with self._lock:
            self._snapshot = snapshot
            callback = self._on_status
        if callback is not None:
            try:
                callback(snapshot)
            except Exception:
                pass

    def _set_phase(
        self,
        phase: DojoTrainingPhase,
        *,
        running: bool | None = None,
        last_line: str | None = None,
        last_error: str | None = None,
        return_code: int | None = None,
        current_round: int | None = None,
        completed_rounds: int | None = None,
    ) -> None:
        previous = self.snapshot()
        self._publish(
            replace(
                previous,
                phase=phase,
                running=previous.running if running is None else bool(running),
                last_line=previous.last_line if last_line is None else str(last_line),
                last_error=previous.last_error if last_error is None else str(last_error),
                return_code=previous.return_code if return_code is None else int(return_code),
                current_round=(
                    previous.current_round if current_round is None else max(0, int(current_round))
                ),
                completed_rounds=(
                    previous.completed_rounds
                    if completed_rounds is None
                    else max(0, int(completed_rounds))
                ),
            )
        )

    @classmethod
    def phase_for_line(cls, line: str, current: DojoTrainingPhase) -> DojoTrainingPhase:
        text = str(line or "").casefold()
        if any(
            marker in text
            for marker in (
                "dojo_request_failed",
                "dojo_request_stopped",
                "child_exit=",
                "no victory chat",
                "no ready result",
                "controle interrompido",
                "live control stopped",
            )
        ):
            return DojoTrainingPhase.ERROR
        if "search and request taijutsu dojo spar" in text:
            return DojoTrainingPhase.REQUESTING
        if "start combat runtime" in text:
            return DojoTrainingPhase.COMBAT
        if "victory_chat / vitoria_chat" in text:
            return DojoTrainingPhase.VICTORY
        if "post_combat / pos-combate" in text or text.startswith("post "):
            return DojoTrainingPhase.RECOVERY
        if "round " in text and "complete / concluida" in text:
            return DojoTrainingPhase.READY
        if "dojo_loop_stopped" in text:
            return DojoTrainingPhase.STOPPED
        return current

    def _consume_output_line(self, line: str) -> None:
        clean = str(line).rstrip("\r\n")
        previous = self.snapshot()
        phase = self.phase_for_line(clean, previous.phase)
        round_match = self._ROUND_RE.search(clean)
        completed_match = self._COMPLETED_RE.search(clean)
        current_round = previous.current_round
        completed_rounds = previous.completed_rounds
        if round_match is not None:
            current_round = max(current_round, int(round_match.group(1)))
        if "complete / concluida" in clean.casefold() and round_match is not None:
            completed_rounds = max(completed_rounds, int(round_match.group(1)))
        if completed_match is not None:
            completed_rounds = max(completed_rounds, int(completed_match.group(1)))
        error = clean if phase == DojoTrainingPhase.ERROR else previous.last_error
        self._set_phase(
            phase,
            running=True,
            last_line=clean,
            last_error=error,
            current_round=current_round,
            completed_rounds=completed_rounds,
        )
        callback = self._on_output
        if callback is not None:
            try:
                callback(clean)
            except Exception:
                pass

    def start(
        self,
        config: DojoTrainingConfig | None = None,
        *,
        on_output: OutputCallback | None = None,
        on_status: StatusCallback | None = None,
    ) -> bool:
        value = (config or DojoTrainingConfig()).normalized()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            if not self.script_path.exists():
                self._snapshot = DojoTrainingSnapshot(
                    phase=DojoTrainingPhase.ERROR,
                    last_error=f"DOJO_SCRIPT_NOT_FOUND:{self.script_path}",
                )
                return False
            self._on_output = on_output
            self._on_status = on_status
            self._stop_requested = False
            self._snapshot = DojoTrainingSnapshot(
                phase=DojoTrainingPhase.STARTING,
                running=True,
            )
            self._thread = threading.Thread(
                target=self._run,
                args=(value,),
                name="kage-pilot-dojo-training",
                daemon=True,
            )
            thread = self._thread
        self._publish(self.snapshot())
        thread.start()
        return True

    def _run(self, config: DojoTrainingConfig) -> None:
        command = self.build_command(config)
        creationflags = 0
        if os.name == "nt":
            creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        try:
            process = self._popen_factory(
                command,
                cwd=str(self.project_dir),
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
            self._set_phase(DojoTrainingPhase.STARTING, running=True)
            stream: Iterable[str] = process.stdout or ()
            for line in stream:
                self._consume_output_line(line)
            return_code = int(process.wait())
            previous = self.snapshot()
            if self._stop_requested:
                final_phase = DojoTrainingPhase.STOPPED
                error = previous.last_error
            elif return_code != 0 or previous.phase == DojoTrainingPhase.ERROR:
                final_phase = DojoTrainingPhase.ERROR
                error = previous.last_error or f"DOJO_PROCESS_EXIT:{return_code}"
            else:
                final_phase = DojoTrainingPhase.STOPPED
                error = previous.last_error
            self._set_phase(
                final_phase,
                running=False,
                last_error=error,
                return_code=return_code,
            )
        except Exception as exc:
            self._set_phase(
                DojoTrainingPhase.ERROR,
                running=False,
                last_error=f"{type(exc).__name__}:{exc}",
            )
        finally:
            with self._lock:
                self._process = None

    def wait(self, timeout: float | None = None) -> DojoTrainingSnapshot:
        thread = None
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout=None if timeout is None else max(0.0, float(timeout)))
        return self.snapshot()

    def stop(self, *, timeout: float = 6.0) -> bool:
        with self._lock:
            process = self._process
            thread = self._thread
            if thread is None or not thread.is_alive():
                return False
            self._stop_requested = True
        self._set_phase(DojoTrainingPhase.STOPPING, running=True)

        if process is not None and process.poll() is None:
            try:
                if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
            except Exception:
                pass
            try:
                process.wait(timeout=max(0.5, float(timeout)))
            except Exception:
                try:
                    process.terminate()
                    process.wait(timeout=2.0)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass

        if thread is not None:
            thread.join(timeout=max(0.5, float(timeout)))
        return True


__all__ = [
    "DojoTrainingConfig",
    "DojoTrainingPhase",
    "DojoTrainingService",
    "DojoTrainingSnapshot",
]
