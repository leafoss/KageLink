from __future__ import annotations

import math
from typing import Any

from .models import PlayerLocation, PlayerLocationSource


class PlayerLocator:
    """Locate Player without making one learned pose a hard pipeline gate.

    Priority is visual confirmation, a short temporal prediction, then the
    calibrated playfield anchor. The fallback uses configurable proportions of
    the playable field, never the centre of the full HWND that includes HUD.
    """

    def __init__(
        self,
        tile_size_px: int = 64,
        temporal_ttl_frames: int = 10,
        mode: str = "auto",
        anchor_column: int | None = None,
        anchor_row: int | None = None,
        anchor_x_ratio: float = 0.50,
        anchor_y_ratio: float = 0.57,
    ) -> None:
        self.tile_size_px = max(1, int(tile_size_px))
        self.temporal_ttl_frames = max(0, int(temporal_ttl_frames))
        self.mode = str(mode).strip().lower()
        self.anchor_column = anchor_column
        self.anchor_row = anchor_row
        self.anchor_x_ratio = float(anchor_x_ratio)
        self.anchor_y_ratio = float(anchor_y_ratio)
        if not 0.05 <= self.anchor_x_ratio <= 0.95:
            raise ValueError("anchor_x_ratio must be between 0.05 and 0.95")
        if not 0.05 <= self.anchor_y_ratio <= 0.95:
            raise ValueError("anchor_y_ratio must be between 0.05 and 0.95")
        self.last_location: PlayerLocation | None = None
        self.last_visual_frame = 0
        self.residual_world_px = [0.0, 0.0]

    @staticmethod
    def _visual_confidence(mapping: Any) -> float:
        if mapping.player_screen is None:
            return 0.0
        column, row = mapping.player_screen
        return max(
            (
                float(item.classification.confidence)
                for item in mapping.scan.cells
                if item.crop.column == column and item.crop.row == row
            ),
            default=0.0,
        )

    def _anchor_screen_cell(
        self,
        mapping: Any,
        frame_width: int,
        playfield_cutoff_y: int,
    ) -> tuple[int, int] | None:
        if self.anchor_column is not None and self.anchor_row is not None:
            requested = (int(self.anchor_column), int(self.anchor_row))
            if any(
                (item.crop.column, item.crop.row) == requested
                for item in mapping.scan.cells
            ):
                return requested

        anchor_x = int(round(int(frame_width) * self.anchor_x_ratio))
        anchor_y = int(round(int(playfield_cutoff_y) * self.anchor_y_ratio))
        anchor_x = min(max(anchor_x, 0), max(0, int(frame_width) - 1))
        anchor_y = min(max(anchor_y, 0), max(0, int(playfield_cutoff_y) - 1))
        containing = next(
            (
                item
                for item in mapping.scan.cells
                if item.crop.contains(anchor_x, anchor_y)
            ),
            None,
        )
        if containing is not None:
            return containing.crop.column, containing.crop.row
        if not mapping.scan.cells:
            return None
        nearest = min(
            mapping.scan.cells,
            key=lambda item: (
                item.crop.center[0] - anchor_x
            ) ** 2
            + (item.crop.center[1] - anchor_y) ** 2,
        )
        return nearest.crop.column, nearest.crop.row

    def _motion_world_delta(self, motion: Any) -> tuple[int, int]:
        if motion is None or not bool(getattr(motion, "accepted", False)):
            return 0, 0
        self.residual_world_px[0] += -float(motion.screen_dx_px)
        self.residual_world_px[1] += -float(motion.screen_dy_px)
        return self._consume_axis(0), self._consume_axis(1)

    def _consume_axis(self, axis: int) -> int:
        value = self.residual_world_px[axis]
        if abs(value) < self.tile_size_px * 0.65:
            return 0
        steps = int(
            math.copysign(
                max(1, int(round(abs(value) / float(self.tile_size_px)))),
                value,
            )
        )
        self.residual_world_px[axis] -= steps * self.tile_size_px
        return steps

    def locate(
        self,
        mapping: Any,
        frame_width: int,
        playfield_cutoff_y: int,
    ) -> PlayerLocation:
        frame_index = int(mapping.frame_index)
        visual_allowed = self.mode not in {"fallback", "anchor"}
        fallback_allowed = self.mode not in {"visual", "visual_only"}

        if visual_allowed and mapping.player_screen is not None:
            world = mapping.player_world
            if world is None:
                world = self.last_location.world_cell if self.last_location else (0, 0)
            location = PlayerLocation(
                True,
                PlayerLocationSource.VISUAL_CONFIRMED,
                tuple(mapping.player_screen),
                tuple(world),
                self._visual_confidence(mapping),
                0,
            )
            self.last_visual_frame = frame_index
            self.last_location = location
            self.residual_world_px = [0.0, 0.0]
            return location

        if (
            self.last_visual_frame > 0
            and self.last_location is not None
            and self.temporal_ttl_frames > 0
        ):
            age = frame_index - self.last_visual_frame
            if age <= self.temporal_ttl_frames:
                world = self.last_location.world_cell or (0, 0)
                dx, dy = self._motion_world_delta(mapping.motion)
                world = (world[0] + dx, world[1] + dy)
                location = PlayerLocation(
                    True,
                    PlayerLocationSource.TEMPORAL_PREDICTED,
                    self.last_location.screen_cell,
                    world,
                    max(0.30, self.last_location.confidence * (0.92 ** max(1, age))),
                    age,
                )
                self.last_location = location
                return location

        if fallback_allowed:
            screen = self._anchor_screen_cell(mapping, frame_width, playfield_cutoff_y)
            if screen is not None:
                world = self.last_location.world_cell if self.last_location else None
                if world is None:
                    world = mapping.player_world or (0, 0)
                dx, dy = self._motion_world_delta(mapping.motion)
                world = (world[0] + dx, world[1] + dy)
                location = PlayerLocation(
                    True,
                    PlayerLocationSource.CALIBRATED_ANCHOR_FALLBACK,
                    screen,
                    tuple(world),
                    0.65,
                    0,
                )
                self.last_location = location
                return location

        location = PlayerLocation(
            False,
            PlayerLocationSource.NOT_FOUND,
            None,
            None,
            0.0,
            0,
        )
        self.last_location = location
        return location

    def reset(self) -> None:
        self.last_location = None
        self.last_visual_frame = 0
        self.residual_world_px = [0.0, 0.0]
