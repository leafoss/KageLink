from __future__ import annotations

from dataclasses import asdict, is_dataclass
import os
from pathlib import Path
import time
from typing import Any

import numpy as np

from .combat_lab.black_box import BlackBoxRecord, CombatBlackBoxRecorder


_ACTIVE_RECORDER: CombatBlackBoxRecorder | None = None
_ACTIVE_PENDING: dict[int, BlackBoxRecord] = {}
_ACTIVE_LAST_FRAME_INDEX: int | None = None


def _plain(value: Any) -> dict[str, object] | None:
    if value is None:
        return None
    if is_dataclass(value):
        try:
            return asdict(value)
        except Exception:
            pass
    try:
        return {
            str(key): item
            for key, item in vars(value).items()
            if isinstance(item, (str, int, float, bool, type(None), tuple, list, dict))
        }
    except Exception:
        return {"repr": repr(value)}


def _track_row(track: Any, observer: Any) -> dict[str, object]:
    track_id = int(getattr(track, "track_id", 0) or 0)
    context = None
    metrics = None
    try:
        context = observer.tracker.context_for(track_id)
    except Exception:
        pass
    try:
        metrics = observer.metrics_for(track_id)
    except Exception:
        pass
    return {
        "track_id": track_id,
        "bbox": tuple(int(value) for value in getattr(track, "bbox", (0, 0, 0, 0))),
        "center": tuple(float(value) for value in getattr(track, "center", (0.0, 0.0))),
        "enemy_score": float(getattr(track, "enemy_score", 0.0) or 0.0),
        "shape_score": float(getattr(track, "shape_score", 0.0) or 0.0),
        "context_state": str(getattr(context, "state", "-") or "-"),
        "grid_cell": getattr(metrics, "cell", None),
        "player_cell": getattr(metrics, "player_cell", None),
        "grid_distance": getattr(metrics, "grid_distance", None),
    }


def _candidate_rows(values: Any) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for value in tuple(values or ()):
        bbox = getattr(value, "bbox", None)
        if bbox is None:
            bbox = getattr(value, "candidate_bbox", None)
        rows.append(
            {
                "bbox": tuple(int(item) for item in bbox or (0, 0, 0, 0)),
                "reason": str(getattr(value, "reason", "") or ""),
                "score": float(getattr(value, "score", 0.0) or 0.0),
            }
        )
    return tuple(rows)


def _arena_crop(frame_bgr: np.ndarray, state: Any) -> np.ndarray:
    try:
        x0, y0, x1, y1 = (int(value) for value in state.arena_rect)
        crop = frame_bgr[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)]
        if crop.size:
            return np.ascontiguousarray(crop.copy())
    except Exception:
        pass
    return np.ascontiguousarray(frame_bgr.copy())


def _player_anchor(observer: Any, state: Any) -> tuple[float, float]:
    method = getattr(observer, "_player_anchor", None)
    if callable(method):
        try:
            point = method(state)
            return float(point[0]), float(point[1])
        except Exception:
            pass
    point = getattr(state, "player_center", (0.0, 0.0))
    return float(point[0]), float(point[1])


def _grid_origin(observer: Any) -> tuple[float, float]:
    try:
        point = observer.grid_origin
        return float(point[0]), float(point[1])
    except Exception:
        return (
            float(getattr(observer, "grid_origin_x", 0.0) or 0.0),
            float(getattr(observer, "grid_origin_y", 0.0) or 0.0),
        )


def _finalize_pending(frame_index: int, *, command: Any = None) -> None:
    global _ACTIVE_LAST_FRAME_INDEX
    recorder = _ACTIVE_RECORDER
    record = _ACTIVE_PENDING.pop(int(frame_index), None)
    if recorder is None or record is None:
        return
    if command is not None:
        record.command = _plain(command)
    recorder.append(record)
    _ACTIVE_LAST_FRAME_INDEX = int(frame_index)


def active_combat_black_box() -> CombatBlackBoxRecorder | None:
    return _ACTIVE_RECORDER


def request_combat_black_box(reason: str) -> bool:
    recorder = _ACTIVE_RECORDER
    if recorder is None:
        return False
    for frame_index in tuple(_ACTIVE_PENDING):
        _finalize_pending(frame_index)
    return recorder.request_materialization(reason)


def close_combat_black_box() -> None:
    global _ACTIVE_RECORDER
    recorder = _ACTIVE_RECORDER
    if recorder is not None:
        recorder.close(timeout=1.5)
    _ACTIVE_RECORDER = None
    _ACTIVE_PENDING.clear()


