from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, TextIO

import cv2
import numpy as np


_ACTIVE_DIAGNOSTICS: "RoundRuntimeDiagnostics | None" = None
_ACTIVE_RECORDER: Any | None = None
_INSTALLED = False


class _Tee:
    def __init__(self, primary: TextIO, secondary: TextIO) -> None:
        self.primary = primary
        self.secondary = secondary

    def write(self, text: str) -> int:
        value = self.primary.write(text)
        self.primary.flush()
        self.secondary.write(text)
        self.secondary.flush()
        return value

    def flush(self) -> None:
        self.primary.flush()
        self.secondary.flush()

    def isatty(self) -> bool:
        return bool(getattr(self.primary, "isatty", lambda: False)())

    @property
    def encoding(self) -> str:
        return getattr(self.primary, "encoding", "utf-8") or "utf-8"


class RoundRuntimeDiagnostics:
    """Persist the complete child console and a machine-readable result."""

    def __init__(self, root: Path | str | None = None) -> None:
        base = (
            Path(root)
            if root is not None
            else Path.cwd() / "kage_pilot_loop_logs" / "runtime_failures"
        )
        base.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.folder = base / f"round_{stamp}_{time.time_ns() % 1_000_000:06d}"
        self.folder.mkdir(parents=True, exist_ok=False)
        self.console_path = self.folder / "child_console.log"
        self.result_path = self.folder / "round_result.json"
        self.traceback_path = self.folder / "escaped_traceback.txt"
        self._console: TextIO | None = None
        self._stdout: TextIO | None = None
        self._stderr: TextIO | None = None
        self._started_at = time.time()
        self._escaped_traceback: str | None = None

    def __enter__(self) -> "RoundRuntimeDiagnostics":
        global _ACTIVE_DIAGNOSTICS
        _ACTIVE_DIAGNOSTICS = self
        self._console = self.console_path.open("w", encoding="utf-8")
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        sys.stdout = _Tee(self._stdout, self._console)  # type: ignore[assignment]
        sys.stderr = _Tee(self._stderr, self._console)  # type: ignore[assignment]
        print(f"PR26_RUNTIME_DIAGNOSTICS folder={self.folder.resolve()}")
        return self

    def finish(self, exit_code: int) -> None:
        recorder = _ACTIVE_RECORDER
        replay_path = getattr(recorder, "full_replay_path", None) if recorder else None
        replay_frames = int(getattr(recorder, "full_replay_frames", 0) or 0) if recorder else 0
        payload = {
            "exit_code": int(exit_code),
            "started_at": self._started_at,
            "finished_at": time.time(),
            "cwd": str(Path.cwd()),
            "argv": list(sys.argv),
            "python": sys.executable,
            "replay": {
                "path": str(replay_path) if replay_path is not None else None,
                "frames": replay_frames,
                "mode": getattr(recorder, "full_replay_mode", None) if recorder else None,
                "codec": getattr(recorder, "full_replay_codec", None) if recorder else None,
                "writer_errors": list(getattr(recorder, "writer_errors", ()) or ()) if recorder else [],
            },
            "escaped_traceback": self._escaped_traceback,
            "console_log": str(self.console_path),
        }
        self.result_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        label = "PR26_ROUND_FAILED_REPORT" if int(exit_code) != 0 else "PR26_ROUND_RESULT"
        print(
            f"{label} exit_code={exit_code} result={self.result_path.resolve()} "
            f"console={self.console_path.resolve()}"
        )

    def __exit__(self, exc_type, exc, tb) -> bool:
        global _ACTIVE_DIAGNOSTICS
        if exc_type is not None:
            self._escaped_traceback = "".join(
                traceback.format_exception(exc_type, exc, tb)
            )
            self.traceback_path.write_text(
                self._escaped_traceback,
                encoding="utf-8",
            )
        if self._stdout is not None:
            sys.stdout = self._stdout
        if self._stderr is not None:
            sys.stderr = self._stderr
        if self._console is not None:
            self._console.close()
        _ACTIVE_DIAGNOSTICS = None
        return False


def _decode_capture(captured: Any) -> np.ndarray | None:
    jpeg = getattr(captured, "jpeg", None)
    if jpeg is None:
        return None
    values = np.frombuffer(bytes(jpeg), dtype=np.uint8)
    if values.size == 0:
        return None
    return cv2.imdecode(values, cv2.IMREAD_COLOR)


def install_round_runtime_diagnostics() -> None:
    """Install passive replay/bootstrap diagnostics before full_round.main()."""

    global _INSTALLED
    if _INSTALLED:
        return

    from pc_agent.kage_pilot import recorder as source_module
    from . import event_recorder as event_module

    Recorder = event_module.CombatEventVideoRecorder
    original_init = Recorder.__init__
    original_close = Recorder.close

    def diagnostic_init(self, *args, **kwargs):
        global _ACTIVE_RECORDER
        original_init(self, *args, **kwargs)
        _ACTIVE_RECORDER = self
        bootstrap_path = Path(self.output_dir) / "recorder_bootstrap.json"
        bootstrap_path.write_text(
            json.dumps(
                {
                    "status": "RECORDER_CONSTRUCTED",
                    "timestamp": time.time(),
                    "output_dir": str(Path(self.output_dir).resolve()),
                    "fps": float(self.fps),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            f"FULL_REPLAY_BOOTSTRAP recorder=CONSTRUCTED "
            f"path={bootstrap_path.resolve()}"
        )

    def diagnostic_close(self):
        try:
            return original_close(self)
        finally:
            status_path = Path(self.output_dir) / "recorder_final_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "status": "RECORDER_CLOSED",
                        "timestamp": time.time(),
                        "summary": self.summary_line(),
                        "path": str(self.full_replay_path) if self.full_replay_path else None,
                        "frames": int(self.full_replay_frames),
                        "mode": self.full_replay_mode,
                        "codec": self.full_replay_codec,
                        "writer_errors": list(self.writer_errors),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"FULL_REPLAY_STATUS path={status_path.resolve()}")

    Recorder.__init__ = diagnostic_init
    Recorder.close = diagnostic_close

    Source = source_module.WindowsGameFrameSource
    original_capture = Source.capture

    def capture_with_bootstrap(self, *args, **kwargs):
        captured = original_capture(self, *args, **kwargs)
        recorder = _ACTIVE_RECORDER
        if recorder is not None and int(recorder.full_replay_frames) == 0:
            try:
                frame = _decode_capture(captured)
                if frame is not None and frame.size > 0:
                    marked = recorder._terminal_frame(
                        frame,
                        "BOOTSTRAP_CAPTURE_BEFORE_OBSERVER",
                    )
                    recorder._write_full_frame(marked)
                    recorder._buffer.append(marked)
                    print(
                        "FULL_REPLAY_BOOTSTRAP_FRAME saved=true "
                        f"size={frame.shape[1]}x{frame.shape[0]}"
                    )
                else:
                    print("FULL_REPLAY_BOOTSTRAP_FRAME saved=false reason=JPEG_DECODE")
            except Exception as exc:
                print(
                    "FULL_REPLAY_BOOTSTRAP_FRAME saved=false "
                    f"reason={type(exc).__name__}:{exc}"
                )
        return captured

    Source.capture = capture_with_bootstrap
    _INSTALLED = True
    print(
        "PR26.12 ROUND DIAGNOSTICS: child console, recorder status and "
        "pre-observer bootstrap frame enabled"
    )


__all__ = ["RoundRuntimeDiagnostics", "install_round_runtime_diagnostics"]
