from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..models import Point


@dataclass(frozen=True, slots=True)
class TileOdometryUpdate:
    screen_dx_px: float
    screen_dy_px: float
    world_dx_px: float
    world_dy_px: float
    residual_x_px: float
    residual_y_px: float
    tile_dx: int
    tile_dy: int
    position: Point
    traversed: tuple[Point, ...]
    accepted: bool


class TileOdometry:
    """Convert observed camera displacement into relative tile coordinates."""

    def __init__(
        self,
        tile_size_px: int = 64,
        camera_mode: str = "following",
        invert_x: bool = False,
        invert_y: bool = False,
        min_confidence: float = 0.18,
        start: Point = Point(0, 0),
    ) -> None:
        if tile_size_px <= 0:
            raise ValueError("tile_size_px must be positive")
        if camera_mode not in {"following", "hybrid", "fixed"}:
            raise ValueError("camera_mode must be following, hybrid or fixed")
        self.tile_size_px = tile_size_px
        self.camera_mode = camera_mode
        self.invert_x = invert_x
        self.invert_y = invert_y
        self.min_confidence = min_confidence
        self.position = start
        self.residual_x_px = 0.0
        self.residual_y_px = 0.0
        self.total_world_x_px = float(start.x * tile_size_px)
        self.total_world_y_px = float(start.y * tile_size_px)

    def update(self, screen_dx_px: float, screen_dy_px: float, confidence: float) -> TileOdometryUpdate:
        if confidence < self.min_confidence or self.camera_mode == "fixed":
            return self._result(screen_dx_px, screen_dy_px, 0.0, 0.0, 0, 0, (), False)
        world_dx = -float(screen_dx_px)
        world_dy = -float(screen_dy_px)
        if self.invert_x:
            world_dx *= -1.0
        if self.invert_y:
            world_dy *= -1.0
        self.total_world_x_px += world_dx
        self.total_world_y_px += world_dy
        self.residual_x_px += world_dx
        self.residual_y_px += world_dy
        tile_dx = math.trunc(self.residual_x_px / self.tile_size_px)
        tile_dy = math.trunc(self.residual_y_px / self.tile_size_px)
        self.residual_x_px -= tile_dx * self.tile_size_px
        self.residual_y_px -= tile_dy * self.tile_size_px
        previous = self.position
        self.position = Point(previous.x + tile_dx, previous.y + tile_dy)
        traversed = tuple(_raster_line(previous, self.position)[1:]) if self.position != previous else ()
        return self._result(screen_dx_px, screen_dy_px, world_dx, world_dy, tile_dx, tile_dy, traversed, True)

    def reset(self, start: Point = Point(0, 0)) -> None:
        self.position = start
        self.residual_x_px = 0.0
        self.residual_y_px = 0.0
        self.total_world_x_px = float(start.x * self.tile_size_px)
        self.total_world_y_px = float(start.y * self.tile_size_px)

    def restore(self, payload: dict[str, Any]) -> None:
        position = payload.get("position", {"x": 0, "y": 0})
        self.position = Point(int(position["x"]), int(position["y"]))
        self.residual_x_px = float(payload.get("residual_x_px", 0.0))
        self.residual_y_px = float(payload.get("residual_y_px", 0.0))
        self.total_world_x_px = float(payload.get("total_world_x_px", self.position.x * self.tile_size_px))
        self.total_world_y_px = float(payload.get("total_world_y_px", self.position.y * self.tile_size_px))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tile_size_px": self.tile_size_px,
            "camera_mode": self.camera_mode,
            "invert_x": self.invert_x,
            "invert_y": self.invert_y,
            "position": {"x": self.position.x, "y": self.position.y},
            "residual_x_px": self.residual_x_px,
            "residual_y_px": self.residual_y_px,
            "total_world_x_px": self.total_world_x_px,
            "total_world_y_px": self.total_world_y_px,
        }

    def _result(
        self,
        screen_dx: float,
        screen_dy: float,
        world_dx: float,
        world_dy: float,
        tile_dx: int,
        tile_dy: int,
        traversed: tuple[Point, ...],
        accepted: bool,
    ) -> TileOdometryUpdate:
        return TileOdometryUpdate(
            screen_dx_px=float(screen_dx),
            screen_dy_px=float(screen_dy),
            world_dx_px=world_dx,
            world_dy_px=world_dy,
            residual_x_px=self.residual_x_px,
            residual_y_px=self.residual_y_px,
            tile_dx=tile_dx,
            tile_dy=tile_dy,
            position=self.position,
            traversed=traversed,
            accepted=accepted,
        )


def _raster_line(start: Point, end: Point) -> list[Point]:
    x0, y0, x1, y1 = start.x, start.y, end.x, end.y
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    error = dx - dy
    points: list[Point] = []
    while True:
        points.append(Point(x0, y0))
        if x0 == x1 and y0 == y1:
            return points
        doubled = 2 * error
        if doubled > -dy:
            error -= dy
            x0 += sx
        if doubled < dx:
            error += dx
            y0 += sy
