from __future__ import annotations

import atexit
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any

import cv2
import numpy as np

from .post_combat_v03 import HudResourceReader


@dataclass(frozen=True, slots=True)
class VisionLabSettings:
    enabled: bool = True
    fps: float = 6.0
    record_video: bool = True
    save_stages: bool = True
    stage_interval: float = 1.0
    jpeg_quality: int = 88

    def normalized(self):
        return replace(
            self,
            enabled=bool(self.enabled),
            fps=max(1.0, min(15.0, float(self.fps))),
            record_video=bool(self.record_video),
            save_stages=bool(self.save_stages),
            stage_interval=max(0.25, min(10.0, float(self.stage_interval))),
            jpeg_quality=max(55, min(96, int(self.jpeg_quality))),
        )

    def to_dict(self):
        return asdict(self.normalized())

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            return cls()
        default = cls()

        def num(key, fallback):
            try:
                return float(data.get(key, fallback))
            except (TypeError, ValueError):
                return fallback

        def flag(key, fallback):
            value = data.get(key, fallback)
            return value if isinstance(value, bool) else fallback

        return cls(
            enabled=flag("enabled", default.enabled),
            fps=num("fps", default.fps),
            record_video=flag("record_video", default.record_video),
            save_stages=flag("save_stages", default.save_stages),
            stage_interval=num("stage_interval", default.stage_interval),
            jpeg_quality=int(num("jpeg_quality", default.jpeg_quality)),
        ).normalized()


def vision_lab_root() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".kagelink"))
    return base / "KageLink" / "dojo_vision_lab"


