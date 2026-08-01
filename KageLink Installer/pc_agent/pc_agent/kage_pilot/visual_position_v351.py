from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import Callable, Iterable

import cv2
import numpy as np


class PositionState(str, Enum):
    KNOWN = "KNOWN"
    UNCERTAIN = "UNCERTAIN"
    LOST = "LOST"


@dataclass(frozen=True, slots=True)
class VisualMotionEstimate:
    dx_pixels: float = 0.0
    dy_pixels: float = 0.0
    dx_cells: float = 0.0
    dy_cells: float = 0.0
    confidence: float = 0.0
    environment_dx: float = 0.0
    environment_dy: float = 0.0
    player_screen_dx: float = 0.0
    player_screen_dy: float = 0.0
    player_match_score: float = 0.0
    accepted: bool = False
    discontinuity: bool = False


@dataclass(frozen=True, slots=True)
class VisualKeyframe:
    keyframe_id: int
    x: float
    y: float
    descriptor: np.ndarray
    created_at: float
    quality: float
    mode: str
    origin: bool = False


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    x: float = 0.0
    y: float = 0.0
    confidence: float = 0.0
    state: PositionState = PositionState.LOST
    anchored: bool = False
    keyframes: int = 0


Telemetry = Callable[[str, dict[str, object]], None]


_DIRECTION_VECTOR = {
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
    "up": (0.0, -1.0),
    "down": (0.0, 1.0),
}


