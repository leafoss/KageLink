from __future__ import annotations

from dataclasses import dataclass

from ..models import Point
from .motion import MotionSample


_DIRECTION_VECTORS: dict[str, Point] = {
    "left": Point(-1, 0),
    "right": Point(1, 0),
    "up": Point(0, -1),
    "down": Point(0, 1),
}


@dataclass(frozen=True, slots=True)
class PendingMovementCommand:
    direction: str
    world_delta: Point
    started_at: float


@dataclass(frozen=True, slots=True)
class MovementCommandResolution:
    direction: str
    world_delta: Point
    moved: bool
    blocked: bool
    reason: str
    elapsed_seconds: float
    screen_dx_px: float
    screen_dy_px: float
    projected_shift_px: float
    lateral_shift_px: float
    response: float


class MovementCommandVerifier:
    """Confirm one logical tile attempt from a user movement key and screen motion.

    Tile size remains map metadata. A single key tap is one attempted logical tile;
    visual translation confirms whether that attempt succeeded. This avoids requiring
    the camera itself to travel a full 64 pixels for every tile step.
    """

    def __init__(
        self,
        camera_mode: str = "following",
        timeout_seconds: float = 0.70,
        min_shift_px: float = 2.0,
        min_response: float = 0.18,
        direction_tolerance: float = 0.65,
        invert_x: bool = False,
        invert_y: bool = False,
    ) -> None:
        if camera_mode not in {"following", "hybrid", "fixed"}:
            raise ValueError("camera_mode must be following, hybrid or fixed")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if min_shift_px <= 0:
            raise ValueError("min_shift_px must be positive")
        self.camera_mode = camera_mode
        self.timeout_seconds = timeout_seconds
        self.min_shift_px = min_shift_px
        self.min_response = min_response
        self.direction_tolerance = direction_tolerance
        self.invert_x = invert_x
        self.invert_y = invert_y
        self.pending: PendingMovementCommand | None = None
        self.best_motion = MotionSample.baseline()
        self.best_projection = 0.0
        self.best_lateral = 0.0

    def begin(self, direction: str, started_at: float) -> bool:
        normalized = direction.casefold()
        if normalized not in _DIRECTION_VECTORS or self.pending is not None:
            return False
        delta = _DIRECTION_VECTORS[normalized]
        if self.invert_x:
            delta = Point(-delta.x, delta.y)
        if self.invert_y:
            delta = Point(delta.x, -delta.y)
        self.pending = PendingMovementCommand(normalized, delta, float(started_at))
        self.best_motion = MotionSample.baseline()
        self.best_projection = 0.0
        self.best_lateral = 0.0
        return True

    def observe(self, motion: MotionSample, now: float) -> MovementCommandResolution | None:
        pending = self.pending
        if pending is None:
            return None
        projection, lateral = self._project(motion, pending.world_delta)
        if motion.response >= self.best_motion.response and projection >= self.best_projection:
            self.best_motion = motion
            self.best_projection = projection
            self.best_lateral = lateral
        direction_ok = projection >= lateral * self.direction_tolerance
        if (
            self.camera_mode != "fixed"
            and motion.accepted
            and motion.response >= self.min_response
            and projection >= self.min_shift_px
            and direction_ok
        ):
            return self._resolve(True, "movement_confirmed", now, motion, projection, lateral)
        if float(now) - pending.started_at >= self.timeout_seconds:
            reason = "fixed_camera_requires_player_tracking" if self.camera_mode == "fixed" else "no_screen_movement_after_input"
            return self._resolve(False, reason, now, self.best_motion, self.best_projection, self.best_lateral)
        return None

    def cancel(self) -> None:
        self.pending = None
        self.best_motion = MotionSample.baseline()
        self.best_projection = 0.0
        self.best_lateral = 0.0

    def _project(self, motion: MotionSample, world_delta: Point) -> tuple[float, float]:
        if self.camera_mode in {"following", "hybrid"}:
            expected_screen_x = -world_delta.x
            expected_screen_y = -world_delta.y
        else:
            expected_screen_x = world_delta.x
            expected_screen_y = world_delta.y
        projection = motion.screen_dx_px * expected_screen_x + motion.screen_dy_px * expected_screen_y
        lateral = abs(motion.screen_dx_px * expected_screen_y - motion.screen_dy_px * expected_screen_x)
        return float(projection), float(lateral)

    def _resolve(
        self,
        moved: bool,
        reason: str,
        now: float,
        motion: MotionSample,
        projection: float,
        lateral: float,
    ) -> MovementCommandResolution:
        pending = self.pending
        if pending is None:
            raise RuntimeError("No pending movement command")
        result = MovementCommandResolution(
            direction=pending.direction,
            world_delta=pending.world_delta,
            moved=moved,
            blocked=not moved,
            reason=reason,
            elapsed_seconds=max(0.0, float(now) - pending.started_at),
            screen_dx_px=motion.screen_dx_px,
            screen_dy_px=motion.screen_dy_px,
            projected_shift_px=projection,
            lateral_shift_px=lateral,
            response=motion.response,
        )
        self.cancel()
        return result
