from __future__ import annotations

"""Invisible one-video-per-round visual recorder for the Dojo runtime.

This module deliberately has no Tkinter, no desktop UI, no overlay and no second
capture source. It wraps the exact observer used by ``KagePilotRound.exe`` and
records the frame already delivered to the combat code after that same iteration
has produced raw contour candidates, tracked candidates and a confirmed target
lock.
"""

import atexit
from datetime import datetime
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Callable, Iterable

import cv2
import numpy as np


_VIDEO_WIDTH = 1280
_VIDEO_HEIGHT = 720
_MAIN_WIDTH = 960
_MAIN_HEIGHT = 540
_SIDE_WIDTH = 320
_SIDE_HEIGHT = 180
_METADATA_HEIGHT = 180
_DEFAULT_FPS = 8.0


Telemetry = Callable[[str, dict[str, object]], None]
WriterFactory = Callable[..., Any]


def round_video_root() -> Path:
    local = str(os.getenv("LOCALAPPDATA") or "").strip()
    base = Path(local) if local else Path.home() / ".kagelink"
    return base / "KageLink" / "dojo_round_videos"


def _argument_value(name: str, argv: Iterable[str] | None = None) -> str:
    values = list(sys.argv if argv is None else argv)
    for index, item in enumerate(values):
        text = str(item)
        if text == name and index + 1 < len(values):
            return str(values[index + 1])
        if text.startswith(name + "="):
            return text.split("=", 1)[1]
    return ""


def round_number_from_argv(argv: Iterable[str] | None = None) -> int | None:
    values = list(sys.argv if argv is None else argv)
    log_value = _argument_value("--log", values)
    search_text = " ".join([log_value, *map(str, values)])
    match = re.search(r"(?:^|[\\/_-])round[_-]?(\d+)(?:\D|$)", search_text, re.IGNORECASE)
    if match is None:
        return None
    try:
        return max(1, int(match.group(1)))
    except (TypeError, ValueError):
        return None


def fps_from_argv(argv: Iterable[str] | None = None) -> float:
    value = _argument_value("--fps", argv)
    try:
        fps = float(value) if value else _DEFAULT_FPS
    except (TypeError, ValueError):
        fps = _DEFAULT_FPS
    return max(1.0, min(20.0, fps))


def _bgr(image: np.ndarray | None, *, width: int = 320, height: int = 180) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.size == 0:
        return np.zeros((height, width, 3), dtype=np.uint8)
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image[:, :, :3].copy()


def _fit(image: np.ndarray | None, width: int, height: int) -> np.ndarray:
    source = _bgr(image, width=width, height=height)
    source_height, source_width = source.shape[:2]
    scale = min(width / max(1, source_width), height / max(1, source_height))
    target_width = max(1, int(round(source_width * scale)))
    target_height = max(1, int(round(source_height * scale)))
    resized = cv2.resize(
        source,
        (target_width, target_height),
        interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_NEAREST,
    )
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    x = (width - target_width) // 2
    y = (height - target_height) // 2
    canvas[y : y + target_height, x : x + target_width] = resized
    return canvas


