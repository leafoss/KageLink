from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TypeVar

from .tile_map_engine import ClassifiedGridCell


TCell = TypeVar("TCell", bound=ClassifiedGridCell)


@dataclass(frozen=True, slots=True)
class PlayfieldLearningScope:
    """Define which vertical part of the captured HWND may teach new tiles.

    Cells outside the scope remain visible and classified, but they must not be
    offered as unknown examples or accepted by the teaching workflow. This keeps
    the BYOND HUD from contaminating terrain knowledge while preserving the full
    window in the diagnostic preview.
    """

    bottom_ratio: float = 0.75

    def __post_init__(self) -> None:
        ratio = float(self.bottom_ratio)
        if not 0.50 <= ratio <= 1.0:
            raise ValueError("bottom_ratio must be between 0.50 and 1.0")
        object.__setattr__(self, "bottom_ratio", ratio)

    def cutoff_y(self, frame_height: int) -> int:
        height = max(1, int(frame_height))
        return max(1, min(height, int(round(height * self.bottom_ratio))))

    def is_eligible(self, cell: ClassifiedGridCell, frame_height: int) -> bool:
        """Require the full calibrated cell to remain above the HUD cutoff."""

        return int(cell.crop.y1) <= self.cutoff_y(frame_height)

    def filter_eligible(
        self,
        cells: Iterable[TCell],
        frame_height: int,
    ) -> list[TCell]:
        return [cell for cell in cells if self.is_eligible(cell, frame_height)]
