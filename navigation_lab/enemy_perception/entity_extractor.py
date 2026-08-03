from __future__ import annotations

from typing import Any

from .models import EntityRegion, OverlayResult


class EntityExtractor:
    """Merge connected overlay evidence across adjacent 64 px cells."""

    def __init__(
        self,
        tile_size_px: int = 64,
        min_entity_area: int = 12,
        join_gap_px: int = 3,
    ) -> None:
        self.tile_size_px = int(tile_size_px)
        self.min_entity_area = int(min_entity_area)
        self.join_gap_px = int(join_gap_px)

    def extract(
        self,
        frame: Any,
        cell_results: list[tuple[Any, OverlayResult, tuple[int, int] | None]],
    ) -> list[EntityRegion]:
        import cv2
        import numpy as np

        height, width = frame.shape[:2]
        global_mask = np.zeros((height, width), np.uint8)
        global_difference = np.zeros_like(frame)
        cell_lookup: list[tuple[Any, tuple[int, int] | None]] = []

        for cell, result, world_cell in cell_results:
            if not result.metrics.overlay_detected:
                continue
            tile_width, tile_height = cell.x1 - cell.x0, cell.y1 - cell.y0
            mask = cv2.resize(
                result.mask,
                (tile_width, tile_height),
                interpolation=cv2.INTER_NEAREST,
            )
            difference = cv2.resize(
                result.difference,
                (tile_width, tile_height),
                interpolation=cv2.INTER_NEAREST,
            )
            global_mask[cell.y0:cell.y1, cell.x0:cell.x1] = np.maximum(
                global_mask[cell.y0:cell.y1, cell.x0:cell.x1],
                mask,
            )
            global_difference[cell.y0:cell.y1, cell.x0:cell.x1] = np.maximum(
                global_difference[cell.y0:cell.y1, cell.x0:cell.x1],
                difference,
            )
            cell_lookup.append((cell, world_cell))

        if self.join_gap_px > 0 and np.any(global_mask):
            kernel_size = self.join_gap_px * 2 + 1
            kernel = np.ones((kernel_size, kernel_size), np.uint8)
            global_mask = cv2.morphologyEx(global_mask, cv2.MORPH_CLOSE, kernel)

        count, labels, stats, _ = cv2.connectedComponentsWithStats(global_mask, 8)
        regions: list[EntityRegion] = []
        for label in range(1, count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < self.min_entity_area:
                continue
            x, y, box_width, box_height = [int(value) for value in stats[label, :4]]
            x1, y1 = x + box_width, y + box_height
            local_mask = np.where(labels[y:y1, x:x1] == label, 255, 0).astype(np.uint8)
            covered_cells: list[tuple[int, int]] = []
            world_anchor: tuple[int, int] | None = None
            for cell, world_cell in cell_lookup:
                if cell.x1 <= x or cell.x0 >= x1 or cell.y1 <= y or cell.y0 >= y1:
                    continue
                covered_cells.append((cell.column, cell.row))

            anchor_x = min(width - 1, max(0, x + box_width // 2))
            anchor_y = min(height - 1, max(0, y1 - 1))
            anchor_screen = (
                anchor_x // self.tile_size_px,
                anchor_y // self.tile_size_px,
            )
            for cell, world_cell in cell_lookup:
                if cell.contains(anchor_x, anchor_y):
                    world_anchor = world_cell
                    anchor_screen = (cell.column, cell.row)
                    break

            regions.append(
                EntityRegion(
                    bounding_box_px=(x, y, x1, y1),
                    anchor_screen_cell=anchor_screen,
                    anchor_world_cell=world_anchor,
                    covered_cells=covered_cells,
                    crop=frame[y:y1, x:x1].copy(),
                    mask=local_mask,
                    difference=global_difference[y:y1, x:x1].copy(),
                )
            )
        return regions
