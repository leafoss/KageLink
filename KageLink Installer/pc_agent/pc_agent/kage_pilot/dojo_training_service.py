from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import sys

from .dojo_journal_v351 import DojoSessionJournal, latest_dojo_error
from .dojo_templates import DEFAULT_DOJO_TEMPLATE_STORE
from .dojo_training import (
    DojoTrainingConfig,
    DojoTrainingPhase,
    DojoTrainingService as _BaseDojoTrainingService,
    DojoTrainingSnapshot,
)


class DojoTrainingService(_BaseDojoTrainingService):
    """Stable public facade with crash-safe 3.5.1 Dojo diagnostics."""

    _COMPLETED_RE = re.compile(
        r"^\s*(?:DOJO_LOOP_(?:FINISHED|STOPPED)|DOJO_FINAL)\b.*\bcompleted=(\d+)\b",
        re.IGNORECASE,
    )

    def __init__(self, *args, **kwargs) -> None:
        self._journal: DojoSessionJournal | None = None
        self._last_journal_path = ""
        DojoSessionJournal.recover_abandoned()
        super().__init__(*args, **kwargs)

    @property
    def is_frozen_runtime(self) -> bool:
        return bool(getattr(sys, "frozen", False))

    @property
    def packaged_helper_path(self) -> Path:
        return Path(sys.executable).resolve().with_name("KagePilotDojo.exe")

    @property
    def script_path(self) -> Path:
        if self.is_frozen_runtime:
            return self.packaged_helper_path
        return self.project_dir / "kage_pilot_loop.py"

    def build_command(self, config: DojoTrainingConfig) -> list[str]:
        value = config.normalized()
        if self.is_frozen_runtime:
            return [str(self.packaged_helper_path), *value.to_cli_args()]
        return [self.python_executable, str(self.script_path), *value.to_cli_args()]

    def runtime_available(self) -> bool:
        return self.script_path.exists()

    def log_status(self) -> dict:
        payload = latest_dojo_error().to_dict()
        payload["directory"] = str(latest_dojo_error.__globals__["canonical_dojo_log_dir"]())
        return payload

    def _journal_metadata(self, config: DojoTrainingConfig) -> dict:
        try:
            templates = DEFAULT_DOJO_TEMPLATE_STORE.public_status()
        except Exception as exc:
            templates = {"metadata_error": f"{type(exc).__name__}:{exc}"}
        return {
            "kagelink_version": "3.5.1",
            "kage_pilot_version": "v0.3j+visual-position-3.5.1",
            "frozen_runtime": self.is_frozen_runtime,
            "command": self.build_command(config),
            "configuration": config.to_public_dict(),
            "templates": templates,
        }

    def start(self, config: DojoTrainingConfig | None = None, **kwargs) -> bool:
        value = (config or DojoTrainingConfig()).normalized()
        journal = DojoSessionJournal(metadata=self._journal_metadata(value))
        self._journal = journal
        started = super().start(value, **kwargs)
        if not started:
            snapshot = self.snapshot()
            destination = journal.finalize(
                success=False,
                error=snapshot.last_error or "DOJO_START_REJECTED",
                return_code=snapshot.return_code,
                summary={
                    "phase": snapshot.phase.value,
                    "current_round": snapshot.current_round,
                    "completed_rounds": snapshot.completed_rounds,
                },
            )
            self._last_journal_path = str(destination or "")
            self._journal = None
        return started

    @classmethod
    def phase_for_line(cls, line: str, current: DojoTrainingPhase) -> DojoTrainingPhase:
        text = str(line or "").casefold()
        if "dojo_loop_finished" in text or "dojo_loop_stopped" in text:
            return DojoTrainingPhase.STOPPED
        if "dojo_final" in text and "phase=stopped" in text:
            return DojoTrainingPhase.STOPPED
        return super().phase_for_line(line, current)

    def _consume_output_line(self, line: str) -> None:
        journal = self._journal
        if journal is not None:
            journal.write_output(line)
        super()._consume_output_line(line)

    def _creation_flags(self) -> int:
        if os.name != "nt":
            return 0
        flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        if self.is_frozen_runtime:
            flags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return flags

    def _run(self, config: DojoTrainingConfig) -> None:
        command = self.build_command(config)
        cwd = self.packaged_helper_path.parent if self.is_frozen_runtime else self.project_dir
        process = None
        caught: BaseException | None = None
        try:
            process = self._popen_factory(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=self._creation_flags(),
            )
            with self._lock:
                self._process = process
            self._set_phase(DojoTrainingPhase.STARTING, running=True)
            for line in process.stdout or ():
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
            caught = exc
            journal = self._journal
            if journal is not None:
                journal.write_exception(exc)
            self._set_phase(
                DojoTrainingPhase.ERROR,
                running=False,
                last_error=f"{type(exc).__name__}:{exc}",
            )
        finally:
            with self._lock:
                self._process = None
            snapshot = self.snapshot()
            success = snapshot.phase != DojoTrainingPhase.ERROR and (
                snapshot.return_code in (None, 0) or self._stop_requested
            )
            journal = self._journal
            if journal is not None:
                destination = journal.finalize(
                    success=success,
                    error=(
                        snapshot.last_error
                        or (f"{type(caught).__name__}:{caught}" if caught is not None else "")
                    ),
                    return_code=snapshot.return_code,
                    summary={
                        "phase": snapshot.phase.value,
                        "current_round": snapshot.current_round,
                        "completed_rounds": snapshot.completed_rounds,
                        "stop_requested": self._stop_requested,
                        "last_line": snapshot.last_line,
                    },
                )
                self._last_journal_path = str(destination or "")
                self._journal = None

    def stop(self, *, timeout: float = 8.0) -> bool:
        if not self.is_frozen_runtime or os.name != "nt":
            return super().stop(timeout=timeout)

        with self._lock:
            process = self._process
            thread = self._thread
            if thread is None or not thread.is_alive():
                return False
            self._stop_requested = True
        journal = self._journal
        if journal is not None:
            journal.write("STOP", "requested_by_desktop")
        self._set_phase(DojoTrainingPhase.STOPPING, running=True)

        if process is not None and process.poll() is None:
            pid = int(getattr(process, "pid", 0) or 0)
            if pid > 0:
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=max(2.0, float(timeout)),
                        check=False,
                        creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
                    )
                except Exception:
                    pass
            try:
                process.wait(timeout=max(0.5, float(timeout)))
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

        thread.join(timeout=max(0.5, float(timeout)))
        return True


__all__ = [
    "DojoTrainingConfig",
    "DojoTrainingPhase",
    "DojoTrainingService",
    "DojoTrainingSnapshot",
]
