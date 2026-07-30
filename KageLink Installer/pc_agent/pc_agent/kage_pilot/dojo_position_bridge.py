from __future__ import annotations

import base64
from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from typing import Any, Callable

import cv2
import numpy as np

from .dojo_templates_v35 import UserDojoLeaderDetector
from .entity_observer import decode_jpeg
from .observer_runtime_v03 import V03ObserverConfig
from .particle_safe_grid_target_v03 import ParticleSafeGridTargetObserver
from .recorder import WindowsGameFrameSource
from .visual_position_v351 import (
    PositionState,
    VisualKeyframe,
    VisualPositionTracker,
)


Telemetry = Callable[[str, dict[str, object]], None]


@dataclass(slots=True)
class _BufferedFrame:
    sequence: int
    captured_at: float
    jpeg: bytes
    arena_rect: tuple[int, int, int, int]
    player_center: tuple[float, float]
    flow_dx: float
    flow_dy: float
    flow_points: int
    trainer_bbox: tuple[int, int, int, int] | None = None
    trainer_score: float = 0.0
    trainer_mode: str = "-"

    def frame(self) -> np.ndarray:
        return decode_jpeg(self.jpeg)

    def observer_state(self):
        return SimpleNamespace(
            arena_rect=self.arena_rect,
            player_center=self.player_center,
            global_flow=SimpleNamespace(
                dx=self.flow_dx,
                dy=self.flow_dy,
                points=self.flow_points,
            ),
        )


