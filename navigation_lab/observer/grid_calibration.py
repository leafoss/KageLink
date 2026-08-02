from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GridCalibration:
    """Visual square-grid calibration shared by the calibration and mapping windows."""

    tile_size_px: int = 64
    offset_x_px: int = 0
    offset_y_px: int = 0
    line_thickness: int = 1
    line_opacity: float = 0.75

    def __post_init__(self) -> None:
        self.validate()
        self.normalize_offsets()

    def validate(self) -> None:
        if not 4 <= int(self.tile_size_px) <= 512:
            raise ValueError("tile_size_px must be between 4 and 512")
        if not 1 <= int(self.line_thickness) <= 8:
            raise ValueError("line_thickness must be between 1 and 8")
        if not 0.05 <= float(self.line_opacity) <= 1.0:
            raise ValueError("line_opacity must be between 0.05 and 1.0")

    def normalize_offsets(self) -> None:
        size = int(self.tile_size_px)
        self.offset_x_px = int(self.offset_x_px) % size
        self.offset_y_px = int(self.offset_y_px) % size

    def vertical_lines(self, width: int) -> tuple[int, ...]:
        return self._axis_lines(int(width), self.offset_x_px)

    def horizontal_lines(self, height: int) -> tuple[int, ...]:
        return self._axis_lines(int(height), self.offset_y_px)

    def center_on(self, width: int, height: int) -> None:
        self.offset_x_px = (int(width) // 2) % self.tile_size_px
        self.offset_y_px = (int(height) // 2) % self.tile_size_px

    def draw(self, frame: Any) -> Any:
        import cv2

        self.validate()
        self.normalize_offsets()
        if frame is None or not hasattr(frame, "shape"):
            raise TypeError("frame must be a numpy-compatible image")
        result = frame.copy()
        overlay = frame.copy()
        height, width = frame.shape[:2]
        color = (64, 220, 96)
        for x in self.vertical_lines(width):
            cv2.line(overlay, (x, 0), (x, height - 1), color, self.line_thickness)
        for y in self.horizontal_lines(height):
            cv2.line(overlay, (0, y), (width - 1, y), color, self.line_thickness)
        cv2.addWeighted(
            overlay,
            float(self.line_opacity),
            result,
            1.0 - float(self.line_opacity),
            0.0,
            result,
        )
        center_x, center_y = width // 2, height // 2
        cv2.drawMarker(
            result,
            (center_x, center_y),
            (255, 255, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=20,
            thickness=2,
        )
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "tile_size_px": int(self.tile_size_px),
            "offset_x_px": int(self.offset_x_px),
            "offset_y_px": int(self.offset_y_px),
            "line_thickness": int(self.line_thickness),
            "line_opacity": float(self.line_opacity),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GridCalibration":
        return cls(
            tile_size_px=int(payload.get("tile_size_px", 64)),
            offset_x_px=int(payload.get("offset_x_px", 0)),
            offset_y_px=int(payload.get("offset_y_px", 0)),
            line_thickness=int(payload.get("line_thickness", 1)),
            line_opacity=float(payload.get("line_opacity", 0.75)),
        )

    def _axis_lines(self, length: int, offset: int) -> tuple[int, ...]:
        if length <= 0:
            return ()
        start = int(offset) % self.tile_size_px
        return tuple(range(start, length, self.tile_size_px))
