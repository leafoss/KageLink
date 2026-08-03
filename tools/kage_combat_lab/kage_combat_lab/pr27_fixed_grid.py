from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


class PR278CalibrationMismatch(RuntimeError):
    """Raised when a frame cannot use the audited native grid calibration."""


@dataclass(frozen=True, slots=True)
class NativeRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def bbox_xywh(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.width, self.height

    def contains(self, point: tuple[float, float]) -> bool:
        x, y = point
        return self.left <= x < self.right and self.top <= y < self.bottom

    def intersect(self, other: "NativeRect") -> "NativeRect | None":
        left = max(self.left, other.left)
        top = max(self.top, other.top)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return None
        return NativeRect(left, top, right, bottom)

    def expand(self, *, left: int = 0, top: int = 0, right: int = 0, bottom: int = 0) -> "NativeRect":
        return NativeRect(
            self.left - int(left),
            self.top - int(top),
            self.right + int(right),
            self.bottom + int(bottom),
        )


@dataclass(frozen=True, slots=True)
class FixedGridCell:
    absolute_row: int
    absolute_column: int
    relative_row: int
    relative_column: int
    native_rect: NativeRect

    @property
    def relative_key(self) -> tuple[int, int]:
        return self.relative_row, self.relative_column

    @property
    def absolute_key(self) -> tuple[int, int]:
        return self.absolute_row, self.absolute_column


@dataclass(frozen=True, slots=True)
class FixedNativeGridCalibration:
    """Audited PR27.8 grid. It never follows a body track or target."""

    native_width: int = 1920
    native_height: int = 1037
    cell_size: int = 64
    offset_x: int = 0
    offset_y: int = 21
    self_row: int = 6
    self_column: int = 15
    roi_radius: int = 4

    def validate_native_shape(self, shape: Sequence[int]) -> None:
        height, width = int(shape[0]), int(shape[1])
        if (width, height) != (self.native_width, self.native_height):
            raise PR278CalibrationMismatch(
                "PR27_CALIBRATION_MISMATCH:"
                f"expected={self.native_width}x{self.native_height} "
                f"actual={width}x{height}"
            )
        if self.cell_size != 64 or self.offset_x != 0 or self.offset_y != 21:
            raise PR278CalibrationMismatch(
                "PR27_CALIBRATION_MISMATCH:fixed grid constants changed"
            )
        if (self.self_row, self.self_column) != (6, 15):
            raise PR278CalibrationMismatch(
                "PR27_CALIBRATION_MISMATCH:fixed SELF cell changed"
            )

    def absolute_cell_rect(self, row: int, column: int) -> NativeRect:
        left = self.offset_x + int(column) * self.cell_size
        top = self.offset_y + int(row) * self.cell_size
        return NativeRect(left, top, left + self.cell_size, top + self.cell_size)

    def self_cell_rect(self) -> NativeRect:
        return self.absolute_cell_rect(self.self_row, self.self_column)

    def self_search_rect(
        self,
        *,
        side_margin: int = 16,
        top_margin: int = 20,
        bottom_margin: int = 4,
    ) -> NativeRect:
        return self.self_cell_rect().expand(
            left=side_margin,
            right=side_margin,
            top=top_margin,
            bottom=bottom_margin,
        ).intersect(NativeRect(0, 0, self.native_width, self.native_height)) or self.self_cell_rect()

    def relative_cell(self, absolute_row: int, absolute_column: int) -> tuple[int, int]:
        return int(absolute_row) - self.self_row, int(absolute_column) - self.self_column

    def absolute_from_relative(self, relative_row: int, relative_column: int) -> tuple[int, int]:
        return self.self_row + int(relative_row), self.self_column + int(relative_column)

    def cell_for_native_point(self, x: float, y: float) -> FixedGridCell | None:
        if not (0 <= x < self.native_width and 0 <= y < self.native_height):
            return None
        column = int((x - self.offset_x) // self.cell_size)
        row = int((y - self.offset_y) // self.cell_size)
        rect = self.absolute_cell_rect(row, column)
        if not rect.contains((x, y)):
            return None
        relative_row, relative_column = self.relative_cell(row, column)
        return FixedGridCell(row, column, relative_row, relative_column, rect)

    def roi_cells(self) -> tuple[FixedGridCell, ...]:
        cells: list[FixedGridCell] = []
        for relative_row in range(-self.roi_radius, self.roi_radius + 1):
            for relative_column in range(-self.roi_radius, self.roi_radius + 1):
                if relative_row * relative_row + relative_column * relative_column > self.roi_radius * self.roi_radius:
                    continue
                row, column = self.absolute_from_relative(relative_row, relative_column)
                rect = self.absolute_cell_rect(row, column)
                if rect.intersect(NativeRect(0, 0, self.native_width, self.native_height)) is None:
                    continue
                cells.append(
                    FixedGridCell(
                        row,
                        column,
                        relative_row,
                        relative_column,
                        rect,
                    )
                )
        return tuple(sorted(cells, key=lambda cell: (cell.relative_row, cell.relative_column)))

    def roi_native_rect(self, *, padding: int = 0) -> NativeRect:
        rects = [cell.native_rect for cell in self.roi_cells()]
        return NativeRect(
            max(0, min(rect.left for rect in rects) - padding),
            max(0, min(rect.top for rect in rects) - padding),
            min(self.native_width, max(rect.right for rect in rects) + padding),
            min(self.native_height, max(rect.bottom for rect in rects) + padding),
        )

    @staticmethod
    def native_to_arena(rect: NativeRect, arena_rect: NativeRect) -> NativeRect:
        return NativeRect(
            rect.left - arena_rect.left,
            rect.top - arena_rect.top,
            rect.right - arena_rect.left,
            rect.bottom - arena_rect.top,
        )

    @staticmethod
    def arena_to_native(rect: NativeRect, arena_rect: NativeRect) -> NativeRect:
        return NativeRect(
            rect.left + arena_rect.left,
            rect.top + arena_rect.top,
            rect.right + arena_rect.left,
            rect.bottom + arena_rect.top,
        )

    def iter_grid_lines(self) -> Iterable[tuple[str, int]]:
        column = 0
        x = self.offset_x
        while x <= self.native_width:
            yield "vertical", x
            column += 1
            x = self.offset_x + column * self.cell_size
        row = 0
        y = self.offset_y
        while y <= self.native_height:
            yield "horizontal", y
            row += 1
            y = self.offset_y + row * self.cell_size


DEFAULT_FIXED_GRID = FixedNativeGridCalibration()


__all__ = [
    "DEFAULT_FIXED_GRID",
    "FixedGridCell",
    "FixedNativeGridCalibration",
    "NativeRect",
    "PR278CalibrationMismatch",
]
