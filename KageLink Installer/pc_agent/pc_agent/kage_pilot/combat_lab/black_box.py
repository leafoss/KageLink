from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import queue
import threading
import time
from typing import Callable

import numpy as np

from ..combat_strategy_v351 import CombatTargetSnapshotV2, GridObservation
from .replay import observation_to_dict


Telemetry = Callable[[str, dict[str, object]], None]


@dataclass(slots=True)
class BlackBoxRecord:
    timestamp: float
    frame_index: int
    raw_arena: np.ndarray
    player_anchor: tuple[float, float]
    player_cell: tuple[int, int]
    grid_origin: tuple[float, float]
    tile_size: float
    raw_candidates: tuple[dict[str, object], ...]
    filtered_candidates: tuple[dict[str, object], ...]
    tracks: tuple[dict[str, object], ...]
    observations: tuple[GridObservation, ...]
    snapshot: CombatTargetSnapshotV2
    decision: dict[str, object] | None = None
    command: dict[str, object] | None = None
    attack_context: dict[str, object] | None = None
    ko_state: str = "NONE"


@dataclass(frozen=True, slots=True)
class BlackBoxStats:
    buffered: int
    submitted: int
    dropped: int
    materialized: int
    pending_jobs: int


class CombatBlackBoxRecorder:
    """Bounded hot-path buffer with asynchronous failure materialization.

    `append` stores the already captured arena and simple metadata. Rendering, video
    encoding and disk writes never happen in the combat loop. When the lock is busy or
    the ring is full, evidence is discarded according to a bounded policy.
    """

    def __init__(
        self,
        *,
        max_frames: int = 160,
        root: str | Path | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.max_frames = max(16, min(1200, int(max_frames)))
        self.root = (
            Path(root)
            if root is not None
            else Path.home() / ".kagelink" / "combat_black_box"
        )
        self.telemetry = telemetry
        self._records: deque[BlackBoxRecord] = deque(maxlen=self.max_frames)
        self._lock = threading.Lock()
        self._jobs: queue.Queue[tuple[str, tuple[BlackBoxRecord, ...]]] = queue.Queue(
            maxsize=2
        )
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._worker,
            name="kage-combat-black-box",
            daemon=True,
        )
        self._thread.start()
        self.submitted = 0
        self.dropped = 0
        self.materialized = 0

    def _emit(self, event: str, fields: dict[str, object]) -> None:
        if self.telemetry is not None:
            try:
                self.telemetry(event, fields)
            except Exception:
                pass

    def append(self, record: BlackBoxRecord) -> bool:
        if not self._lock.acquire(blocking=False):
            self.dropped += 1
            return False
        try:
            before = len(self._records)
            self._records.append(record)
            if before == self.max_frames:
                self.dropped += 1
            self.submitted += 1
            return True
        finally:
            self._lock.release()

    def snapshot(self) -> tuple[BlackBoxRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def request_materialization(self, reason: str) -> bool:
        records = self.snapshot()
        if not records:
            return False
        try:
            self._jobs.put_nowait((str(reason or "requested"), records))
            return True
        except queue.Full:
            self.dropped += len(records)
            self._emit("DOJO_COMBAT_BLACK_BOX_JOB_DROPPED", {"reason": reason})
            return False

    def stats(self) -> BlackBoxStats:
        return BlackBoxStats(
            buffered=len(self._records),
            submitted=self.submitted,
            dropped=self.dropped,
            materialized=self.materialized,
            pending_jobs=self._jobs.qsize(),
        )

    def flush(self, *, timeout: float = 4.0) -> bool:
        """Wait outside the combat loop for already requested packages to finish."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while self._jobs.unfinished_tasks > 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        return self._jobs.unfinished_tasks == 0

    def close(self, *, timeout: float = 4.0) -> None:
        # A failure request is queued immediately before shutdown. Drain it first so
        # closing the process cannot silently discard the only forensic package.
        self.flush(timeout=max(0.0, float(timeout)))
        self._stop.set()
        try:
            self._jobs.put_nowait(("__stop__", ()))
        except queue.Full:
            pass
        self._thread.join(timeout=max(0.0, float(timeout)))

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                reason, records = self._jobs.get(timeout=0.25)
            except queue.Empty:
                continue
            if reason == "__stop__":
                self._jobs.task_done()
                return
            try:
                destination = self._write_package(reason, records)
                self.materialized += 1
                self._emit(
                    "DOJO_COMBAT_BLACK_BOX_MATERIALIZED",
                    {"path": str(destination), "reason": reason, "frames": len(records)},
                )
            except Exception as error:
                self._emit(
                    "DOJO_COMBAT_BLACK_BOX_FAILED",
                    {"reason": reason, "error": f"{type(error).__name__}:{error}"},
                )
            finally:
                self._jobs.task_done()

    def _write_package(self, reason: str, records: tuple[BlackBoxRecord, ...]) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destination = self.root / f"combat_{stamp}_{reason}"
        destination.mkdir(parents=True, exist_ok=False)
        frames = np.stack([np.asarray(item.raw_arena) for item in records], axis=0)
        np.savez_compressed(destination / "raw_arena_frames.npz", frames=frames)

        rows: list[dict[str, object]] = []
        for index, item in enumerate(records):
            rows.append(
                {
                    "frame_slot": index,
                    "timestamp": item.timestamp,
                    "frame_index": item.frame_index,
                    "player_anchor": list(item.player_anchor),
                    "player_cell": list(item.player_cell),
                    "grid_origin": list(item.grid_origin),
                    "tile_size": item.tile_size,
                    "raw_candidates": list(item.raw_candidates),
                    "filtered_candidates": list(item.filtered_candidates),
                    "tracks": list(item.tracks),
                    "observations": [
                        observation_to_dict(value) for value in item.observations
                    ],
                    "snapshot": asdict(item.snapshot),
                    "decision": item.decision,
                    "command": item.command,
                    "attack_context": item.attack_context,
                    "ko_state": item.ko_state,
                }
            )
        (destination / "replay.json").write_text(
            json.dumps(
                {"version": 1, "reason": reason, "frames": rows},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return destination


__all__ = [
    "BlackBoxRecord",
    "BlackBoxStats",
    "CombatBlackBoxRecorder",
]
