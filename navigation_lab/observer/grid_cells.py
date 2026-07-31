from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .grid_calibration import GridCalibration


@dataclass(slots=True)
class GridCellCrop:
    row: int
    column: int
    x0: int
    y0: int
    x1: int
    y1: int
    image: Any

    @property
    def id(self) -> str:
        return f"r{self.row:02d}_c{self.column:02d}"

    @property
    def center(self) -> tuple[int, int]:
        return ((self.x0 + self.x1) // 2, (self.y0 + self.y1) // 2)

    def contains(self, x: int, y: int) -> bool:
        return self.x0 <= x < self.x1 and self.y0 <= y < self.y1


def grid_boundaries(length: int, tile_size: int, offset: int) -> tuple[int, ...]:
    if length <= 0 or tile_size <= 0:
        return ()
    start = int(offset) % int(tile_size)
    values = list(range(start, int(length) + 1, int(tile_size)))
    if values and values[-1] > length:
        values.pop()
    return tuple(values)


def extract_grid_cells(
    frame: Any,
    calibration: GridCalibration,
    inset_px: int = 2,
) -> list[GridCellCrop]:
    if frame is None or not hasattr(frame, "shape") or frame.size == 0:
        raise ValueError("frame must be a non-empty image")
    height, width = frame.shape[:2]
    vertical = grid_boundaries(width, calibration.tile_size_px, calibration.offset_x_px)
    horizontal = grid_boundaries(height, calibration.tile_size_px, calibration.offset_y_px)
    inset = max(int(inset_px), int(calibration.line_thickness))
    cells: list[GridCellCrop] = []
    for row, (top, bottom) in enumerate(zip(horizontal, horizontal[1:])):
        if bottom - top != calibration.tile_size_px:
            continue
        for column, (left, right) in enumerate(zip(vertical, vertical[1:])):
            if right - left != calibration.tile_size_px:
                continue
            x0, x1 = left + inset, right - inset
            y0, y1 = top + inset, bottom - inset
            if x1 <= x0 or y1 <= y0:
                continue
            cells.append(
                GridCellCrop(
                    row=row,
                    column=column,
                    x0=left,
                    y0=top,
                    x1=right,
                    y1=bottom,
                    image=frame[y0:y1, x0:x1].copy(),
                )
            )
    return cells