def _descriptor_base64(descriptor: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", descriptor)
    if not ok:
        raise ValueError("DOJO_POSITION_DESCRIPTOR_ENCODE_FAILED")
    return base64.b64encode(bytes(encoded)).decode("ascii")


def _decode_descriptor(value: str) -> np.ndarray:
    raw = base64.b64decode(str(value or ""), validate=True)
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None or image.size == 0:
        raise ValueError("DOJO_POSITION_DESCRIPTOR_DECODE_FAILED")
    return image


def tracker_payload(tracker: VisualPositionTracker) -> dict[str, Any]:
    snapshot = tracker.snapshot()
    return {
        "version": 1,
        "saved_at": time.time(),
        "position": {
            "x": snapshot.x,
            "y": snapshot.y,
            "confidence": snapshot.confidence,
            "state": snapshot.state.value,
            "anchored": snapshot.anchored,
            "mode": tracker.mode,
            "cell_size": tracker.cell_size,
        },
        "keyframes": [
            {
                "id": item.keyframe_id,
                "x": item.x,
                "y": item.y,
                "created_at": item.created_at,
                "quality": item.quality,
                "mode": item.mode,
                "origin": item.origin,
                "descriptor_png_base64": _descriptor_base64(item.descriptor),
            }
            for item in tracker.keyframes
        ],
    }


def save_tracker_state(tracker: VisualPositionTracker, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(tracker_payload(tracker), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def restore_tracker_state(
    tracker: VisualPositionTracker,
    path: str | Path,
    *,
    delete_after_load: bool = False,
) -> bool:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        position = payload.get("position")
        if not isinstance(position, dict):
            raise ValueError("DOJO_POSITION_STATE_INVALID")
        tracker.x = float(position.get("x", 0.0) or 0.0)
        tracker.y = float(position.get("y", 0.0) or 0.0)
        tracker.confidence = max(0.0, min(1.0, float(position.get("confidence", 0.0) or 0.0)))
        tracker.state = PositionState(str(position.get("state") or "LOST").upper())
        tracker.anchored = bool(position.get("anchored"))
        tracker.mode = str(position.get("mode") or "-")
        cell_size = float(position.get("cell_size", 32.0) or 32.0)
        if cell_size not in {32.0, 64.0}:
            cell_size = 32.0
        tracker.cell_size = cell_size
        tracker.odometry.cell_size = cell_size
        keyframes: list[VisualKeyframe] = []
        for value in payload.get("keyframes") or []:
            if not isinstance(value, dict):
                continue
            keyframes.append(
                VisualKeyframe(
                    keyframe_id=int(value.get("id", len(keyframes) + 1)),
                    x=float(value.get("x", 0.0) or 0.0),
                    y=float(value.get("y", 0.0) or 0.0),
                    descriptor=_decode_descriptor(str(value.get("descriptor_png_base64") or "")),
                    created_at=float(value.get("created_at", 0.0) or 0.0),
                    quality=max(0.0, min(1.0, float(value.get("quality", 0.0) or 0.0))),
                    mode=str(value.get("mode") or tracker.mode),
                    origin=bool(value.get("origin")),
                )
            )
        tracker._keyframes = keyframes
        tracker._next_keyframe_id = max((item.keyframe_id for item in keyframes), default=0) + 1
        tracker._last_keyframe_position = (
            (keyframes[-1].x, keyframes[-1].y) if keyframes else None
        )
        tracker.odometry.reset()
        return tracker.anchored
    except Exception:
        tracker.x = 0.0
        tracker.y = 0.0
        tracker.confidence = 0.0
        tracker.state = PositionState.LOST
        tracker.anchored = False
        tracker.odometry.reset()
        return False
    finally:
        if delete_after_load:
            try:
                source.unlink(missing_ok=True)
            except Exception:
                pass


class DojoAnchorMonitor:
    """Capture the click-time Trainer anchor and follow the dialog/spawn transition.

    The monitor does not click, move, change thresholds, or alter dialog behavior. It runs beside
    the validated request function, buffers compressed frames until that function confirms its
    click, then retroactively anchors the matching frame and replays all following observations.
    """

    def __init__(
        self,
        *,
        leader_threshold: float = 0.88,
        capture_hz: float = 10.0,
        buffer_seconds: float = 20.0,
        telemetry: Telemetry | None = None,
        source=None,
    ) -> None:
        self.telemetry = telemetry
        self.capture_interval = 1.0 / max(2.0, min(20.0, float(capture_hz)))
        capacity = max(20, int(max(5.0, float(buffer_seconds)) / self.capture_interval))
        self._frames: deque[_BufferedFrame] = deque(maxlen=capacity)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sequence = 0
        self._owns_source = source is None
        self.source = source or WindowsGameFrameSource()
        config = V03ObserverConfig(
            player_x=0.5181,
            player_y=0.4706,
            player_exclusion_radius=19.0,
            player_box_width=18.0,
            player_box_height=38.0,
            dynamic_background_enabled=True,
        ).normalized()
        self.observer = ParticleSafeGridTargetObserver(
            config,
            tile_size=32.0,
            contact_lock_seconds=2.8,
            show_grid=False,
            contact_confirm_frames=2,
        )
        self.detector = UserDojoLeaderDetector(threshold=leader_threshold)
        self.tracker = VisualPositionTracker(cell_size=32.0, telemetry=self._emit)
        self._click_confirmed = False

    def _emit(self, event: str, fields: dict[str, object]) -> None:
        if self.telemetry is not None:
            try:
                self.telemetry(event, fields)
            except Exception:
                pass

    @staticmethod
    def _compress(frame: np.ndarray) -> bytes:
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not ok:
            raise RuntimeError("DOJO_ANCHOR_FRAME_ENCODE_FAILED")
        return bytes(encoded)

    @staticmethod
    def _bbox_distance(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = first
        bx, by, bw, bh = second
        ac = (ax + aw * 0.5, ay + ah * 0.5)
        bc = (bx + bw * 0.5, by + bh * 0.5)
        size_penalty = abs(aw - bw) + abs(ah - bh)
        return float(np.hypot(ac[0] - bc[0], ac[1] - bc[1]) + size_penalty * 0.5)

    def capture_once(self) -> None:
        capture = self.source.capture()
        frame = decode_jpeg(bytes(capture.jpeg))
        state = self.observer.process(frame)
        match = self.detector.find(frame, arena_rect=state.arena_rect, now=time.monotonic())
        flow = getattr(state, "global_flow", None)
        value = _BufferedFrame(
            sequence=self._sequence,
            captured_at=time.monotonic(),
            jpeg=self._compress(frame),
            arena_rect=tuple(int(item) for item in state.arena_rect),
            player_center=tuple(float(item) for item in state.player_center),
            flow_dx=float(getattr(flow, "dx", 0.0) or 0.0),
            flow_dy=float(getattr(flow, "dy", 0.0) or 0.0),
            flow_points=int(getattr(flow, "points", 0) or 0),
            trainer_bbox=(tuple(int(item) for item in match.bbox) if match is not None and match.source == "visual" else None),
            trainer_score=(float(match.score) if match is not None and match.source == "visual" else 0.0),
            trainer_mode=(
                str(getattr(self.detector, "last_accepted_template_mode", "-") or "-")
                if match is not None and match.source == "visual"
                else "-"
            ),
        )
        self._sequence += 1
        with self._lock:
            self._frames.append(value)
            if self.tracker.anchored:
                self.tracker.observe(frame, value.observer_state())

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.capture_once()
            except Exception as error:
                self._emit(
                    "DOJO_ANCHOR_MONITOR_CAPTURE_FAILED",
                    {"error": f"{type(error).__name__}:{error}"},
                )
            remaining = self.capture_interval - (time.monotonic() - started)
            self._stop.wait(max(0.01, remaining))

    def start(self) -> "DojoAnchorMonitor":
        if self._thread is not None and self._thread.is_alive():
            return self
        try:
            self.capture_once()
        except Exception:
            pass
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="DojoAnchorMonitor", daemon=True)
        self._thread.start()
        self._emit("DOJO_ANCHOR_MONITOR_STARTED", {"buffer_frames": self._frames.maxlen})
        return self

    def confirm_click(self, click_target) -> bool:
        wanted_bbox = tuple(int(item) for item in click_target.bbox)
        with self._lock:
            candidates = [item for item in self._frames if item.trainer_bbox is not None]
            if not candidates:
                self._emit("DOJO_ANCHOR_CONFIRM_FAILED", {"reason": "no_visual_candidate"})
                return False
            candidate = min(
                candidates,
                key=lambda item: (
                    self._bbox_distance(item.trainer_bbox or wanted_bbox, wanted_bbox),
                    -item.sequence,
                ),
            )
            frame = candidate.frame()
            state = candidate.observer_state()
            mode = candidate.trainer_mode if candidate.trainer_mode in {"32", "64"} else "32"
            cell_size = float(mode)
            self.tracker.cell_size = cell_size
            self.tracker.odometry.cell_size = cell_size
            self.tracker.set_anchor(frame, state, mode=mode)
            for item in self._frames:
                if item.sequence <= candidate.sequence:
                    continue
                self.tracker.observe(item.frame(), item.observer_state())
            self._click_confirmed = True
            snapshot = self.tracker.snapshot()
            self._emit(
                "DOJO_CLICK_ANCHOR_CONFIRMED",
                {
                    "mode": mode,
                    "score": f"{candidate.trainer_score:.3f}",
                    "x": f"{snapshot.x:.4f}",
                    "y": f"{snapshot.y:.4f}",
                    "state": snapshot.state.value,
                    "confidence": f"{snapshot.confidence:.3f}",
                },
            )
            return True

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        if self._owns_source:
            try:
                self.source.close()
            except Exception:
                pass
        self._emit("DOJO_ANCHOR_MONITOR_STOPPED", {})

    def stop_and_save(self, path: str | Path) -> Path | None:
        self.stop()
        if not self._click_confirmed or not self.tracker.anchored:
            self._emit("DOJO_POSITION_BRIDGE_SKIPPED", {"reason": "anchor_not_confirmed"})
            return None
        destination = save_tracker_state(self.tracker, path)
        snapshot = self.tracker.snapshot()
        self._emit(
            "DOJO_POSITION_BRIDGE_SAVED",
            {
                "path": str(destination),
                "x": f"{snapshot.x:.4f}",
                "y": f"{snapshot.y:.4f}",
                "state": snapshot.state.value,
                "keyframes": snapshot.keyframes,
            },
        )
        return destination


__all__ = [
    "DojoAnchorMonitor",
    "restore_tracker_state",
    "save_tracker_state",
    "tracker_payload",
]
