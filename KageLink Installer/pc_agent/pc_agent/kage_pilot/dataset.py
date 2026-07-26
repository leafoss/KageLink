from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Any

SCHEMA_VERSION = 1
RESULTS = frozenset({"unknown", "victory", "defeat"})


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "KageLink PC Agent" / "data" / "kage_pilot"
    return Path.home() / ".kagelink" / "kage_pilot"


@dataclass(frozen=True, slots=True)
class Sample:
    index: int
    timestamp: float
    delta_ms: float
    frame: str
    keys: tuple[str, ...]
    mouse_buttons: tuple[str, ...]
    mouse_x: float | None
    mouse_y: float | None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Sample":
        return cls(
            index=int(raw["index"]),
            timestamp=float(raw["timestamp"]),
            delta_ms=float(raw.get("delta_ms", 0.0)),
            frame=str(raw["frame"]),
            keys=tuple(str(v) for v in raw.get("keys", [])),
            mouse_buttons=tuple(str(v) for v in raw.get("mouse_buttons", [])),
            mouse_x=_optional_float(raw.get("mouse_x")),
            mouse_y=_optional_float(raw.get("mouse_y")),
        )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


class SessionWriter:
    """Append-only writer for one demonstrated fight/session."""

    def __init__(
        self,
        root: Path,
        *,
        session_id: str | None = None,
        started_at: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.root = Path(root)
        self.session_id = session_id or time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.path = self.root / "sessions" / self.session_id
        self.frames_dir = self.path / "frames"
        self.samples_path = self.path / "samples.jsonl"
        self.manifest_path = self.path / "manifest.json"
        self.frames_dir.mkdir(parents=True, exist_ok=False)
        self._lock = threading.RLock()
        self._index = 0
        self._started_at = float(started_at if started_at is not None else time.time())
        self._last_timestamp: float | None = None
        self._closed = False
        self._manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "started_at": self._started_at,
            "ended_at": None,
            "duration_seconds": None,
            "result": "unknown",
            "samples": 0,
            "metadata": dict(metadata or {}),
        }
        self._write_manifest()

    def append(
        self,
        jpeg: bytes,
        *,
        timestamp: float,
        keys: Iterable[str] = (),
        mouse_buttons: Iterable[str] = (),
        mouse_x: float | None = None,
        mouse_y: float | None = None,
    ) -> Sample:
        with self._lock:
            if self._closed:
                raise RuntimeError("SESSION_ALREADY_CLOSED")
            ts = float(timestamp)
            delta_ms = 0.0 if self._last_timestamp is None else max(0.0, (ts - self._last_timestamp) * 1000.0)
            frame_name = f"{self._index:06d}.jpg"
            frame_path = self.frames_dir / frame_name
            frame_path.write_bytes(jpeg)
            sample = Sample(
                index=self._index,
                timestamp=ts,
                delta_ms=round(delta_ms, 3),
                frame=f"frames/{frame_name}",
                keys=tuple(sorted({str(k).strip().lower() for k in keys if str(k).strip()})),
                mouse_buttons=tuple(sorted({str(k).strip().lower() for k in mouse_buttons if str(k).strip()})),
                mouse_x=_normalize_optional(mouse_x),
                mouse_y=_normalize_optional(mouse_y),
            )
            with self.samples_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({
                    "index": sample.index,
                    "timestamp": sample.timestamp,
                    "delta_ms": sample.delta_ms,
                    "frame": sample.frame,
                    "keys": list(sample.keys),
                    "mouse_buttons": list(sample.mouse_buttons),
                    "mouse_x": sample.mouse_x,
                    "mouse_y": sample.mouse_y,
                }, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._index += 1
            self._last_timestamp = ts
            self._manifest["samples"] = self._index
            return sample

    def finalize(self, result: str = "unknown", *, ended_at: float | None = None) -> dict[str, Any]:
        normalized = str(result).strip().lower()
        if normalized not in RESULTS:
            raise ValueError("INVALID_SESSION_RESULT")
        with self._lock:
            if self._closed:
                return dict(self._manifest)
            end = float(ended_at if ended_at is not None else time.time())
            self._manifest.update(
                {
                    "ended_at": end,
                    "duration_seconds": round(max(0.0, end - self._started_at), 3),
                    "result": normalized,
                    "samples": self._index,
                }
            )
            actions = self._write_action_runs(end)
            self._manifest["actions"] = actions
            self._write_manifest()
            self._closed = True
            return dict(self._manifest)

    def _write_action_runs(self, ended_at: float) -> int:
        samples = list(DatasetStore.samples(self.path))
        actions_path = self.path / "actions.jsonl"
        if not samples:
            actions_path.write_text("", encoding="utf-8")
            return 0
        rows: list[dict[str, Any]] = []
        start = samples[0]
        previous = samples[0]
        state = (start.keys, start.mouse_buttons)
        for sample in samples[1:]:
            sample_state = (sample.keys, sample.mouse_buttons)
            if sample_state != state:
                rows.append(_action_row(start, previous, sample.timestamp, state))
                start = sample
                state = sample_state
            previous = sample
        rows.append(_action_row(start, previous, ended_at, state))
        with actions_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        return len(rows)

    def _write_manifest(self) -> None:
        temp = self.manifest_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.manifest_path)


def _action_row(start: Sample, previous: Sample, end_timestamp: float, state: tuple[tuple[str, ...], tuple[str, ...]]) -> dict[str, Any]:
    return {
        "start_index": start.index,
        "end_index": previous.index,
        "started_at": start.timestamp,
        "ended_at": float(end_timestamp),
        "duration_ms": round(max(0.0, (float(end_timestamp) - start.timestamp) * 1000.0), 3),
        "keys": list(state[0]),
        "mouse_buttons": list(state[1]),
        "mouse_x": start.mouse_x,
        "mouse_y": start.mouse_y,
    }


def _normalize_optional(value: float | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError("NORMALIZED_COORDINATE_OUT_OF_RANGE")
    return round(number, 6)


class DatasetStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_data_dir()

    def session_paths(self, *, results: Iterable[str] | None = None) -> list[Path]:
        allowed = None if results is None else {str(r).lower() for r in results}
        sessions = self.root / "sessions"
        if not sessions.exists():
            return []
        output: list[Path] = []
        for path in sorted(p for p in sessions.iterdir() if p.is_dir()):
            manifest = self.read_manifest(path)
            if allowed is None or str(manifest.get("result", "unknown")) in allowed:
                output.append(path)
        return output

    @staticmethod
    def read_manifest(session_path: Path) -> dict[str, Any]:
        return json.loads((Path(session_path) / "manifest.json").read_text(encoding="utf-8"))

    @staticmethod
    def samples(session_path: Path) -> Iterator[Sample]:
        samples_path = Path(session_path) / "samples.jsonl"
        if not samples_path.exists():
            return
        with samples_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield Sample.from_dict(json.loads(line))

    def mark_result(self, session_id: str, result: str) -> dict[str, Any]:
        normalized = str(result).strip().lower()
        if normalized not in RESULTS:
            raise ValueError("INVALID_SESSION_RESULT")
        path = self.root / "sessions" / str(session_id) / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["result"] = normalized
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
        return manifest
