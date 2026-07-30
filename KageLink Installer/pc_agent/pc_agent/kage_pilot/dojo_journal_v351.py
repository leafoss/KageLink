from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import threading
import traceback
import uuid
from typing import Any, Mapping


def canonical_dojo_log_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return root / "KageLink" / "logs" / "dojo"


def _now() -> datetime:
    return datetime.now().astimezone()


def _stamp(value: datetime | None = None) -> str:
    return (value or _now()).isoformat(timespec="milliseconds")


def _filename_stamp(value: datetime | None = None) -> str:
    return (value or _now()).strftime("%Y-%m-%d_%H-%M-%S")


def _safe_scalar(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\r", " ").replace("\n", "\\n").strip()
    return text or "-"


def _fields_text(fields: Mapping[str, Any]) -> str:
    return " ".join(f"{key}={_safe_scalar(value)}" for key, value in sorted(fields.items()))


@dataclass(frozen=True, slots=True)
class DojoLogStatus:
    exists: bool = False
    path: str = ""
    filename: str = ""
    modified_at: str = ""
    kind: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "exists": self.exists,
            "path": self.path,
            "filename": self.filename,
            "modified_at": self.modified_at,
            "kind": self.kind,
            "summary": self.summary,
        }


class DojoSessionJournal:
    """Crash-safe UTF-8 journal kept only when a Dojo session fails.

    The file is line-buffered and flushed after every event. Successful or user-stopped
    sessions remove the temporary ``.active`` file. Error sessions rename it to ``.txt``.
    Any stale active file is converted to an incomplete log on the next startup.
    Journal failures are deliberately non-fatal so the F12 safety path remains independent.
    """

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        metadata: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> None:
        self.root = Path(root) if root is not None else canonical_dojo_log_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.started_at = _now()
        self.session_id = (session_id or uuid.uuid4().hex[:12]).replace("-", "")
        self.active_path = self.root / (
            f"dojo_session_{_filename_stamp(self.started_at)}_{self.session_id}.active"
        )
        self._lock = threading.RLock()
        self._closed = False
        self._healthy = True
        self._last_error = ""
        self._handle = self.active_path.open("w", encoding="utf-8", buffering=1)
        self.write("SESSION", "started", session_id=self.session_id)
        for key, value in sorted(dict(metadata or {}).items()):
            if isinstance(value, (dict, list, tuple)):
                encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
                self.write("CONFIG", "metadata", key=key, value=encoded)
            else:
                self.write("CONFIG", "metadata", key=key, value=value)

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def last_error(self) -> str:
        return self._last_error

    def _write_text(self, text: str) -> None:
        if self._closed or not self._healthy:
            return
        try:
            self._handle.write(text)
            self._handle.flush()
        except Exception as exc:  # logging must never break F12 or key release
            self._healthy = False
            self._last_error = f"{type(exc).__name__}:{exc}"

    def write(self, category: str, message: str, **fields: Any) -> None:
        category_text = str(category or "EVENT").strip().upper().replace(" ", "_")
        message_text = str(message or "-").replace("\r", " ").replace("\n", "\\n")
        suffix = _fields_text(fields)
        line = f"{_stamp()} [{category_text}] {message_text}"
        if suffix:
            line += f" {suffix}"
        with self._lock:
            self._write_text(line + "\n")

    def write_output(self, line: str) -> None:
        clean = str(line or "").rstrip("\r\n")
        if clean:
            self.write("OUTPUT", clean)

    def write_exception(self, exc: BaseException, *, category: str = "ERROR") -> None:
        self.write(category, f"{type(exc).__name__}:{exc}")
        formatted = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        for line in formatted.rstrip().splitlines():
            self.write("TRACEBACK", line)

    def finalize(
        self,
        *,
        success: bool,
        error: str = "",
        return_code: int | None = None,
        summary: Mapping[str, Any] | None = None,
    ) -> Path | None:
        with self._lock:
            if self._closed:
                return None
            finished = _now()
            duration = max(0.0, (finished - self.started_at).total_seconds())
            for key, value in sorted(dict(summary or {}).items()):
                self.write("SUMMARY", "value", key=key, value=value)
            if error:
                self.write("ERROR", error, return_code=return_code)
            self.write(
                "SESSION",
                "finished",
                success=success,
                return_code=return_code,
                duration_seconds=f"{duration:.3f}",
            )
            try:
                self._handle.flush()
                self._handle.close()
            except Exception:
                pass
            self._closed = True

            if success:
                try:
                    self.active_path.unlink(missing_ok=True)
                except Exception:
                    pass
                return None

            destination = self.root / (
                f"dojo_error_{_filename_stamp(self.started_at)}_{self.session_id}.txt"
            )
            try:
                self.active_path.replace(destination)
                return destination
            except Exception as exc:
                self._healthy = False
                self._last_error = f"{type(exc).__name__}:{exc}"
                return self.active_path if self.active_path.exists() else None

    @classmethod
    def recover_abandoned(cls, root: str | Path | None = None) -> list[Path]:
        directory = Path(root) if root is not None else canonical_dojo_log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        recovered: list[Path] = []
        for active in sorted(directory.glob("dojo_session_*.active")):
            destination = directory / active.name.replace("dojo_session_", "dojo_incomplete_").replace(
                ".active", ".txt"
            )
            try:
                with active.open("a", encoding="utf-8") as handle:
                    handle.write(
                        f"{_stamp()} [ERROR] UNCLEAN_PREVIOUS_SHUTDOWN recovered_on_startup=true\n"
                    )
                    handle.flush()
                active.replace(destination)
                recovered.append(destination)
            except Exception:
                continue
        return recovered


def latest_dojo_error(root: str | Path | None = None) -> DojoLogStatus:
    directory = Path(root) if root is not None else canonical_dojo_log_dir()
    if not directory.exists():
        return DojoLogStatus()
    candidates = [*directory.glob("dojo_error_*.txt"), *directory.glob("dojo_incomplete_*.txt")]
    if not candidates:
        return DojoLogStatus()
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    kind = "incomplete" if newest.name.startswith("dojo_incomplete_") else "error"
    summary = ""
    try:
        lines = newest.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            if "[ERROR]" in line:
                summary = line.split("[ERROR]", 1)[1].strip()
                break
        if not summary and lines:
            summary = lines[-1][-500:]
    except Exception:
        pass
    modified = datetime.fromtimestamp(newest.stat().st_mtime).astimezone()
    return DojoLogStatus(
        exists=True,
        path=str(newest.resolve()),
        filename=newest.name,
        modified_at=_stamp(modified),
        kind=kind,
        summary=summary,
    )


__all__ = [
    "DojoLogStatus",
    "DojoSessionJournal",
    "canonical_dojo_log_dir",
    "latest_dojo_error",
]
