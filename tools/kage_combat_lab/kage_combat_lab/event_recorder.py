from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from .domain import CandidateObservation, CombatDecision


@dataclass(slots=True)
class _ActiveClip:
    event: str
    started_at: float
    frames: list[np.ndarray]
    remaining_post_frames: int


class CombatEventVideoRecorder:
    """Record a mandatory full-round replay plus optional event clips.

    The recorder first tries several video codecs and containers. If the local
    OpenCV build cannot open any writer, it falls back to a numbered PNG
    sequence plus a JSON manifest. Recording failure must never be silent.
    """

    _VIDEO_PROFILES = (
        ("mp4v", ".mp4"),
        ("avc1", ".mp4"),
        ("XVID", ".avi"),
        ("MJPG", ".avi"),
    )

    def __init__(
        self,
        output_dir: Path | str,
        *,
        fps: float = 8.0,
        pre_seconds: float = 5.0,
        post_seconds: float = 5.0,
        enabled: bool = True,
        full_replay_enabled: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.fps = max(2.0, min(20.0, float(fps)))
        self.pre_frames = max(1, round(self.fps * max(1.0, float(pre_seconds))))
        self.post_frames = max(1, round(self.fps * max(1.0, float(post_seconds))))
        self.enabled = bool(enabled)
        self.full_replay_enabled = bool(full_replay_enabled and enabled)
        self._buffer: deque[np.ndarray] = deque(maxlen=self.pre_frames)
        self._active: list[_ActiveClip] = []
        self._last_event_at: dict[str, float] = {}
        self.saved_paths: list[Path] = []
        self._full_writer: cv2.VideoWriter | None = None
        self._full_replay_path: Path | None = None
        self._full_size: tuple[int, int] | None = None
        self._full_frames = 0
        self._full_codec: str | None = None
        self._full_mode: str | None = None
        self._full_open_attempted = False
        self._writer_errors: list[str] = []
        self._png_sequence_dir: Path | None = None
        self._closed = False
        if self.enabled:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def full_replay_path(self) -> Path | None:
        return self._full_replay_path

    @property
    def full_replay_frames(self) -> int:
        return int(self._full_frames)

    @property
    def full_replay_mode(self) -> str | None:
        return self._full_mode

    @property
    def full_replay_codec(self) -> str | None:
        return self._full_codec

    @property
    def writer_errors(self) -> tuple[str, ...]:
        return tuple(self._writer_errors)

    @staticmethod
    def _sanitize(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value).strip())
        return cleaned.strip("_") or "event"

    def _unique_path(self, stem: str, suffix: str) -> Path:
        path = self.output_dir / f"{stem}{suffix}"
        index = 2
        while path.exists():
            path = self.output_dir / f"{stem}_{index}{suffix}"
            index += 1
        return path

    def _unique_directory(self, stem: str) -> Path:
        path = self.output_dir / stem
        index = 2
        while path.exists():
            path = self.output_dir / f"{stem}_{index}"
            index += 1
        return path

    @staticmethod
    def _orientation_state(decision: CombatDecision) -> str:
        if decision.turn_direction:
            return "TURN_ALIGN"
        if decision.contact_deadzone_active and decision.r_authorized:
            return "CONTACT_LOCK"
        if decision.r_authorized:
            return "LOCKED_ALIGNED"
        if decision.target_state.value == "LOCKED":
            return "LOCKED_UNALIGNED"
        return decision.target_state.value

    @classmethod
    def _annotate(
        cls,
        frame_bgr: np.ndarray,
        *,
        decision: CombatDecision,
        candidate: CandidateObservation | None,
        actions: Iterable[str],
        event_text: str = "",
        arena_rect: tuple[int, int, int, int] | None = None,
    ) -> np.ndarray:
        annotated = frame_bgr.copy()
        if candidate is not None and candidate.bbox is not None:
            left, top, width, height = candidate.bbox
            if arena_rect is not None:
                left += int(arena_rect[0])
                top += int(arena_rect[1])
            cv2.rectangle(
                annotated,
                (int(left), int(top)),
                (int(left + width), int(top + height)),
                (255, 255, 255),
                1,
            )
        lines = [
            f"state={cls._orientation_state(decision)} logical={decision.combat_target_id or '-'} visual={decision.visual_track_id or '-'}",
            f"D={decision.grid_distance} raw={decision.raw_target_bearing or '-'} stable={decision.stable_target_bearing or '-'}",
            f"cmd={decision.commanded_facing or '-'} confirmed={decision.confirmed_facing or '-'} conf={decision.facing_confidence:.2f}",
            f"turn={decision.turn_attempt} R={decision.r_authorized} H={decision.h_authorized} invalid={decision.orientation_invalidated_reason or '-'}",
            f"id={decision.identity_score:.2f} app={decision.appearance_score:.2f} bg={decision.background_probability:.2f} reid={decision.reidentified}",
            f"actions={','.join(actions) if actions else 'WAIT'}",
        ]
        if event_text:
            lines.insert(0, f"EVENT={event_text}")
        y = 22
        for line in lines:
            cv2.putText(
                annotated,
                line,
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (0, 0, 0),
                3,
                cv2.LINE_AA,
            )
            cv2.putText(
                annotated,
                line,
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            y += 20
        return annotated

    @staticmethod
    def _terminal_frame(frame: np.ndarray, event_text: str) -> np.ndarray:
        result = frame.copy()
        height, width = result.shape[:2]
        bar_height = min(54, max(34, height // 10))
        top = max(0, height - bar_height)
        cv2.rectangle(result, (0, top), (width, height), (0, 0, 0), -1)
        cv2.putText(
            result,
            f"FINAL={event_text}",
            (12, min(height - 12, top + 32)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return result

    @staticmethod
    def _prepare_video_frame(frame: np.ndarray) -> np.ndarray:
        current = np.asarray(frame)
        if current.ndim == 2:
            current = cv2.cvtColor(current, cv2.COLOR_GRAY2BGR)
        elif current.ndim == 3 and current.shape[2] == 4:
            current = cv2.cvtColor(current, cv2.COLOR_BGRA2BGR)
        elif current.ndim != 3 or current.shape[2] != 3:
            raise ValueError(f"UNSUPPORTED_REPLAY_FRAME_SHAPE:{current.shape}")
        if current.dtype != np.uint8:
            current = np.clip(current, 0, 255).astype(np.uint8)
        current = np.ascontiguousarray(current)

        # Several Windows codecs silently refuse odd frame dimensions.
        height, width = current.shape[:2]
        pad_right = width % 2
        pad_bottom = height % 2
        if pad_right or pad_bottom:
            current = cv2.copyMakeBorder(
                current,
                0,
                pad_bottom,
                0,
                pad_right,
                cv2.BORDER_CONSTANT,
                value=(0, 0, 0),
            )
        return current

    def _remove_failed_file(self, path: Path) -> None:
        try:
            if path.exists() and path.stat().st_size <= 4096:
                path.unlink()
        except OSError:
            pass

    def _try_video_writer(
        self,
        *,
        stem: str,
        frame: np.ndarray,
    ) -> tuple[cv2.VideoWriter | None, Path | None, str | None]:
        height, width = frame.shape[:2]
        for codec, suffix in self._VIDEO_PROFILES:
            path = self._unique_path(stem, suffix)
            writer: cv2.VideoWriter | None = None
            try:
                writer = cv2.VideoWriter(
                    str(path),
                    cv2.VideoWriter_fourcc(*codec),
                    self.fps,
                    (int(width), int(height)),
                )
                if writer.isOpened():
                    return writer, path, codec
                self._writer_errors.append(
                    f"codec={codec} container={suffix} opened=false"
                )
            except Exception as exc:
                self._writer_errors.append(
                    f"codec={codec} container={suffix} error={type(exc).__name__}:{exc}"
                )
            finally:
                if writer is not None and not writer.isOpened():
                    writer.release()
                self._remove_failed_file(path)
        return None, None, None

    def _open_full_output(self, frame: np.ndarray) -> None:
        if self._full_open_attempted or not self.full_replay_enabled:
            return
        self._full_open_attempted = True
        prepared = self._prepare_video_frame(frame)
        height, width = prepared.shape[:2]
        self._full_size = (int(width), int(height))
        writer, path, codec = self._try_video_writer(
            stem="full_combat_replay",
            frame=prepared,
        )
        if writer is not None and path is not None and codec is not None:
            self._full_writer = writer
            self._full_replay_path = path
            self._full_codec = codec
            self._full_mode = "VIDEO"
            print(
                f"FULL_REPLAY_RECORDER_OPEN mode=VIDEO codec={codec} "
                f"size={width}x{height} fps={self.fps:.2f} path={path}"
            )
            return

        sequence_dir = self._unique_directory("full_combat_replay_frames")
        sequence_dir.mkdir(parents=True, exist_ok=False)
        self._png_sequence_dir = sequence_dir
        self._full_replay_path = sequence_dir
        self._full_codec = "PNG"
        self._full_mode = "PNG_SEQUENCE"
        print(
            "FULL_REPLAY_VIDEO_WRITER_FAILED "
            f"fallback=PNG_SEQUENCE path={sequence_dir} "
            f"attempts={' | '.join(self._writer_errors) or 'none'}"
        )

    def _write_full_frame(self, frame: np.ndarray) -> None:
        prepared = self._prepare_video_frame(frame)
        self._open_full_output(prepared)
        if self._full_size is None:
            return
        width, height = self._full_size
        current = prepared
        if current.shape[1] != width or current.shape[0] != height:
            current = cv2.resize(
                current,
                (width, height),
                interpolation=cv2.INTER_AREA,
            )

        if self._full_writer is not None:
            self._full_writer.write(current)
            self._full_frames += 1
            return

        if self._png_sequence_dir is not None:
            path = self._png_sequence_dir / f"frame_{self._full_frames:06d}.png"
            if not cv2.imwrite(str(path), current):
                self._writer_errors.append(f"png_write_failed:{path}")
                return
            self._full_frames += 1

    def push(
        self,
        frame_bgr: np.ndarray,
        *,
        decision: CombatDecision,
        candidate: CandidateObservation | None,
        actions: tuple[str, ...],
        events: Iterable[str] = (),
        timestamp: float | None = None,
        arena_rect: tuple[int, int, int, int] | None = None,
    ) -> None:
        if (
            self._closed
            or not self.enabled
            or frame_bgr is None
            or frame_bgr.size == 0
        ):
            return
        now = time.monotonic() if timestamp is None else float(timestamp)
        annotated = self._annotate(
            frame_bgr,
            decision=decision,
            candidate=candidate,
            actions=actions,
            arena_rect=arena_rect,
        )

        # Mandatory continuous replay. This happens before event processing so a
        # clean round with no diagnostic event still creates visual evidence.
        self._write_full_frame(annotated)

        completed: list[_ActiveClip] = []
        for clip in self._active:
            clip.frames.append(annotated.copy())
            clip.remaining_post_frames -= 1
            if clip.remaining_post_frames <= 0:
                completed.append(clip)
        for clip in completed:
            self._active.remove(clip)
            self._write_clip(clip)
        for raw_event in events:
            event = self._sanitize(raw_event)
            if now - self._last_event_at.get(event, -1e9) < 2.0:
                continue
            self._last_event_at[event] = now
            pre = [frame.copy() for frame in self._buffer]
            pre.append(
                self._annotate(
                    frame_bgr,
                    decision=decision,
                    candidate=candidate,
                    actions=actions,
                    event_text=event,
                    arena_rect=arena_rect,
                )
            )
            self._active.append(_ActiveClip(event, now, pre, self.post_frames))
        self._buffer.append(annotated)

    def mark_terminal_event(self, event_text: str, *, seconds: float = 1.0) -> None:
        """Append a visible final marker to the mandatory replay output."""

        if self._closed or not self._buffer:
            return
        event = self._sanitize(event_text)
        frame = self._terminal_frame(self._buffer[-1], event)
        repeats = max(1, round(self.fps * max(0.25, float(seconds))))
        for _ in range(repeats):
            self._write_full_frame(frame)

    def _write_clip(self, clip: _ActiveClip) -> None:
        if not clip.frames:
            return
        prepared = self._prepare_video_frame(clip.frames[0])
        writer, path, _codec = self._try_video_writer(
            stem=f"{time.strftime('%Y%m%d_%H%M%S')}_{clip.event}",
            frame=prepared,
        )
        if writer is None or path is None:
            return
        height, width = prepared.shape[:2]
        try:
            for frame in clip.frames:
                current = self._prepare_video_frame(frame)
                if current.shape[1] != width or current.shape[0] != height:
                    current = cv2.resize(
                        current,
                        (width, height),
                        interpolation=cv2.INTER_AREA,
                    )
                writer.write(current)
        finally:
            writer.release()
        self.saved_paths.append(path)

    def _write_png_manifest(self) -> None:
        if self._png_sequence_dir is None:
            return
        manifest = {
            "format": "PNG_SEQUENCE",
            "fps": self.fps,
            "frames": self._full_frames,
            "frame_pattern": "frame_%06d.png",
            "writer_errors": list(self._writer_errors),
        }
        path = self._png_sequence_dir / "replay_manifest.json"
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def summary_line(self) -> str:
        if self._full_replay_path is None or self._full_frames <= 0:
            return (
                "FULL_REPLAY_NOT_CREATED "
                f"errors={' | '.join(self._writer_errors) or 'no combat frames received'}"
            )
        return (
            f"FULL_REPLAY_SAVED mode={self._full_mode} codec={self._full_codec} "
            f"frames={self._full_frames} path={self._full_replay_path}"
        )

    def close(self) -> None:
        if self._closed:
            return
        for clip in list(self._active):
            self._write_clip(clip)
        self._active.clear()
        if self._full_writer is not None:
            self._full_writer.release()
            self._full_writer = None
        self._write_png_manifest()
        if self._full_replay_path is not None and self._full_frames > 0:
            self.saved_paths.append(self._full_replay_path)
        self._closed = True
        print(self.summary_line())


__all__ = ["CombatEventVideoRecorder"]