def read_settings(path: str | Path | None = None) -> VisionLabSettings:
    source = Path(path) if path else vision_lab_root() / "control.json"
    try:
        return VisionLabSettings.from_dict(json.loads(source.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError):
        return VisionLabSettings()


def write_settings(settings: VisionLabSettings, path: str | Path | None = None) -> Path:
    target = Path(path) if path else vision_lab_root() / "control.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(
        json.dumps(settings.normalized().to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(target)
    return target


def _safe(value: str, fallback="session"):
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return cleaned[:72] or fallback


def _round_label():
    match = re.search(r"round[_-]?(\d+)", " ".join(map(str, sys.argv)), re.I)
    return f"round_{int(match.group(1)):03d}" if match else "round_unknown"


def _jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return str(value)


def _atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp.write_bytes(data)
    temp.replace(path)


def _write_json(path: Path, data):
    payload = (json.dumps(_jsonable(data), ensure_ascii=False, indent=2) + "\n").encode()
    _atomic(path, payload)


def _jpg(image, quality=88):
    ok, data = cv2.imencode(
        ".jpg",
        image,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
    )
    return bytes(data) if ok else None


def _bgr(image, shape=(180, 320)):
    if not isinstance(image, np.ndarray) or image.size == 0:
        return np.zeros((shape[0], shape[1], 3), np.uint8)
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image[:, :, :3].copy()


def _fit(image, width=320, height=180):
    source = _bgr(image, (height, width))
    source_height, source_width = source.shape[:2]
    scale = min(width / max(1, source_width), height / max(1, source_height))
    size = (
        max(1, round(source_width * scale)),
        max(1, round(source_height * scale)),
    )
    resized = cv2.resize(
        source,
        size,
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_NEAREST,
    )
    canvas = np.zeros((height, width, 3), np.uint8)
    x = (width - size[0]) // 2
    y = (height - size[1]) // 2
    canvas[y : y + size[1], x : x + size[0]] = resized
    return canvas


def _text(image, value, x, y, scale=0.42):
    text = str(value or "-")
    cv2.putText(
        image,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (0, 0, 0),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (245, 245, 245),
        1,
        cv2.LINE_AA,
    )


def _tile(name, image):
    panel = _fit(image)
    cv2.rectangle(panel, (0, 0), (319, 22), (12, 16, 13), -1)
    _text(panel, name.upper().replace("_", " "), 7, 16)
    return panel


def _arena(frame, state):
    height, width = frame.shape[:2]
    value = getattr(state, "arena_rect", (0, 0, width, height))
    x0, y0, x1, y1 = [int(round(float(item))) for item in value]
    x0 = max(0, min(width - 1, x0))
    y0 = max(0, min(height - 1, y0))
    return (
        x0,
        y0,
        max(x0 + 1, min(width, x1)),
        max(y0 + 1, min(height, y1)),
    )


def _roi(frame, region):
    height, width = frame.shape[:2]
    x, y, region_width, region_height = region
    x0 = max(0, round(x * width))
    y0 = max(0, round(y * height))
    x1 = min(width, max(x0 + 1, round((x + region_width) * width)))
    y1 = min(height, max(y0 + 1, round((y + region_height) * height)))
    return frame[y0:y1, x0:x1].copy()


def _decision(decision):
    if decision is None:
        return {
            "state": "TRAINER_ACQUISITION",
            "action": "hold",
            "reason": "waiting for Trainer",
            "hp": None,
            "chakra": None,
        }
    state = getattr(decision, "state", None) or f"COMBAT_{getattr(decision, 'mode', '-')}"
    action = getattr(decision, "action", None) or (
        "V"
        if getattr(decision, "tap_v", False)
        else getattr(decision, "move_pulse", None)
        or getattr(decision, "navigation", None)
        or "hold"
    )
    return {
        "state": str(state),
        "action": str(action),
        "reason": str(getattr(decision, "reason", "") or ""),
        "hp": getattr(decision, "health", None),
        "chakra": getattr(decision, "chakra", None),
        "target_id": getattr(decision, "target_id", None),
        "grid_distance": getattr(decision, "grid_distance", None),
    }


def build_panels(
    frame_bgr,
    state,
    *,
    observer=None,
    detector=None,
    match=None,
    decision=None,
    source="dojo",
):
    frame = _bgr(frame_bgr)
    x0, y0, x1, y1 = _arena(frame, state)
    arena = frame[y0:y1, x0:x1].copy()
    gray = cv2.cvtColor(arena, cv2.COLOR_BGR2GRAY)

    contrast = getattr(observer, "_kagelink_debug_contrast", None)
    if not isinstance(contrast, np.ndarray) or contrast.shape != gray.shape:
        contrast = getattr(observer, "_previous_gray", None)
    if not isinstance(contrast, np.ndarray) or contrast.shape != gray.shape:
        clahe = getattr(observer, "_clahe", cv2.createCLAHE(2.4, (8, 8)))
        contrast = cv2.GaussianBlur(clahe.apply(gray), (3, 3), 0)

    motion = getattr(state, "motion_mask", None)
    if not isinstance(motion, np.ndarray):
        motion = np.zeros_like(gray)

    tracks = tuple(getattr(state, "tracks", ()) or ())
    target_id = getattr(state, "target_id", None)
    player = tuple(getattr(state, "player_center", ()) or ())
    tracked = arena.copy()
    track_rows = []
    for track in tracks:
        box = tuple(int(item) for item in (getattr(track, "bbox", ()) or ()))
        if len(box) != 4:
            continue
        x, y, box_width, box_height = box
        track_id = int(getattr(track, "track_id", 0) or 0)
        score = float(getattr(track, "enemy_score", 0) or 0)
        is_target = track_id == target_id
        cv2.rectangle(
            tracked,
            (x, y),
            (x + box_width, y + box_height),
            (20, 235, 240) if is_target else (70, 200, 90),
            2 if is_target else 1,
        )
        _text(tracked, f"#{track_id} {score:.0f}", max(0, x), max(13, y - 2), 0.35)
        track_rows.append(
            {
                "id": track_id,
                "bbox": box,
                "enemy_score": score,
                "target": is_target,
            }
        )
    if len(player) == 2:
        cv2.circle(
            tracked,
            tuple(int(round(float(item))) for item in player),
            7,
            (230, 220, 40),
            2,
        )

    scan = frame.copy()
    cv2.rectangle(scan, (x0, y0), (x1, y1), (80, 180, 80), 1)
    match_box = tuple(int(item) for item in (getattr(match, "bbox", ()) or ()))
    if len(match_box) == 4:
        x, y, box_width, box_height = match_box
        cv2.rectangle(
            scan,
            (x, y),
            (x + box_width, y + box_height),
            (20, 230, 240),
            2,
        )
    scan_mode = str(getattr(detector, "active_scan_mode", "-") or "-")
    scan_scales = [
        float(item)
        for item in tuple(getattr(detector, "active_scan_scales", ()) or ())
    ]
    raw_score = float(getattr(detector, "last_raw_score", -1) or -1)
    threshold = float(getattr(detector, "threshold", 0) or 0)
    raw_scale = float(getattr(detector, "last_raw_scale", 0) or 0)
    rejection = str(getattr(detector, "last_rejection_reason", "") or "-")
    scale_text = ",".join(f"{item:.2f}" for item in scan_scales) or "-"
    _text(scan, f"mode={scan_mode} scales={scale_text}", 8, 18)
    _text(scan, f"raw={raw_score:.3f} need={threshold:.3f} scale={raw_scale:.3f}", 8, 38)
    _text(scan, f"rejection={rejection}", 8, 58, 0.36)

    grid = arena.copy()
    cell = max(4.0, float(getattr(observer, "tile_size", 32) or 32))
    origin_x = float(getattr(observer, "grid_origin_x", 0) or 0) % cell
    origin_y = float(getattr(observer, "grid_origin_y", 0) or 0) % cell
    value = origin_x
    while value < grid.shape[1]:
        cv2.line(
            grid,
            (round(value), 0),
            (round(value), grid.shape[0]),
            (90, 90, 90),
            1,
        )
        value += cell
    value = origin_y
    while value < grid.shape[0]:
        cv2.line(
            grid,
            (0, round(value)),
            (grid.shape[1], round(value)),
            (90, 90, 90),
            1,
        )
        value += cell
    _text(grid, f"cell={cell:.2f}px origin={origin_x:.1f},{origin_y:.1f}", 7, 18)

    hud = np.zeros((180, 640, 3), np.uint8)
    hud[35:165, 5:315] = _fit(_roi(frame, HudResourceReader.HEALTH_ROI), 310, 130)
    hud[35:165, 325:635] = _fit(_roi(frame, HudResourceReader.CHAKRA_ROI), 310, 130)
    _text(hud, "HEALTH ROI", 10, 24)
    _text(hud, "CHAKRA ROI", 330, 24)

    info = _decision(decision)
    flow = getattr(state, "global_flow", None)
    flow_data = {
        "dx": float(getattr(flow, "dx", 0) or 0),
        "dy": float(getattr(flow, "dy", 0) or 0),
        "points": int(getattr(flow, "points", 0) or 0),
    }
    metadata = {
        "source": source,
        "frame_size": [frame.shape[1], frame.shape[0]],
        "arena_rect": [x0, y0, x1, y1],
        "decision": info,
        "detector": {
            "scan_mode": scan_mode,
            "scan_scales": scan_scales,
            "raw_score": raw_score,
            "threshold": threshold,
            "raw_scale": raw_scale,
            "rejection": rejection,
            "match_bbox": match_box,
        },
        "observer": {
            "cell_size": cell,
            "grid_origin": [origin_x, origin_y],
            "player_center": player,
            "target_id": target_id,
            "tracks": track_rows,
            "flow": flow_data,
        },
    }
    panels = {
        "raw": frame,
        "arena": arena,
        "gray": _bgr(gray),
        "contrast": _bgr(contrast),
        "motion_mask": _bgr(motion),
        "tracks": tracked,
        "trainer_scan": scan,
        "grid": grid,
        "hud": hud,
    }
    mosaic = np.zeros((660, 960, 3), np.uint8)
    for index, (name, image) in enumerate(panels.items()):
        row, column = divmod(index, 3)
        mosaic[
            row * 180 : (row + 1) * 180,
            column * 320 : (column + 1) * 320,
        ] = _tile(name, image)
    cv2.rectangle(mosaic, (0, 540), (959, 659), (12, 16, 13), -1)
    lines = [
        f"Source={source} State={info['state']} Action={info['action']}",
        f"Trainer raw={raw_score:.3f}/{threshold:.3f} mode={scan_mode} scale={raw_scale:.3f} reject={rejection}",
        f"Grid={cell:.2f}px Tracks={len(track_rows)} Target={target_id} Flow={flow_data}",
        f"Reason={info['reason'] or '-'}",
    ]
    for index, line in enumerate(lines):
        _text(mosaic, line[:155], 10, 565 + index * 23)
    panels["composite"] = mosaic
    return panels, metadata


class VisionLabRecorder:
    def __init__(self, source, label=None, *, root=None, settings=None):
        self.source = _safe(source, "dojo")
        self.label = _safe(label or (_round_label() if source == "round" else source))
        self.root = Path(root) if root else vision_lab_root()
        self.settings = (settings or read_settings()).normalized()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.session_id = f"{stamp}_{self.label}_{self.source}_pid{os.getpid()}"
        self.session = self.root / "sessions" / self.session_id
        self.live = self.root / "live"
        self.video = self.session / "vision_pipeline.avi"
        self.frames_file = self.session / "frames.jsonl"
        self.writer = None
        self.handle = None
        self.last_at = -1e9
        self.stage_at = -1e9
        self.seen = 0
        self.recorded = 0
        self.closed = False
        self.error = ""
        self.lock = threading.RLock()

    def _open(self, composite):
        if self.handle is not None:
            return
        self.session.mkdir(parents=True, exist_ok=True)
        (self.session / "stages").mkdir(exist_ok=True)
        self.live.mkdir(parents=True, exist_ok=True)
        self.handle = self.frames_file.open("a", encoding="utf-8", buffering=1)
        if self.settings.record_video:
            height, width = composite.shape[:2]
            writer = cv2.VideoWriter(
                str(self.video),
                cv2.VideoWriter_fourcc(*"MJPG"),
                self.settings.fps,
                (width, height),
            )
            if writer.isOpened():
                self.writer = writer
            else:
                writer.release()
                self.error = "VIDEO_WRITER_OPEN_FAILED"

    def record(
        self,
        frame,
        state,
        *,
        observer=None,
        detector=None,
        match=None,
        decision=None,
        now=None,
    ):
        self.seen += 1
        if self.closed or not self.settings.enabled:
            return False
        now = time.monotonic() if now is None else float(now)
        with self.lock:
            if now - self.last_at < 1 / self.settings.fps:
                return False
            try:
                panels, metadata = build_panels(
                    frame,
                    state,
                    observer=observer,
                    detector=detector,
                    match=match,
                    decision=decision,
                    source=self.source,
                )
                self._open(panels["composite"])
                stage_files = {}
                if self.settings.save_stages and now - self.stage_at >= self.settings.stage_interval:
                    folder = self.session / "stages" / f"frame_{self.recorded:06d}"
                    folder.mkdir(parents=True, exist_ok=True)
                    for name, image in panels.items():
                        data = _jpg(image, self.settings.jpeg_quality)
                        if data:
                            path = folder / f"{name}.jpg"
                            path.write_bytes(data)
                            stage_files[name] = str(path.relative_to(self.session)).replace("\\", "/")
                    self.stage_at = now
                if self.writer is not None:
                    self.writer.write(panels["composite"])
                row = {
                    "index": self.recorded,
                    "time": time.time(),
                    "stages": stage_files,
                    "metadata": metadata,
                }
                self.handle.write(json.dumps(_jsonable(row), ensure_ascii=False) + "\n")
                self.recorded += 1
                self.last_at = now
                for name, image in panels.items():
                    data = _jpg(image, self.settings.jpeg_quality)
                    if data:
                        _atomic(self.live / f"{name}.jpg", data)
                _write_json(
                    self.live / "status.json",
                    {
                        "active": True,
                        "enabled": True,
                        "session_id": self.session_id,
                        "source": self.source,
                        "session_dir": str(self.session),
                        "video": str(self.video) if self.writer else "",
                        "updated_at": time.time(),
                        "seen": self.seen,
                        "recorded": self.recorded,
                        "fps": self.settings.fps,
                        "error": self.error,
                        "metadata": metadata,
                    },
                )
                return True
            except Exception as error:
                self.error = f"{type(error).__name__}:{error}"
                return False

    def close(self, reason="closed"):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            if self.writer:
                self.writer.release()
                self.writer = None
            if self.handle:
                self.handle.close()
                self.handle = None
            if self.session.exists():
                _write_json(
                    self.session / "summary.json",
                    {
                        "session_id": self.session_id,
                        "source": self.source,
                        "reason": reason,
                        "seen": self.seen,
                        "recorded": self.recorded,
                        "video": self.video.name if self.video.exists() else None,
                        "error": self.error,
                        "settings": self.settings.to_dict(),
                    },
                )
            _write_json(
                self.live / "status.json",
                {
                    "active": False,
                    "enabled": self.settings.enabled,
                    "session_id": self.session_id,
                    "source": self.source,
                    "session_dir": str(self.session),
                    "video": str(self.video) if self.video.exists() else "",
                    "updated_at": time.time(),
                    "seen": self.seen,
                    "recorded": self.recorded,
                    "error": self.error,
                    "reason": reason,
                },
            )


_ACTIVE_RECORDER = None
_LATEST = {"frame": None, "state": None, "observer": None}
_CONTEXT_LOCK = threading.RLock()


def install_observer_tap():
    from .grid_target_observer_v03d import TileCalibratedGridTargetObserver

    observer_class = TileCalibratedGridTargetObserver
    if getattr(observer_class, "_vision_lab_tap", False):
        return
    original_process = observer_class.process

    def process(self, frame_bgr, *, timestamp=None):
        state = original_process(self, frame_bgr, timestamp=timestamp)
        try:
            previous = getattr(self, "_previous_gray", None)
            self._kagelink_debug_contrast = previous.copy() if isinstance(previous, np.ndarray) else None
            with _CONTEXT_LOCK:
                _LATEST.update(frame=frame_bgr.copy(), state=state, observer=self)
        except Exception:
            pass
        return state

    observer_class.process = process
    observer_class._vision_lab_tap = True


def install_combat_tap():
    from .live_control_v03 import LiveCombatControlPlanner

    planner_class = LiveCombatControlPlanner
    if getattr(planner_class, "_vision_lab_tap", False):
        return
    original_plan = planner_class.plan

    def plan(self, decision, *args, **kwargs):
        command = original_plan(self, decision, *args, **kwargs)
        with _CONTEXT_LOCK:
            recorder = _ACTIVE_RECORDER
            frame = _LATEST["frame"]
            state = _LATEST["state"]
            observer = _LATEST["observer"]
        if recorder is not None and frame is not None and state is not None:
            action = (
                "H"
                if getattr(command, "h_fire", False)
                else getattr(command, "move_pulse", None)
                or getattr(command, "face_pulse", None)
                or "+".join(getattr(command, "held_keys", ()) or ())
                or "hold"
            )
            view = SimpleNamespace(
                state=f"COMBAT_{getattr(decision, 'mode', '-')}",
                mode=getattr(decision, "mode", None),
                target_id=getattr(decision, "target_id", None),
                grid_distance=getattr(decision, "grid_distance", None),
                navigation=getattr(decision, "navigation", None),
                action=action,
                move_pulse=getattr(command, "move_pulse", None),
                reason=getattr(command, "reason", ""),
                tap_v=False,
                health=None,
                chakra=None,
            )
            recorder.record(frame, state, observer=observer, decision=view)
        return command

    planner_class.plan = plan
    planner_class._vision_lab_tap = True


def install_anchor_monitor_lab(monitor_class):
    install_observer_tap()
    if getattr(monitor_class, "_vision_lab", False):
        return
    original_init = monitor_class.__init__
    original_start = monitor_class.start
    original_capture = monitor_class.capture_once
    original_stop = monitor_class.stop

    def initialize(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._vision_lab_recorder = VisionLabRecorder("trainer_acquisition")

    def start(self):
        recorder = getattr(self, "_vision_lab_recorder", None)
        if recorder is None or recorder.closed:
            self._vision_lab_recorder = VisionLabRecorder("trainer_acquisition")
        return original_start(self)

    def capture(self):
        original_capture(self)
        with _CONTEXT_LOCK:
            frame = _LATEST["frame"]
            state = _LATEST["state"]
            observer = _LATEST["observer"]
        if frame is not None and state is not None:
            detector = getattr(self, "detector", None)
            self._vision_lab_recorder.record(
                frame,
                state,
                observer=observer,
                detector=detector,
                match=getattr(detector, "_last_visual", None),
            )

    def stop(self):
        try:
            original_stop(self)
        finally:
            self._vision_lab_recorder.close("anchor_monitor_stopped")

    monitor_class.__init__ = initialize
    monitor_class.start = start
    monitor_class.capture_once = capture
    monitor_class.stop = stop
    monitor_class._vision_lab = True


def install_runtime_lab(runtime: Any):
    global _ACTIVE_RECORDER
    install_observer_tap()
    install_combat_tap()
    engine_class = runtime.ClosedLoopVisualRecoveryEngine
    if getattr(engine_class, "_vision_lab", False):
        return engine_class
    original_init = engine_class.__init__
    original_publish = engine_class._publish_debug
    original_step = engine_class.step
    telemetry = getattr(runtime, "_telemetry", lambda *_: None)

    def initialize(self, *args, **kwargs):
        global _ACTIVE_RECORDER
        original_init(self, *args, **kwargs)
        self._vision_lab_recorder = VisionLabRecorder("round", _round_label())
        self._vision_lab_observer = None
        with _CONTEXT_LOCK:
            _ACTIVE_RECORDER = self._vision_lab_recorder
        atexit.register(self._vision_lab_recorder.close, "process_exit")
        telemetry(
            "DOJO_VISION_LAB_READY",
            {
                "enabled": str(self._vision_lab_recorder.settings.enabled).lower(),
                "path": str(self._vision_lab_recorder.root),
                "session": self._vision_lab_recorder.session_id,
            },
        )

    def publish(self, frame, state, decision, *, now, match=None):
        result = original_publish(self, frame, state, decision, now=now, match=match)
        self._vision_lab_recorder.record(
            frame,
            state,
            observer=self._vision_lab_observer,
            detector=getattr(self, "leader_detector", None),
            match=match,
            decision=decision,
            now=now,
        )
        return result

    def step(self, frame, state, observer, *, now):
        self._vision_lab_observer = observer
        try:
            decision = original_step(self, frame, state, observer, now=now)
        except Exception:
            self._vision_lab_recorder.close("runtime_exception")
            raise
        if str(getattr(decision, "state", "")) == "READY":
            self._vision_lab_recorder.close("round_ready")
        return decision

    engine_class.__init__ = initialize
    engine_class._publish_debug = publish
    engine_class.step = step
    engine_class._vision_lab = True
    telemetry("DOJO_VISION_LAB_BRIDGE_INSTALLED", {"engine": engine_class.__name__})
    return engine_class


__all__ = [
    "VisionLabRecorder",
    "VisionLabSettings",
    "build_panels",
    "install_anchor_monitor_lab",
    "install_runtime_lab",
    "read_settings",
    "vision_lab_root",
    "write_settings",
]