def _text(
    image: np.ndarray,
    value: object,
    x: int,
    y: int,
    *,
    scale: float = 0.43,
    thickness: int = 1,
    color: tuple[int, int, int] = (245, 245, 245),
) -> None:
    text = str(value or "-")
    cv2.putText(
        image,
        text,
        (int(x), int(y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        float(scale),
        (0, 0, 0),
        max(2, int(thickness) + 2),
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        (int(x), int(y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        float(scale),
        color,
        max(1, int(thickness)),
        cv2.LINE_AA,
    )


def _panel(title: str, image: np.ndarray | None) -> np.ndarray:
    result = _fit(image, _SIDE_WIDTH, _SIDE_HEIGHT)
    cv2.rectangle(result, (0, 0), (_SIDE_WIDTH - 1, 23), (12, 16, 13), -1)
    _text(result, title, 7, 17, scale=0.40)
    return result


def _arena_rect(frame: np.ndarray, state: Any) -> tuple[int, int, int, int]:
    height, width = frame.shape[:2]
    value = getattr(state, "arena_rect", (0, 0, width, height))
    try:
        x0, y0, x1, y1 = (int(round(float(item))) for item in value)
    except Exception:
        return 0, 0, width, height
    x0 = max(0, min(width - 1, x0))
    y0 = max(0, min(height - 1, y0))
    x1 = max(x0 + 1, min(width, x1))
    y1 = max(y0 + 1, min(height, y1))
    return x0, y0, x1, y1


def _candidate_box(candidate: Any) -> tuple[int, int, int, int] | None:
    value = getattr(candidate, "bbox", None)
    try:
        x, y, width, height = (int(round(float(item))) for item in value)
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _tracker_context(observer: Any, track_id: int) -> str:
    tracker = getattr(observer, "tracker", None)
    context_for = getattr(tracker, "context_for", None)
    if not callable(context_for):
        return "-"
    try:
        context = context_for(int(track_id))
        return str(getattr(context, "state", "-") or "-")
    except Exception:
        return "-"


def _grid_distance(observer: Any, track_id: int) -> str:
    metrics_for = getattr(observer, "metrics_for", None)
    if not callable(metrics_for):
        return "-"
    try:
        metrics = metrics_for(int(track_id))
        value = getattr(metrics, "grid_distance", None)
        return "-" if value is None else str(int(value))
    except Exception:
        return "-"


def _active_recovery_engine() -> Any | None:
    try:
        import kage_pilot_live_v03e_round as round_runtime

        return getattr(round_runtime, "_ACTIVE_RECOVERY_ENGINE", None)
    except Exception:
        return None


def _trainer_snapshot(engine: Any, *, timestamp: float) -> dict[str, object]:
    detector = getattr(engine, "leader_detector", None) if engine is not None else None
    if detector is None:
        return {
            "box": None,
            "fresh": False,
            "score": -1.0,
            "raw_score": -1.0,
            "threshold": 0.0,
            "mode": "-",
            "scale": 0.0,
            "rejection": "-",
            "state": "-",
        }
    match = getattr(detector, "_last_visual", None)
    seen_at = float(getattr(detector, "_last_visual_at", -1e9) or -1e9)
    fresh = match is not None and (
        seen_at <= -1e8 or abs(float(timestamp) - seen_at) <= 1.20
    )
    box = _candidate_box(match) if fresh else None
    return {
        "box": box,
        "fresh": bool(fresh),
        "score": float(getattr(match, "score", -1.0) or -1.0) if match is not None else -1.0,
        "raw_score": float(getattr(detector, "last_raw_score", -1.0) or -1.0),
        "threshold": float(getattr(detector, "threshold", 0.0) or 0.0),
        "mode": str(
            getattr(detector, "last_accepted_template_mode", None)
            or getattr(detector, "last_raw_template_mode", None)
            or getattr(detector, "active_scan_mode", "-")
            or "-"
        ),
        "scale": float(getattr(detector, "last_raw_scale", 0.0) or 0.0),
        "rejection": str(getattr(detector, "last_rejection_reason", "-") or "-"),
        "state": str(getattr(engine, "state", "-") or "-"),
    }


def _draw_grid(arena: np.ndarray, observer: Any) -> np.ndarray:
    result = arena.copy()
    height, width = result.shape[:2]
    cell = max(4.0, float(getattr(observer, "tile_size", 32.0) or 32.0))
    origin_x = float(getattr(observer, "grid_origin_x", 0.0) or 0.0) % cell
    origin_y = float(getattr(observer, "grid_origin_y", 0.0) or 0.0) % cell
    value = origin_x
    while value < width:
        x = int(round(value))
        cv2.line(result, (x, 0), (x, height - 1), (80, 80, 80), 1)
        value += cell
    value = origin_y
    while value < height:
        y = int(round(value))
        cv2.line(result, (0, y), (width - 1, y), (80, 80, 80), 1)
        value += cell
    return result


def render_round_frame(
    frame_bgr: np.ndarray,
    state: Any,
    observer: Any,
    *,
    raw_candidates: Iterable[Any] = (),
    engine: Any | None = None,
    round_number: int | None = None,
    sequence: int = 0,
    elapsed: float = 0.0,
) -> np.ndarray:
    """Create one 1280×720 diagnostic frame from the exact observer input."""

    frame = _bgr(frame_bgr, width=_MAIN_WIDTH, height=_MAIN_HEIGHT)
    x0, y0, x1, y1 = _arena_rect(frame, state)
    arena = frame[y0:y1, x0:x1].copy()
    annotated = frame.copy()
    cv2.rectangle(annotated, (x0, y0), (x1 - 1, y1 - 1), (80, 190, 80), 1)

    timestamp = float(getattr(state, "timestamp", time.monotonic()) or time.monotonic())
    target_id = getattr(state, "target_id", None)
    locked_id = getattr(observer, "_locked_target_id", None)
    grid_target_id = getattr(observer, "_grid_target_id", None)
    target_mode = str(getattr(observer, "target_mode", "-") or "-")
    contact_until = float(getattr(observer, "_contact_latch_until", 0.0) or 0.0)
    contact_active = timestamp <= contact_until

    candidate_rows: list[str] = []
    for index, candidate in enumerate(tuple(raw_candidates or ())):
        box = _candidate_box(candidate)
        if box is None:
            continue
        x, y, width, height = box
        cv2.rectangle(
            annotated,
            (x0 + x, y0 + y),
            (x0 + x + width, y0 + y + height),
            (230, 130, 40),
            1,
        )
        if index < 24:
            _text(
                annotated,
                f"C{index + 1}",
                x0 + x,
                max(13, y0 + y - 2),
                scale=0.31,
                color=(240, 180, 80),
            )

    tracks = tuple(getattr(state, "tracks", ()) or ())
    for track in tracks:
        box = _candidate_box(track)
        if box is None:
            continue
        x, y, width, height = box
        track_id = int(getattr(track, "track_id", 0) or 0)
        score = float(getattr(track, "enemy_score", 0.0) or 0.0)
        context = _tracker_context(observer, track_id)
        distance = _grid_distance(observer, track_id)
        is_lock = track_id in {target_id, locked_id, grid_target_id}
        is_contact = is_lock and contact_active
        if is_contact:
            color = (20, 40, 245)
            label = f"CONTACT LOCK #{track_id} score={score:.0f} d={distance} {context}"
            thickness = 3
        elif is_lock:
            color = (20, 225, 245)
            label = f"LOCK #{track_id} score={score:.0f} d={distance} {context}"
            thickness = 3
        else:
            color = (65, 210, 90)
            label = f"TRACK #{track_id} score={score:.0f} d={distance} {context}"
            thickness = 1
        cv2.rectangle(
            annotated,
            (x0 + x, y0 + y),
            (x0 + x + width, y0 + y + height),
            color,
            thickness,
        )
        _text(
            annotated,
            label,
            x0 + x,
            max(14, y0 + y - 3),
            scale=0.32,
            color=color,
        )
        candidate_rows.append(label)

    player = tuple(getattr(state, "player_center", ()) or ())
    if len(player) == 2:
        px = x0 + int(round(float(player[0])))
        py = y0 + int(round(float(player[1])))
        cv2.circle(annotated, (px, py), 8, (245, 225, 50), 2)
        _text(annotated, "PLAYER", px + 10, py - 8, scale=0.35, color=(245, 225, 50))

    trainer = _trainer_snapshot(engine, timestamp=timestamp)
    trainer_box = trainer.get("box")
    if isinstance(trainer_box, tuple) and len(trainer_box) == 4:
        tx, ty, width, height = trainer_box
        cv2.rectangle(
            annotated,
            (int(tx), int(ty)),
            (int(tx + width), int(ty + height)),
            (235, 60, 220),
            3,
        )
        _text(
            annotated,
            f"TRAINER LOCK score={float(trainer['score']):.3f} mode={trainer['mode']}",
            int(tx),
            max(14, int(ty) - 4),
            scale=0.34,
            color=(245, 90, 230),
        )

    contrast = getattr(observer, "_previous_gray", None)
    if not isinstance(contrast, np.ndarray) or contrast.size == 0:
        gray = cv2.cvtColor(arena, cv2.COLOR_BGR2GRAY)
        contrast = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8)).apply(gray)
    motion = getattr(state, "motion_mask", None)
    if not isinstance(motion, np.ndarray) or motion.size == 0:
        motion = np.zeros(contrast.shape[:2], dtype=np.uint8)

    processed_arena = _draw_grid(arena, observer)
    for track in tracks:
        box = _candidate_box(track)
        if box is None:
            continue
        x, y, width, height = box
        track_id = int(getattr(track, "track_id", 0) or 0)
        color = (20, 225, 245) if track_id == target_id else (65, 210, 90)
        cv2.rectangle(
            processed_arena,
            (x, y),
            (x + width, y + height),
            color,
            2 if track_id == target_id else 1,
        )

    canvas = np.zeros((_VIDEO_HEIGHT, _VIDEO_WIDTH, 3), dtype=np.uint8)
    canvas[0:_MAIN_HEIGHT, 0:_MAIN_WIDTH] = _fit(
        annotated,
        _MAIN_WIDTH,
        _MAIN_HEIGHT,
    )
    canvas[0:_SIDE_HEIGHT, _MAIN_WIDTH:_VIDEO_WIDTH] = _panel("CONTRAST / POS-TRATAMENTO", contrast)
    canvas[_SIDE_HEIGHT : _SIDE_HEIGHT * 2, _MAIN_WIDTH:_VIDEO_WIDTH] = _panel(
        "MOTION MASK / MASCARA",
        motion,
    )
    canvas[_SIDE_HEIGHT * 2 : _MAIN_HEIGHT, _MAIN_WIDTH:_VIDEO_WIDTH] = _panel(
        "GRID + TRACKS PROCESSADOS",
        processed_arena,
    )

    metadata = canvas[_MAIN_HEIGHT:_VIDEO_HEIGHT, :]
    cv2.rectangle(metadata, (0, 0), (_VIDEO_WIDTH - 1, _METADATA_HEIGHT - 1), (9, 12, 10), -1)
    flow = getattr(state, "global_flow", None)
    flow_dx = float(getattr(flow, "dx", 0.0) or 0.0)
    flow_dy = float(getattr(flow, "dy", 0.0) or 0.0)
    flow_points = int(getattr(flow, "points", 0) or 0)
    cell_size = float(getattr(observer, "tile_size", 32.0) or 32.0)
    active_cells = int(getattr(observer, "active_grid_cells", 0) or 0)
    round_text = "?" if round_number is None else str(round_number)
    lines = (
        f"ROUND {round_text}  FRAME {sequence}  ELAPSED {elapsed:.2f}s  INPUT {frame.shape[1]}x{frame.shape[0]}",
        f"RAW CANDIDATES {len(tuple(raw_candidates or ()))}  TRACKS {len(tracks)}  TARGET {target_id or '-'}  MODE {target_mode}",
        f"GRID cell={cell_size:.2f}px active_cells={active_cells} contact_latch={'ON' if contact_active else 'OFF'}",
        f"FLOW dx={flow_dx:.2f} dy={flow_dy:.2f} points={flow_points}",
        (
            "TRAINER "
            f"state={trainer['state']} fresh={str(bool(trainer['fresh'])).lower()} "
            f"raw={float(trainer['raw_score']):.3f} need={float(trainer['threshold']):.3f} "
            f"mode={trainer['mode']} scale={float(trainer['scale']):.3f}"
        ),
        f"TRAINER rejection={trainer['rejection']}",
    )
    for index, line in enumerate(lines):
        _text(metadata, line, 12, 23 + index * 25, scale=0.42)

    _text(metadata, "BLUE=CANDIDATE  GREEN=TRACK  YELLOW=LOCK  RED=CONTACT LOCK  MAGENTA=TRAINER", 650, 23, scale=0.37)
    for index, row in enumerate(candidate_rows[:10]):
        column = 0 if index < 5 else 1
        row_index = index if index < 5 else index - 5
        _text(
            metadata,
            row[:68],
            650 + column * 310,
            49 + row_index * 25,
            scale=0.34,
        )
    return canvas


class RoundVideoRecorder:
    """Write exactly one AVI file for one isolated round process."""

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        round_number: int | None = None,
        fps: float | None = None,
        telemetry: Telemetry | None = None,
        writer_factory: WriterFactory | None = None,
    ) -> None:
        self.root = Path(root) if root is not None else round_video_root()
        self.round_number = round_number if round_number is not None else round_number_from_argv()
        self.fps = max(1.0, min(20.0, float(fps if fps is not None else fps_from_argv())))
        self.telemetry = telemetry
        self.writer_factory = writer_factory or cv2.VideoWriter
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        label = "round_unknown" if self.round_number is None else f"round_{self.round_number:03d}"
        self.path = self.root / f"{label}_{stamp}_{os.getpid()}.avi"
        self._writer: Any | None = None
        self._lock = threading.RLock()
        self._closed = False
        self._started_at = time.monotonic()
        self.frames = 0
        self.last_error = ""

    def _emit(self, event: str, fields: dict[str, object]) -> None:
        if self.telemetry is not None:
            try:
                self.telemetry(event, fields)
                return
            except Exception:
                pass
        suffix = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
        print(f"{event}{(' ' + suffix) if suffix else ''}")

    def _open_writer(self) -> bool:
        if self._writer is not None:
            try:
                return bool(self._writer.isOpened())
            except Exception:
                return True
        self.root.mkdir(parents=True, exist_ok=True)
        codecs = ("MJPG", "XVID")
        for codec in codecs:
            try:
                writer = self.writer_factory(
                    str(self.path),
                    cv2.VideoWriter_fourcc(*codec),
                    self.fps,
                    (_VIDEO_WIDTH, _VIDEO_HEIGHT),
                )
                opened = bool(writer.isOpened()) if hasattr(writer, "isOpened") else True
                if opened:
                    self._writer = writer
                    self._emit(
                        "DOJO_ROUND_VIDEO_READY",
                        {
                            "path": str(self.path),
                            "round": self.round_number or "-",
                            "fps": f"{self.fps:.1f}",
                            "codec": codec,
                            "size": f"{_VIDEO_WIDTH}x{_VIDEO_HEIGHT}",
                        },
                    )
                    return True
                try:
                    writer.release()
                except Exception:
                    pass
            except Exception as error:
                self.last_error = f"{type(error).__name__}:{error}"
        self._emit(
            "DOJO_ROUND_VIDEO_OPEN_FAILED",
            {"path": str(self.path), "error": self.last_error or "VIDEO_WRITER_NOT_OPEN"},
        )
        return False

    def record(
        self,
        frame_bgr: np.ndarray,
        state: Any,
        observer: Any,
        *,
        raw_candidates: Iterable[Any] = (),
        engine: Any | None = None,
    ) -> bool:
        with self._lock:
            if self._closed:
                return False
            try:
                output = render_round_frame(
                    frame_bgr,
                    state,
                    observer,
                    raw_candidates=tuple(raw_candidates or ()),
                    engine=engine,
                    round_number=self.round_number,
                    sequence=self.frames + 1,
                    elapsed=max(0.0, time.monotonic() - self._started_at),
                )
                if not self._open_writer():
                    return False
                self._writer.write(output)
                self.frames += 1
                return True
            except Exception as error:
                self.last_error = f"{type(error).__name__}:{error}"
                self._emit(
                    "DOJO_ROUND_VIDEO_FRAME_FAILED",
                    {"frame": self.frames + 1, "error": self.last_error},
                )
                return False

    def close(self, reason: str = "runtime_exit") -> Path | None:
        with self._lock:
            if self._closed:
                return self.path if self.frames > 0 else None
            self._closed = True
            writer = self._writer
            self._writer = None
        if writer is not None:
            try:
                writer.release()
            except Exception as error:
                self.last_error = f"{type(error).__name__}:{error}"
        if self.frames <= 0:
            try:
                self.path.unlink(missing_ok=True)
            except Exception:
                pass
            self._emit(
                "DOJO_ROUND_VIDEO_SKIPPED",
                {"round": self.round_number or "-", "reason": reason, "frames": 0},
            )
            return None
        self._emit(
            "DOJO_ROUND_VIDEO_CLOSED",
            {
                "path": str(self.path),
                "round": self.round_number or "-",
                "frames": self.frames,
                "reason": reason,
                "error": self.last_error or "-",
            },
        )
        return self.path


_CAPTURE_LOCAL = threading.local()
_ACTIVE_RECORDER: RoundVideoRecorder | None = None


def install_runtime_lab(runtime: Any) -> RoundVideoRecorder:
    """Install the invisible recorder inside the isolated round runtime only.

    The historical function name is retained to avoid changing packaged entry
    points. Its implementation no longer exposes a lab, files of intermediate
    stages, a desktop tab or any window.
    """

    global _ACTIVE_RECORDER
    existing = getattr(runtime, "_kagelink_round_video_recorder", None)
    if isinstance(existing, RoundVideoRecorder):
        return existing

    import kage_pilot_live_v03 as live_runtime
    from . import entity_observer as observer_module

    observer_type = live_runtime.ParticleSafeGridTargetObserver
    recorder = RoundVideoRecorder(telemetry=getattr(runtime, "_telemetry", None))
    _ACTIVE_RECORDER = recorder

    original_detect_candidates = observer_module.detect_candidates
    original_process = observer_type.process
    original_main = runtime.main

    def capture_candidates(*args, **kwargs):
        candidates, motion_mask = original_detect_candidates(*args, **kwargs)
        _CAPTURE_LOCAL.candidates = tuple(candidates or ())
        return candidates, motion_mask

    def process_with_round_video(self, frame_bgr, *, timestamp=None):
        _CAPTURE_LOCAL.candidates = ()
        state = original_process(self, frame_bgr, timestamp=timestamp)
        candidates = tuple(getattr(_CAPTURE_LOCAL, "candidates", ()) or ())
        recorder.record(
            frame_bgr,
            state,
            self,
            raw_candidates=candidates,
            engine=_active_recovery_engine(),
        )
        return state

    def main_with_round_video(*args, **kwargs):
        try:
            return original_main(*args, **kwargs)
        finally:
            recorder.close("runtime_exit")

    observer_module.detect_candidates = capture_candidates
    observer_type.process = process_with_round_video
    runtime.main = main_with_round_video
    runtime._kagelink_round_video_recorder = recorder
    observer_type._kagelink_round_video_installed = True
    atexit.register(recorder.close, "process_exit")

    recorder._emit(
        "DOJO_ROUND_VIDEO_BRIDGE_INSTALLED",
        {
            "round": recorder.round_number or "-",
            "path": str(recorder.path),
            "ui": "none",
            "overlay": "none",
            "capture": "observer-input",
        },
    )
    return recorder


__all__ = [
    "RoundVideoRecorder",
    "fps_from_argv",
    "install_runtime_lab",
    "render_round_frame",
    "round_number_from_argv",
    "round_video_root",
]
