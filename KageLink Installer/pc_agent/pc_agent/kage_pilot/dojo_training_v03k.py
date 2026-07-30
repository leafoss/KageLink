from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import sys

from .dojo_training import (
    DojoTrainingConfig,
    DojoTrainingPhase,
    DojoTrainingService as _BaseDojoTrainingService,
    DojoTrainingSnapshot,
)


class DojoTrainingService(_BaseDojoTrainingService):
    """Stable public facade for source-tree and installed Dojo runtimes.

    Source development uses the canonical ``kage_pilot.py dojo`` command. A
    frozen KageLink.exe launches the sibling ``KagePilotDojo.exe`` helper, so
    the same isolated runtime remains usable after installation without loose
    ``.py`` files or a system Python installation.

    Installed helpers are console executables because their stdout is the
    authoritative telemetry stream. KageLink launches them with
    ``CREATE_NO_WINDOW`` and stops the complete Windows process tree, preventing
    visible console flashes and orphaned per-round helpers.

    Search telemetry also contains fields such as ``completed=2`` for completed
    concentric rings. Those values are not completed Dojo rounds and must never
    update the public service snapshot.
    """

    _COMPLETED_RE = re.compile(
        r"^\s*(?:DOJO_LOOP_(?:FINISHED|STOPPED)|DOJO_FINAL)\b.*\bcompleted=(\d+)\b",
        re.IGNORECASE,
    )

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
        return self.project_dir / "kage_pilot.py"

    def build_command(self, config: DojoTrainingConfig) -> list[str]:
        value = config.normalized()
        if self.is_frozen_runtime:
            return [str(self.packaged_helper_path), *value.to_cli_args()]
        return [self.python_executable, str(self.script_path), "dojo", *value.to_cli_args()]

    def runtime_available(self) -> bool:
        return self.script_path.exists()

    @classmethod
    def phase_for_line(cls, line: str, current: DojoTrainingPhase) -> DojoTrainingPhase:
        text = str(line or "").casefold()
        if "dojo_loop_finished" in text or "dojo_loop_stopped" in text:
            return DojoTrainingPhase.STOPPED
        if "dojo_final" in text and "phase=stopped" in text:
            return DojoTrainingPhase.STOPPED
        return super().phase_for_line(line, current)

    def _run(self, config: DojoTrainingConfig) -> None:
        if not self.is_frozen_runtime:
            super()._run(config)
            return

        command = self.build_command(config)
        creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        creationflags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            process = self._popen_factory(
                command,
                cwd=str(self.packaged_helper_path.parent),
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
            self._set_phase(
                DojoTrainingPhase.ERROR,
                running=False,
                last_error=f"{type(exc).__name__}:{exc}",
            )
        finally:
            with self._lock:
                self._process = None

    def stop(self, *, timeout: float = 8.0) -> bool:
        if not self.is_frozen_runtime or os.name != "nt":
            return super().stop(timeout=timeout)

        with self._lock:
            process = self._process
            thread = self._thread
            if thread is None or not thread.is_alive():
                return False
            self._stop_requested = True
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