def install_combat_black_box_runtime(
    runtime: Any,
    *,
    max_frames: int = 80,
    sample_interval_seconds: float = 0.20,
):
    """Install an observational recorder after the canonical strategy classes.

    The adapter cannot send input and never renders/encodes in the combat loop. It
    stores a bounded RAW arena ring and asynchronously materializes only on request or
    failure. Provenance is emitted after this adapter so the exact final classes remain
    visible rather than hidden behind an unnamed monkeypatch.
    """

    import kage_pilot_live_v03 as live_runtime

    if bool(getattr(live_runtime, "_kagelink_combat_black_box_installed", False)):
        return getattr(live_runtime, "_kagelink_combat_black_box_classes")

    telemetry = getattr(runtime, "_telemetry", None)
    root_value = os.getenv("KAGELINK_COMBAT_BLACK_BOX_DIR", "").strip()
    root = Path(root_value) if root_value else None
    global _ACTIVE_RECORDER
    _ACTIVE_RECORDER = CombatBlackBoxRecorder(
        max_frames=max_frames,
        root=root,
        telemetry=telemetry,
    )

    BaseObserver = live_runtime.ParticleSafeGridTargetObserver
    BaseEngine = live_runtime.ShadowCombatDecisionEngine
    BasePlanner = live_runtime.LiveCombatControlPlanner
    BaseWatcher = live_runtime.ChatVictoryWatcher

    class CombatBlackBoxObserver(BaseObserver):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._black_box_last_sample_at = -1e9
            self._black_box_sample_interval = max(
                0.10, min(1.0, float(sample_interval_seconds))
            )

        def process(self, frame_bgr, *, timestamp=None):
            state = super().process(frame_bgr, timestamp=timestamp)
            now = float(getattr(state, "timestamp", time.monotonic()))
            if now - self._black_box_last_sample_at < self._black_box_sample_interval:
                return state
            self._black_box_last_sample_at = now
            frame_index = int(getattr(self, "_combat_frame_index", 0) or 0)
            snapshot = self.combat_snapshot()
            observations = tuple(
                getattr(self, "_last_strategy_observations", ()) or ()
            )
            tracker = getattr(self, "tracker", None)
            rejected = tuple(getattr(tracker, "rejected_candidates", ()) or ())
            tracks = tuple(getattr(state, "tracks", ()) or ())
            player_cell = tuple(getattr(snapshot, "player_cell", (0, 0)))
            previous = _ACTIVE_LAST_FRAME_INDEX
            if previous is not None and previous in _ACTIVE_PENDING:
                _finalize_pending(previous)
            _ACTIVE_PENDING[frame_index] = BlackBoxRecord(
                timestamp=now,
                frame_index=frame_index,
                raw_arena=_arena_crop(frame_bgr, state),
                player_anchor=_player_anchor(self, state),
                player_cell=(int(player_cell[0]), int(player_cell[1])),
                grid_origin=_grid_origin(self),
                tile_size=float(getattr(self, "tile_size", 32.0) or 32.0),
                raw_candidates=(),
                filtered_candidates=_candidate_rows(rejected),
                tracks=tuple(_track_row(track, self) for track in tracks),
                observations=observations,
                snapshot=snapshot,
                ko_state=str(getattr(snapshot, "combat_phase", "COMBAT")),
            )
            return state

    class CombatBlackBoxDecisionEngine(BaseEngine):
        def decide(self, state, observer, tracker, *, now, skills_allowed=True):
            decision = super().decide(
                state,
                observer,
                tracker,
                now=now,
                skills_allowed=skills_allowed,
            )
            frame_index = int(getattr(observer, "_combat_frame_index", 0) or 0)
            record = _ACTIVE_PENDING.get(frame_index)
            if record is not None:
                record.decision = _plain(decision)
                context = getattr(observer, "_attack_visual_context", None)
                record.attack_context = _plain(context)
            return decision

    class CombatBlackBoxPlanner(BasePlanner):
        def plan(self, decision, *, now, movement_allowed=True, block_reason=""):
            command = super().plan(
                decision,
                now=now,
                movement_allowed=movement_allowed,
                block_reason=block_reason,
            )
            observer = getattr(runtime, "_ACTIVE_OBSERVER", None)
            frame_index = None
            if observer is not None:
                frame_index = int(getattr(observer, "_combat_frame_index", 0) or 0)
            if frame_index is None or frame_index not in _ACTIVE_PENDING:
                frame_index = max(_ACTIVE_PENDING, default=None)
            if frame_index is not None:
                _finalize_pending(frame_index, command=command)
            return command

    class CombatBlackBoxVictoryWatcher(BaseWatcher):
        def poll(self):
            signal = super().poll()
            if signal is not None:
                request_combat_black_box("ko")
            return signal

    live_runtime.ParticleSafeGridTargetObserver = CombatBlackBoxObserver
    live_runtime.ShadowCombatDecisionEngine = CombatBlackBoxDecisionEngine
    live_runtime.LiveCombatControlPlanner = CombatBlackBoxPlanner
    live_runtime.ChatVictoryWatcher = CombatBlackBoxVictoryWatcher
    for name, value in (
        ("ParticleSafeGridTargetObserver", CombatBlackBoxObserver),
        ("ShadowCombatDecisionEngine", CombatBlackBoxDecisionEngine),
        ("LiveCombatControlPlanner", CombatBlackBoxPlanner),
        ("ChatVictoryWatcher", CombatBlackBoxVictoryWatcher),
    ):
        if hasattr(runtime, name):
            setattr(runtime, name, value)

    classes = {
        "observer": CombatBlackBoxObserver,
        "engine": CombatBlackBoxDecisionEngine,
        "planner": CombatBlackBoxPlanner,
        "watcher": CombatBlackBoxVictoryWatcher,
    }
    live_runtime._kagelink_combat_black_box_installed = True
    live_runtime._kagelink_combat_black_box_classes = classes
    if telemetry is not None:
        telemetry(
            "DOJO_COMBAT_BLACK_BOX_INSTALLED",
            {
                "max_frames": max_frames,
                "sample_interval_seconds": sample_interval_seconds,
                "hot_path_encoding": "disabled",
                "materialization": "async-on-request-or-failure",
            },
        )
    return classes


__all__ = [
    "active_combat_black_box",
    "close_combat_black_box",
    "install_combat_black_box_runtime",
    "request_combat_black_box",
]
