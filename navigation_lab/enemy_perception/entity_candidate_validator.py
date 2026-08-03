from __future__ import annotations

import math
from dataclasses import dataclass

from .models import CandidateValidation, EntityRegion


@dataclass(slots=True)
class EntityCandidateValidator:
    tile_size_px: int = 64
    interest_radius_cells: int = 4
    max_covered_cells: int = 9
    max_width_cells: int = 3
    max_height_cells: int = 3
    max_pixel_area: int | None = None
    max_aspect_ratio: float = 4.0

    def __post_init__(self) -> None:
        self.tile_size_px = max(1, int(self.tile_size_px))
        self.interest_radius_cells = max(1, int(self.interest_radius_cells))
        self.max_covered_cells = max(1, int(self.max_covered_cells))
        self.max_width_cells = max(1, int(self.max_width_cells))
        self.max_height_cells = max(1, int(self.max_height_cells))
        if self.max_pixel_area is None:
            self.max_pixel_area = (
                self.max_width_cells
                * self.max_height_cells
                * self.tile_size_px
                * self.tile_size_px
            )
        self.max_pixel_area = max(1, int(self.max_pixel_area))
        self.max_aspect_ratio = max(1.0, float(self.max_aspect_ratio))

    @staticmethod
    def manhattan(
        left: tuple[int, int] | None,
        right: tuple[int, int] | None,
    ) -> int | None:
        if left is None or right is None:
            return None
        return abs(left[0] - right[0]) + abs(left[1] - right[1])

    def validate(
        self,
        region: EntityRegion,
        player_world: tuple[int, int] | None,
        playfield_cutoff_y: int,
    ) -> CandidateValidation:
        x0, y0, x1, y1 = region.bounding_box_px
        width = max(1, x1 - x0)
        height = max(1, y1 - y0)
        width_cells = max(1, int(math.ceil(width / self.tile_size_px)))
        height_cells = max(1, int(math.ceil(height / self.tile_size_px)))
        pixel_area = width * height
        aspect_ratio = max(width / height, height / width)
        distance = self.manhattan(region.anchor_world_cell, player_world)

        reason = "accepted"
        if y1 > int(playfield_cutoff_y):
            reason = "touches_hud"
        elif region.anchor_world_cell is None or distance is None:
            reason = "missing_world_anchor"
        elif distance > self.interest_radius_cells:
            reason = "outside_interest_radius"
        elif len(region.covered_cells) > self.max_covered_cells:
            reason = "too_many_covered_cells"
        elif width_cells > self.max_width_cells:
            reason = "bounding_box_too_wide"
        elif height_cells > self.max_height_cells:
            reason = "bounding_box_too_tall"
        elif pixel_area > self.max_pixel_area:
            reason = "pixel_area_too_large"
        elif aspect_ratio > self.max_aspect_ratio:
            reason = "aspect_ratio_too_extreme"

        return CandidateValidation(
            valid=reason == "accepted",
            reason=reason,
            distance_to_player=distance,
            covered_cell_count=len(region.covered_cells),
            width_cells=width_cells,
            height_cells=height_cells,
            pixel_area=pixel_area,
            aspect_ratio=float(aspect_ratio),
        )
