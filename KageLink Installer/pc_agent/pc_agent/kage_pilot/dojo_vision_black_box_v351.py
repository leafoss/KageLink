from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import threading
from typing import Any

import cv2
import numpy as np

from pc_agent.kage_pilot.dojo_debug_v351 import read_debug_settings
from pc_agent.kage_pilot.post_combat_v03 import HudResourceReader


@dataclass(frozen=True, slots=True)
class _VisionFrame:
    captured_at: float
    jpeg: bytes
    metadata: dict[str, object]


def _json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _default_base_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "KageLink" / "vision_black_box"
    return Path.home() / ".kagelink" / "vision_black_box"


class DojoVisionBlackBox:
    """Rolling visual memory built from frames already processed by the agent.

    It never captures the desktop, creates a window, changes focus or controls the
    game. Raw frames are compressed in memory and materialized only for incidents,
    or for successful rounds when the debug level is ``processed``.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        base_dir: str | Path | None = None,
        sample_fps: float = 2.0,
        buffer_seconds: float = 60.0,
        jpeg_quality: int = 78,
    ) -> None:
        self.enabled = bool(enabled)
        self.base_dir = Path(base_dir) if base_dir is not None else _default_base_dir()
        self.sample_fps = max(0.5, min(5.0, float(sample_fps)))
        self.sample_interval = 1.0 / self.sample_fps
        capacity = max(10, int(max(10.0, min(180.0, float(buffer_seconds))) * self.sample_fps))
        self.frames: deque[_VisionFrame] = deque(maxlen=capacity)
        self.jpeg_quality = max(45, min(95, int(jpeg_quality)))
        self._last_sample_at = -1e9
        self._lock = threading.RLock()
        self._saved_reasons: set[str] = set()

    def reset_incidents(self) -> None:
        with self._lock:
            self._saved_reasons.clear()

    def record(self, frame_bgr: np.ndarray, metadata: dict[str, object], *, now: float) -> bool:
        if not self.enabled or frame_bgr is None or frame_bgr.size == 0:
            return False
        now = float(now)
        with self._lock:
            if now - self._last_sample_at < self.sample_interval:
                return False
            ok, encoded = cv2.imencode(
                ".jpg",
                frame_bgr,
                [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
            )
            if not ok:
                return False
            self.frames.append(
                _VisionFrame(
                    captured_at=now,
                    jpeg=bytes(encoded),
                    metadata=_json_value(dict(metadata)),
                )
            )
            self._last_sample_at = now
            return True

    @staticmethod
    def _draw_rect(image: np.ndarray, value, color, thickness: int = 2) -> None:
        if value is None or len(value) != 4:
            return
        x, y, w, h = (int(round(float(item))) for item in value)
        if w <= 0 or h <= 0:
            return
        cv2.rectangle(image, (x, y), (x + w, y + h), color, thickness)

    @staticmethod
    def _hud_rect(frame: np.ndarray, region) -> tuple[int, int, int, int]:
        height, width = frame.shape[:2]
        x, y, rw, rh = region
        return (
            int(round(x * width)),
            int(round(y * height)),
            int(round(rw * width)),
            int(round(rh * height)),
        )

    @classmethod
    def annotate(cls, frame_bgr: np.ndarray, metadata: dict[str, object]) -> np.ndarray:
        image = frame_bgr.copy()
        cls._draw_rect(image, metadata.get("arena_rect"), (80, 190, 80), 1)
        cls._draw_rect(image, metadata.get("trainer_box"), (30, 220, 230), 2)
        cls._draw_rect(image, cls._hud_rect(image, HudResourceReader.HEALTH_ROI), (40, 40, 230), 2)
        cls._draw_rect(image, cls._hud_rect(image, HudResourceReader.CHAKRA_ROI), (230, 120, 40), 2)

        player = metadata.get("player_point")
        if player is not None and len(player) == 2:
            cv2.circle(
                image,
                (int(round(float(player[0]))), int(round(float(player[1])))),
                8,
                (230, 230, 40),
                2,
            )

        hp = metadata.get("hp")
        chakra = metadata.get("chakra")
        hp_text = "-" if hp is None else f"{float(hp) * 100:.1f}%"
        chakra_text = "-" if chakra is None else f"{float(chakra) * 100:.1f}%"
        lines = [
            f"STATE {metadata.get('state', '-')}",
            f"MEDITATION {metadata.get('meditation_state', '-')}  {float(metadata.get('meditation_elapsed', 0.0) or 0.0):.1f}s",
            f"HP {hp_text}  CHAKRA {chakra_text}",
            f"ACTION {metadata.get('last_action', '-')} -> {metadata.get('next_action', '-')}",
            f"POSITION {metadata.get('position_state', '-')} x={float(metadata.get('position_x', 0.0) or 0.0):.2f} y={float(metadata.get('position_y', 0.0) or 0.0):.2f}",
            f"BLOCK {metadata.get('blocked_reason', '-') or '-'}",
        ]
        y = 24
        for text in lines:
            cv2.putText(
                image,
                text,
                (12, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (0, 0, 0),
                3,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                text,
                (12, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (245, 245, 245),
                1,
                cv2.LINE_AA,
            )
            y += 20
        return image

    @staticmethod
    def _decode(jpeg: bytes) -> np.ndarray | None:
        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            return None
        return frame

    @staticmethod
    def _safe_reason(reason: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(reason or "incident")).strip("_")
        return value[:64] or "incident"

    def _write_contact_sheet(self, annotated: list[np.ndarray], destination: Path) -> bool:
        selected = annotated[-12:]
        if not selected:
            return False
        thumb_width = 320
        thumbs = []
        for frame in selected:
            scale = thumb_width / max(1, frame.shape[1])
            thumb = cv2.resize(
                frame,
                (thumb_width, max(1, int(round(frame.shape[0] * scale)))),
                interpolation=cv2.INTER_AREA,
            )
            thumbs.append(thumb)
        thumb_height = max(item.shape[0] for item in thumbs)
        columns = 3
        rows = (len(thumbs) + columns - 1) // columns
        sheet = np.zeros((rows * thumb_height, columns * thumb_width, 3), dtype=np.uint8)
        for index, thumb in enumerate(thumbs):
            row, column = divmod(index, columns)
            sheet[
                row * thumb_height : row * thumb_height + thumb.shape[0],
                column * thumb_width : column * thumb_width + thumb.shape[1],
            ] = thumb
        return bool(cv2.imwrite(str(destination), sheet))

    def save_incident(
        self,
        reason: str,
        *,
        extra: dict[str, object] | None = None,
        allow_duplicate: bool = False,
    ) -> Path | None:
        if not self.enabled:
            return None
        safe_reason = self._safe_reason(reason)
        with self._lock:
            if safe_reason in self._saved_reasons and not allow_duplicate:
                return None
            buffered = list(self.frames)
            if not buffered:
                return None
            self._saved_reasons.add(safe_reason)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destination = self.base_dir / f"{stamp}_{safe_reason}"
        frames_dir = destination / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        manifest_frames: list[dict[str, object]] = []
        annotated_frames: list[np.ndarray] = []
        for index, item in enumerate(buffered):
            raw = self._decode(item.jpeg)
            if raw is None:
                continue
            annotated = self.annotate(raw, item.metadata)
            filename = f"frame_{index:04d}.jpg"
            cv2.imwrite(str(frames_dir / filename), annotated)
            annotated_frames.append(annotated)
            manifest_frames.append(
                {
                    "index": index,
                    "captured_at": item.captured_at,
                    "file": f"frames/{filename}",
                    "metadata": item.metadata,
                }
            )

        if not annotated_frames:
            return None

        raw_last = self._decode(buffered[-1].jpeg)
        if raw_last is not None:
            cv2.imwrite(str(destination / "latest_raw.jpg"), raw_last)
        cv2.imwrite(str(destination / "latest_annotated.jpg"), annotated_frames[-1])
        self._write_contact_sheet(annotated_frames, destination / "contact_sheet.jpg")

        video_path = destination / "vision.avi"
        video_written = False
        height, width = annotated_frames[0].shape[:2]
        writer = cv2.VideoWriter(
            str(video_path),
            cv2.VideoWriter_fourcc(*"MJPG"),
            self.sample_fps,
            (width, height),
        )
        try:
            if writer.isOpened():
                for frame in annotated_frames:
                    if frame.shape[:2] != (height, width):
                        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
                    writer.write(frame)
                video_written = True
        finally:
            writer.release()
        if not video_written:
            try:
                video_path.unlink(missing_ok=True)
            except Exception:
                pass

        manifest = {
            "version": 1,
            "reason": safe_reason,
            "created_at": datetime.now().isoformat(),
            "sample_fps": self.sample_fps,
            "buffer_capacity": self.frames.maxlen,
            "frame_count": len(manifest_frames),
            "video": "vision.avi" if video_written else None,
            "extra": _json_value(extra or {}),
            "frames": manifest_frames,
        }
        (destination / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return destination


def install_vision_black_box(runtime: Any):
    engine_type = runtime.ClosedLoopVisualRecoveryEngine
    if bool(getattr(engine_type, "_kagelink_v351_vision_black_box", False)):
        return engine_type

    telemetry = runtime._telemetry
    original_init = engine_type.__init__
    original_begin = engine_type.begin_post_combat
    original_publish = engine_type._publish_debug
    original_step = engine_type.step

    def black_box_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        control_path = getattr(getattr(self, "_v351_overlay", None), "control_path", None)
        settings = read_debug_settings(control_path)
        self._v351_black_box = DojoVisionBlackBox(enabled=settings.enabled)
        self._v351_black_box_save_success = str(settings.level).lower() == "processed"
        telemetry(
            "DOJO_VISION_BLACK_BOX_READY",
            {
                "enabled": str(bool(settings.enabled)).lower(),
                "mode": "all_rounds" if self._v351_black_box_save_success else "incidents",
                "path": str(self._v351_black_box.base_dir),
                "sample_fps": f"{self._v351_black_box.sample_fps:.1f}",
            },
        )

    def black_box_begin(self):
        box = getattr(self, "_v351_black_box", None)
        if box is not None:
            box.reset_incidents()
        return original_begin(self)

    def metadata_for(self, observer_state, decision, now: float) -> dict[str, object]:
        try:
            position = self.position.snapshot()
        except Exception:
            position = None
        guard = self.meditation_guard.snapshot(float(now))
        current = getattr(self.leader_detector, "_last_visual", None)
        trainer_box = getattr(current, "bbox", None) if current is not None else None
        allowed, blocked_reason = self.can_start_next_combat()
        return {
            "timestamp": float(now),
            "state": str(getattr(decision, "state", "-")),
            "hp": getattr(decision, "health", None)
            if getattr(decision, "health", None) is not None
            else getattr(self, "_v351_last_health", None),
            "chakra": getattr(decision, "chakra", None)
            if getattr(decision, "chakra", None) is not None
            else getattr(self, "_v351_last_chakra", None),
            "meditation_state": guard.phase,
            "meditation_elapsed": guard.elapsed,
            "v_cooldown_remaining": guard.cooldown_remaining,
            "position_state": position.state.value if position is not None else "LOST",
            "position_x": float(position.x) if position is not None else 0.0,
            "position_y": float(position.y) if position is not None else 0.0,
            "position_confidence": float(position.confidence) if position is not None else 0.0,
            "trainer_box": trainer_box,
            "arena_rect": self._arena_rect(observer_state),
            "player_point": self._player_point(observer_state),
            "last_action": "V" if getattr(decision, "tap_v", False) else str(getattr(decision, "move_pulse", None) or "hold"),
            "next_action": "V" if getattr(decision, "tap_v", False) else str(getattr(decision, "move_pulse", None) or ("start next combat" if allowed else "hold")),
            "blocked_reason": "" if allowed else blocked_reason,
            "combat_start_allowed": allowed,
            "reason": str(getattr(decision, "reason", "") or ""),
        }

    def black_box_publish(self, frame_bgr, observer_state, decision, *, now: float, match=None):
        result = original_publish(
            self,
            frame_bgr,
            observer_state,
            decision,
            now=now,
            match=match,
        )
        box = getattr(self, "_v351_black_box", None)
        if box is not None:
            try:
                box.record(frame_bgr, metadata_for(self, observer_state, decision, now), now=float(now))
            except Exception as error:
                telemetry(
                    "DOJO_VISION_BLACK_BOX_RECORD_FAILED",
                    {"error": f"{type(error).__name__}:{error}"},
                )
        return result

    def save_from_step(self, reason: str, decision=None):
        box = getattr(self, "_v351_black_box", None)
        if box is None:
            return None
        guard = getattr(self, "meditation_guard", None)
        destination = box.save_incident(
            reason,
            extra={
                "state": str(getattr(decision, "state", getattr(self, "state", "-"))),
                "hp": getattr(self, "_v351_last_health", None),
                "chakra": getattr(self, "_v351_last_chakra", None),
                "meditation_phase": str(getattr(guard, "phase", "-")),
                "meditation_elapsed": (
                    guard.elapsed(0.0)
                    if False
                    else None
                ),
            },
        )
        if destination is not None:
            telemetry(
                "DOJO_VISION_INCIDENT_SAVED",
                {"reason": reason, "path": str(destination), "frames": len(box.frames)},
            )
        return destination

    def black_box_step(self, *args, **kwargs):
        guard = getattr(self, "meditation_guard", None)
        abort_before = bool(getattr(guard, "abort_after_exit", False))
        try:
            decision = original_step(self, *args, **kwargs)
        except RuntimeError as error:
            if "MEDITATION_RECOVERY_TIMEOUT" in str(error):
                save_from_step(self, "meditation_timeout")
            raise
        guard = getattr(self, "meditation_guard", None)
        abort_after = bool(getattr(guard, "abort_after_exit", False))
        if abort_after and not abort_before:
            save_from_step(self, "meditation_timeout", decision)
        elif (
            bool(getattr(self, "_v351_black_box_save_success", False))
            and str(getattr(decision, "state", "")) == "READY"
        ):
            save_from_step(self, "round_ready", decision)
        return decision

    engine_type.__init__ = black_box_init
    engine_type.begin_post_combat = black_box_begin
    engine_type._publish_debug = black_box_publish
    engine_type.step = black_box_step
    engine_type._v351_black_box_metadata = metadata_for
    engine_type._v351_save_black_box = save_from_step
    engine_type._kagelink_v351_vision_black_box = True
    telemetry("DOJO_VISION_BLACK_BOX_BRIDGE_INSTALLED", {"engine": engine_type.__name__})
    return engine_type


__all__ = ["DojoVisionBlackBox", "install_vision_black_box"]