class VisualOdometry:
    """Estimate real world displacement from player and environment motion.

    The environment flow comes from the existing observer. A compact player patch is matched
    in a bounded search region to cover map-edge cases where the camera does not move. Sent
    keys are not consumed here and never become position authority.
    """

    def __init__(
        self,
        *,
        cell_size: float = 32.0,
        minimum_confidence: float = 0.48,
        lost_confidence: float = 0.25,
        max_continuous_cells: float = 7.0,
        player_patch_width: int = 22,
        player_patch_height: int = 38,
        player_search_cells: float = 2.0,
    ) -> None:
        self.cell_size = max(8.0, float(cell_size))
        self.minimum_confidence = max(0.05, min(0.95, float(minimum_confidence)))
        self.lost_confidence = max(0.01, min(self.minimum_confidence, float(lost_confidence)))
        self.max_continuous_cells = max(1.5, float(max_continuous_cells))
        self.player_patch_width = max(8, int(player_patch_width))
        self.player_patch_height = max(12, int(player_patch_height))
        self.player_search_cells = max(0.5, min(5.0, float(player_search_cells)))
        self._previous_arena: np.ndarray | None = None
        self._previous_player_patch: np.ndarray | None = None
        self._previous_player_center: tuple[float, float] | None = None

    @staticmethod
    def _arena_gray(frame_bgr: np.ndarray, arena_rect) -> np.ndarray | None:
        if frame_bgr is None or frame_bgr.size == 0:
            return None
        x0, y0, x1, y1 = (int(value) for value in arena_rect)
        x0, y0 = max(0, x0), max(0, y0)
        x1 = min(frame_bgr.shape[1], x1)
        y1 = min(frame_bgr.shape[0], y1)
        crop = frame_bgr[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (3, 3), 0)

    def _player_patch(
        self,
        arena_gray: np.ndarray,
        center: tuple[float, float],
    ) -> np.ndarray | None:
        cx, cy = float(center[0]), float(center[1])
        half_w = self.player_patch_width // 2
        half_h = self.player_patch_height // 2
        x0 = max(0, int(round(cx)) - half_w)
        y0 = max(0, int(round(cy)) - half_h)
        x1 = min(arena_gray.shape[1], x0 + self.player_patch_width)
        y1 = min(arena_gray.shape[0], y0 + self.player_patch_height)
        patch = arena_gray[y0:y1, x0:x1]
        if patch.shape[0] < 10 or patch.shape[1] < 8:
            return None
        return patch.copy()

    def _match_player(
        self,
        arena_gray: np.ndarray,
        center: tuple[float, float],
    ) -> tuple[float, float, float]:
        patch = self._previous_player_patch
        previous_center = self._previous_player_center
        if patch is None or previous_center is None:
            return 0.0, 0.0, 0.0
        radius = int(round(self.cell_size * self.player_search_cells))
        cx, cy = float(center[0]), float(center[1])
        x0 = max(0, int(round(cx)) - radius - patch.shape[1] // 2)
        y0 = max(0, int(round(cy)) - radius - patch.shape[0] // 2)
        x1 = min(arena_gray.shape[1], int(round(cx)) + radius + patch.shape[1] // 2)
        y1 = min(arena_gray.shape[0], int(round(cy)) + radius + patch.shape[0] // 2)
        search = arena_gray[y0:y1, x0:x1]
        if search.shape[0] < patch.shape[0] or search.shape[1] < patch.shape[1]:
            return 0.0, 0.0, 0.0
        result = cv2.matchTemplate(search, patch, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        matched_center = (
            x0 + location[0] + patch.shape[1] * 0.5,
            y0 + location[1] + patch.shape[0] * 0.5,
        )
        return (
            float(matched_center[0] - previous_center[0]),
            float(matched_center[1] - previous_center[1]),
            float(score),
        )

    def reset(self) -> None:
        self._previous_arena = None
        self._previous_player_patch = None
        self._previous_player_center = None

    def observe(self, frame_bgr: np.ndarray, observer_state) -> VisualMotionEstimate:
        gray = self._arena_gray(frame_bgr, observer_state.arena_rect)
        if gray is None:
            return VisualMotionEstimate(discontinuity=True)
        center = tuple(float(value) for value in observer_state.player_center)
        current_patch = self._player_patch(gray, center)
        if self._previous_arena is None or self._previous_arena.shape != gray.shape:
            self._previous_arena = gray
            self._previous_player_patch = current_patch
            self._previous_player_center = center
            return VisualMotionEstimate(confidence=1.0, accepted=True)

        flow = getattr(observer_state, "global_flow", None)
        environment_dx = float(getattr(flow, "dx", 0.0) or 0.0)
        environment_dy = float(getattr(flow, "dy", 0.0) or 0.0)
        flow_points = max(0, int(getattr(flow, "points", 0) or 0))
        player_dx, player_dy, player_score = self._match_player(gray, center)

        # The observer flow represents the environment translation from the previous arena frame.
        # World player motion is the player's screen displacement minus that environment motion.
        world_dx = player_dx - environment_dx
        world_dy = player_dy - environment_dy
        magnitude_cells = math.hypot(world_dx, world_dy) / self.cell_size

        flow_confidence = min(1.0, flow_points / 24.0)
        player_confidence = max(0.0, min(1.0, (player_score - 0.35) / 0.55))
        environment_magnitude = math.hypot(environment_dx, environment_dy)
        if environment_magnitude >= 2.0 and flow_points >= 6:
            confidence = max(flow_confidence * 0.85, player_confidence * 0.65)
        else:
            confidence = player_confidence

        discontinuity = magnitude_cells > self.max_continuous_cells and confidence < 0.82
        accepted = confidence >= self.minimum_confidence and not discontinuity
        estimate = VisualMotionEstimate(
            dx_pixels=world_dx,
            dy_pixels=world_dy,
            dx_cells=world_dx / self.cell_size,
            dy_cells=world_dy / self.cell_size,
            confidence=confidence,
            environment_dx=environment_dx,
            environment_dy=environment_dy,
            player_screen_dx=player_dx,
            player_screen_dy=player_dy,
            player_match_score=player_score,
            accepted=accepted,
            discontinuity=discontinuity or confidence < self.lost_confidence,
        )
        self._previous_arena = gray
        self._previous_player_patch = current_patch
        self._previous_player_center = center
        return estimate


class VisualPositionTracker:
    def __init__(
        self,
        *,
        cell_size: float = 32.0,
        telemetry: Telemetry | None = None,
        keyframe_distance_cells: float = 2.0,
        max_keyframes: int = 80,
        relocalization_threshold: float = 0.82,
        relocalization_margin: float = 0.04,
    ) -> None:
        self.odometry = VisualOdometry(cell_size=cell_size)
        self.cell_size = self.odometry.cell_size
        self.telemetry = telemetry
        self.keyframe_distance_cells = max(0.75, float(keyframe_distance_cells))
        self.max_keyframes = max(4, int(max_keyframes))
        self.relocalization_threshold = max(0.50, min(0.99, float(relocalization_threshold)))
        self.relocalization_margin = max(0.01, min(0.30, float(relocalization_margin)))
        self.x = 0.0
        self.y = 0.0
        self.confidence = 0.0
        self.state = PositionState.LOST
        self.anchored = False
        self.mode = "-"
        self._keyframes: list[VisualKeyframe] = []
        self._next_keyframe_id = 1
        self._last_keyframe_position: tuple[float, float] | None = None
        self._blocked_until: dict[str, float] = {}
        self._last_command: str | None = None
        self._last_position_before_command: tuple[float, float] | None = None

    def _emit(self, event: str, **fields: object) -> None:
        if self.telemetry is not None:
            try:
                self.telemetry(event, fields)
            except Exception:
                pass

    @staticmethod
    def _descriptor(frame_bgr: np.ndarray, arena_rect) -> np.ndarray | None:
        gray = VisualOdometry._arena_gray(frame_bgr, arena_rect)
        if gray is None:
            return None
        # Remove thin edges where game chrome or crop jitter is most likely.
        margin_x = max(2, int(gray.shape[1] * 0.03))
        margin_y = max(2, int(gray.shape[0] * 0.05))
        cropped = gray[margin_y : gray.shape[0] - margin_y, margin_x : gray.shape[1] - margin_x]
        if cropped.size == 0:
            return None
        descriptor = cv2.resize(cropped, (96, 72), interpolation=cv2.INTER_AREA)
        descriptor = cv2.equalizeHist(descriptor)
        return descriptor

    def snapshot(self) -> PositionSnapshot:
        return PositionSnapshot(
            x=self.x,
            y=self.y,
            confidence=self.confidence,
            state=self.state,
            anchored=self.anchored,
            keyframes=len(self._keyframes),
        )

    @property
    def keyframes(self) -> tuple[VisualKeyframe, ...]:
        return tuple(self._keyframes)

    def set_anchor(self, frame_bgr: np.ndarray, observer_state, *, mode: str = "-") -> None:
        self.x = 0.0
        self.y = 0.0
        self.confidence = 1.0
        self.state = PositionState.KNOWN
        self.anchored = True
        self.mode = str(mode or "-")
        self._keyframes.clear()
        self._next_keyframe_id = 1
        self._last_keyframe_position = None
        self.odometry.reset()
        self.odometry.observe(frame_bgr, observer_state)
        self._create_keyframe(frame_bgr, observer_state, quality=1.0, origin=True)
        self._emit("DOJO_ANCHOR_SET", x=0.0, y=0.0, confidence=1.0, mode=self.mode)

    def _create_keyframe(
        self,
        frame_bgr: np.ndarray,
        observer_state,
        *,
        quality: float,
        origin: bool = False,
    ) -> bool:
        descriptor = self._descriptor(frame_bgr, observer_state.arena_rect)
        if descriptor is None or float(np.std(descriptor)) < 8.0:
            return False
        frame = VisualKeyframe(
            keyframe_id=self._next_keyframe_id,
            x=self.x,
            y=self.y,
            descriptor=descriptor,
            created_at=time.monotonic(),
            quality=max(0.0, min(1.0, float(quality))),
            mode=self.mode,
            origin=bool(origin),
        )
        self._next_keyframe_id += 1
        self._keyframes.append(frame)
        if len(self._keyframes) > self.max_keyframes:
            removable = next((index for index, item in enumerate(self._keyframes) if not item.origin), 0)
            self._keyframes.pop(removable)
        self._last_keyframe_position = (self.x, self.y)
        self._emit(
            "DOJO_KEYFRAME_CREATED",
            keyframe=frame.keyframe_id,
            x=f"{self.x:.3f}",
            y=f"{self.y:.3f}",
            quality=f"{frame.quality:.3f}",
            origin=origin,
        )
        return True

    def note_command(self, direction: str | None) -> None:
        normalized = str(direction or "").strip().lower()
        self._last_command = normalized if normalized in _DIRECTION_VECTOR else None
        self._last_position_before_command = (self.x, self.y)
        if self._last_command:
            self._emit("DOJO_MOVE_REQUEST", direction=self._last_command, x=self.x, y=self.y)

    def observe(
        self,
        frame_bgr: np.ndarray,
        observer_state,
        *,
        commanded_direction: str | None = None,
    ) -> VisualMotionEstimate:
        if commanded_direction is not None:
            self.note_command(commanded_direction)
        estimate = self.odometry.observe(frame_bgr, observer_state)
        self._emit(
            "DOJO_VISUAL_MOTION",
            dx_px=f"{estimate.dx_pixels:.3f}",
            dy_px=f"{estimate.dy_pixels:.3f}",
            dx_cells=f"{estimate.dx_cells:.4f}",
            dy_cells=f"{estimate.dy_cells:.4f}",
            confidence=f"{estimate.confidence:.3f}",
        )
        if not self.anchored:
            return estimate
        if estimate.discontinuity:
            self.state = PositionState.LOST
            self.confidence = min(self.confidence, estimate.confidence)
            self._emit("DOJO_VISUAL_ODOMETRY_LOST", confidence=f"{estimate.confidence:.3f}")
            return estimate
        if not estimate.accepted:
            self.confidence = max(0.0, self.confidence * 0.82)
            if self.confidence < 0.35:
                self.state = PositionState.LOST
            elif self.confidence < 0.65:
                self.state = PositionState.UNCERTAIN
            self._emit("DOJO_POSITION_STATE", state=self.state.value, confidence=self.confidence)
            return estimate

        old_x, old_y = self.x, self.y
        self.x += estimate.dx_cells
        self.y += estimate.dy_cells
        self.confidence = max(0.0, min(1.0, self.confidence * 0.72 + estimate.confidence * 0.28))
        self.state = PositionState.KNOWN if self.confidence >= 0.62 else PositionState.UNCERTAIN
        moved = math.hypot(self.x - old_x, self.y - old_y)
        if moved >= 0.08:
            source = "commanded" if self._last_command else "external"
            event = "DOJO_POSITION_UPDATE" if self._last_command else "DOJO_EXTERNAL_DISPLACEMENT"
            self._emit(
                event,
                dx=f"{self.x - old_x:.4f}",
                dy=f"{self.y - old_y:.4f}",
                x=f"{self.x:.4f}",
                y=f"{self.y:.4f}",
                confidence=f"{self.confidence:.3f}",
                source=source,
            )
        if self._last_command and moved < 0.08:
            self._emit("DOJO_MOVE_BLOCKED", direction=self._last_command, x=self.x, y=self.y)
        elif self._last_command:
            self._emit("DOJO_MOVE_CONFIRMED", direction=self._last_command, x=self.x, y=self.y)
        self._last_command = None
        self._last_position_before_command = None

        if self.state == PositionState.KNOWN and estimate.confidence >= 0.70:
            last = self._last_keyframe_position
            if last is None or math.hypot(self.x - last[0], self.y - last[1]) >= self.keyframe_distance_cells:
                self._create_keyframe(frame_bgr, observer_state, quality=estimate.confidence)
        return estimate

    def relocalize(self, frame_bgr: np.ndarray, observer_state) -> bool:
        self._emit("DOJO_RELOCALIZATION_BEGIN", keyframes=len(self._keyframes))
        descriptor = self._descriptor(frame_bgr, observer_state.arena_rect)
        if descriptor is None or not self._keyframes:
            self.state = PositionState.LOST
            self._emit("DOJO_RELOCALIZATION_FAILED", reason="no_descriptor_or_keyframes")
            return False
        candidates: list[tuple[float, VisualKeyframe]] = []
        for keyframe in self._keyframes:
            if keyframe.descriptor.shape != descriptor.shape:
                continue
            score = float(cv2.matchTemplate(descriptor, keyframe.descriptor, cv2.TM_CCOEFF_NORMED)[0, 0])
            candidates.append((score, keyframe))
        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates:
            self.state = PositionState.LOST
            self._emit("DOJO_RELOCALIZATION_FAILED", reason="no_candidates")
            return False
        best_score, best = candidates[0]
        second_score = candidates[1][0] if len(candidates) > 1 else -1.0
        self._emit(
            "DOJO_RELOCALIZATION_CANDIDATE",
            keyframe=best.keyframe_id,
            x=best.x,
            y=best.y,
            score=f"{best_score:.3f}",
            second=f"{second_score:.3f}",
        )
        if best_score < self.relocalization_threshold or best_score - second_score < self.relocalization_margin:
            self.state = PositionState.LOST
            self.confidence = max(0.0, min(self.confidence, best_score))
            self._emit(
                "DOJO_RELOCALIZATION_FAILED",
                score=f"{best_score:.3f}",
                margin=f"{best_score - second_score:.3f}",
            )
            return False
        self.x, self.y = best.x, best.y
        self.confidence = min(1.0, best_score)
        self.state = PositionState.KNOWN
        self.odometry.reset()
        self.odometry.observe(frame_bgr, observer_state)
        self._emit(
            "DOJO_RELOCALIZATION_CONFIRMED",
            x=f"{self.x:.4f}",
            y=f"{self.y:.4f}",
            score=f"{best_score:.3f}",
            keyframe=best.keyframe_id,
        )
        self._emit("DOJO_POSITION_RESTORED", x=self.x, y=self.y)
        return True

    def near_origin(self, tolerance_cells: float = 0.75) -> bool:
        return self.anchored and self.state == PositionState.KNOWN and math.hypot(self.x, self.y) <= max(
            0.25, float(tolerance_cells)
        )

    def mark_blocked(self, direction: str, *, now: float | None = None, ttl_seconds: float = 1.5) -> None:
        normalized = str(direction or "").strip().lower()
        if normalized in _DIRECTION_VECTOR:
            self._blocked_until[normalized] = (time.monotonic() if now is None else float(now)) + max(
                0.2, float(ttl_seconds)
            )

    def choose_return_direction(self, *, now: float | None = None) -> str | None:
        if not self.anchored or self.state != PositionState.KNOWN:
            return None
        now_value = time.monotonic() if now is None else float(now)
        candidates: list[tuple[float, str]] = []
        for direction, (vx, vy) in _DIRECTION_VECTOR.items():
            if now_value < self._blocked_until.get(direction, -1e9):
                continue
            new_distance = math.hypot(self.x + vx, self.y + vy)
            candidates.append((new_distance, direction))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        current = math.hypot(self.x, self.y)
        return candidates[0][1] if candidates[0][0] < current + 0.05 else None


__all__ = [
    "PositionSnapshot",
    "PositionState",
    "VisualKeyframe",
    "VisualMotionEstimate",
    "VisualOdometry",
    "VisualPositionTracker",
]
