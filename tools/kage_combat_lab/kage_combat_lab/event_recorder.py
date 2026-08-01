from __future__ import annotations

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
    def __init__(
        self,
        output_dir: Path | str,
        *,
        fps: float = 8.0,
        pre_seconds: float = 5.0,
        post_seconds: float = 5.0,
        enabled: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.fps = max(2.0, min(20.0, float(fps)))
        self.pre_frames = max(1, round(self.fps * max(1.0, float(pre_seconds))))
        self.post_frames = max(1, round(self.fps * max(1.0, float(post_seconds))))
        self.enabled = bool(enabled)
        self._buffer: deque[np.ndarray] = deque(maxlen=self.pre_frames)
        self._active: list[_ActiveClip] = []
        self._last_event_at: dict[str, float] = {}
        self.saved_paths: list[Path] = []
        if self.enabled:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value).strip())
        return cleaned.strip("_") or "event"

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
        if not self.enabled or frame_bgr is None or frame_bgr.size == 0:
            return
        now = time.monotonic() if timestamp is None else float(timestamp)
        annotated = self._annotate(
            frame_bgr,
            decision=decision,
            candidate=candidate,
            actions=actions,
            arena_rect=arena_rect,
        )
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

    def _write_clip(self, clip: _ActiveClip) -> None:
        if not clip.frames:
            return
        height, width = clip.frames[0].shape[:2]
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = self.output_dir / f"{stamp}_{clip.event}"
        path = base.with_suffix(".mp4")
        index = 2
        while path.exists():
            path = self.output_dir / f"{base.name}_{index}.mp4"
            index += 1
        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            self.fps,
            (width, height),
        )
        if not writer.isOpened():
            return
        try:
            for frame in clip.frames:
                current = frame
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

    def close(self) -> None:
        for clip in list(self._active):
            self._write_clip(clip)
        self._active.clear()


__all__ = ["CombatEventVideoRecorder"]
