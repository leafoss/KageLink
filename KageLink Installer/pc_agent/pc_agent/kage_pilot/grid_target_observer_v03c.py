from __future__ import annotations

from dataclasses import replace
import math

import cv2
import numpy as np

from .grid_target_observer_v03 import GridTrackMetrics, _grid_distance
from .grid_target_observer_v03b import StrictGridTargetObserver


class FrameAlignedGridTargetObserver(StrictGridTargetObserver):
    """Strict grid observer aligned to the captured-frame lattice.

    The arena crop starts inside the captured frame, so treating its top-left corner as
    grid origin shifts every cell. This layer maps arena-local track coordinates back to
    captured-frame coordinates before quantising them into the fixed tile lattice.
    """

    grid_origin_x: float = 0.0
    grid_origin_y: float = 0.0

    def _frame_cell(self, point, state) -> tuple[int, int]:
        x0, y0, _, _ = state.arena_rect
        size = self.tile_size
        full_x = float(point[0]) + float(x0) - self.grid_origin_x
        full_y = float(point[1]) + float(y0) - self.grid_origin_y
        return int(max(0.0, full_x) // size), int(max(0.0, full_y) // size)

    def _compress_frame_cells(self, points, state) -> list[tuple[int, int]]:
        cells: list[tuple[int, int]] = []
        for point in points:
            cell = self._frame_cell(point, state)
            if not cells or cells[-1] != cell:
                cells.append(cell)
        return cells

    def _metrics(self, track, state) -> GridTrackMetrics:
        player_cell = self._frame_cell(state.player_center, state)
        cells = self._compress_frame_cells(track.history, state)
        if not cells:
            cells = [self._frame_cell(track.center, state)]
        current_cell = self._frame_cell(track.center, state)
        if cells[-1] != current_cell:
            cells.append(current_cell)
        cells = cells[-10:]

        distances = [_grid_distance(cell, player_cell) for cell in cells]
        toward = 0
        away = 0
        for previous, current in zip(distances, distances[1:]):
            if current < previous:
                toward += 1
            elif current > previous:
                away += 1
        transitions = toward + away
        approach_ratio = float(toward) / float(max(1, transitions))
        net_closer = distances[0] - distances[-1] if distances else 0

        strength = 0.0
        background = getattr(self.tracker, "background", None)
        if background is not None and hasattr(background, "region_strength_bbox"):
            strength = float(background.region_strength_bbox(track.bbox))

        return GridTrackMetrics(
            cell=current_cell,
            player_cell=player_cell,
            grid_distance=_grid_distance(current_cell, player_cell),
            unique_cells=len(set(cells)),
            toward_steps=toward,
            away_steps=away,
            net_closer=net_closer,
            approach_ratio=approach_ratio,
            background_strength=strength,
        )

    def _aligned_active_cells(self, state) -> set[tuple[int, int]]:
        mask = state.motion_mask
        if mask is None or mask.size == 0:
            return set()
        x0, y0, _, _ = state.arena_rect
        height, width = mask.shape[:2]
        size = max(1, round(self.tile_size))
        cells: set[tuple[int, int]] = set()

        # Evaluate each full-frame-aligned tile intersecting the arena mask.
        first_full_x = math.floor(x0 / size) * size
        first_full_y = math.floor(y0 / size) * size
        last_full_x = x0 + width
        last_full_y = y0 + height
        for full_y in range(first_full_y, last_full_y, size):
            for full_x in range(first_full_x, last_full_x, size):
                local_x0 = max(0, full_x - x0)
                local_y0 = max(0, full_y - y0)
                local_x1 = min(width, full_x + size - x0)
                local_y1 = min(height, full_y + size - y0)
                if local_x1 <= local_x0 or local_y1 <= local_y0:
                    continue
                patch = mask[local_y0:local_y1, local_x0:local_x1]
                if patch.size == 0:
                    continue
                ratio = float(np.count_nonzero(patch)) / float(patch.size)
                if ratio >= 0.055:
                    cells.add((full_x // size, full_y // size))
        return cells

    def process(self, frame_bgr: np.ndarray, *, timestamp: float | None = None):
        state = super().process(frame_bgr, timestamp=timestamp)
        self._active_cells = self._aligned_active_cells(state)
        return state

    def draw_grid_overlay(self, preview: np.ndarray, state) -> np.ndarray:
        if not self.show_grid:
            return preview
        x0, y0, x1, y1 = state.arena_rect
        size = max(1, round(self.tile_size))

        first_x = math.ceil((x0 - self.grid_origin_x) / size) * size + round(self.grid_origin_x)
        first_y = math.ceil((y0 - self.grid_origin_y) / size) * size + round(self.grid_origin_y)
        for x in range(int(first_x), x1 + 1, size):
            cv2.line(preview, (x, y0), (x, y1), (65, 65, 65), 1)
        for y in range(int(first_y), y1 + 1, size):
            cv2.line(preview, (x0, y), (x1, y), (65, 65, 65), 1)

        for cell_x, cell_y in self._active_cells:
            left = int(self.grid_origin_x + cell_x * size)
            top = int(self.grid_origin_y + cell_y * size)
            cv2.rectangle(
                preview,
                (max(x0, left), max(y0, top)),
                (min(x1, left + size), min(y1, top + size)),
                (90, 90, 90),
                1,
            )

        player_cell = self._frame_cell(state.player_center, state)
        px = int(self.grid_origin_x + player_cell[0] * size)
        py = int(self.grid_origin_y + player_cell[1] * size)
        cv2.rectangle(preview, (px, py), (px + size, py + size), (255, 255, 255), 1)

        if state.target_id is not None:
            metrics = self._last_metrics.get(state.target_id)
            if metrics is not None:
                tx = int(self.grid_origin_x + metrics.cell[0] * size)
                ty = int(self.grid_origin_y + metrics.cell[1] * size)
                cv2.rectangle(preview, (tx, ty), (tx + size, ty + size), (0, 220, 255), 2)
        return preview
