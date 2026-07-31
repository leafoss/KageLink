from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .grid_calibration import GridCalibration
from .grid_cells import GridCellCrop, extract_grid_cells
from .tile_knowledge import TileClass, TileClassification, TileKnowledgeBase


@dataclass(slots=True)
class ClassifiedGridCell:
    crop: GridCellCrop
    classification: TileClassification


@dataclass(slots=True)
class TileScanResult:
    frame: Any
    cells: list[ClassifiedGridCell]

    @property
    def unknown_cells(self) -> list[ClassifiedGridCell]:
        return [cell for cell in self.cells if not cell.classification.known]

    def counts(self) -> dict[TileClass, int]:
        counter = Counter(cell.classification.category for cell in self.cells)
        return {category: int(counter.get(category, 0)) for category in TileClass}

    def find_at(self, x: int, y: int) -> ClassifiedGridCell | None:
        return next((cell for cell in self.cells if cell.crop.contains(x, y)), None)


class SemanticTileMapEngine:
    """Split a calibrated game frame into cells and classify each crop."""

    def __init__(
        self,
        calibration: GridCalibration,
        knowledge: TileKnowledgeBase,
        similarity_threshold: float | None = None,
        crop_inset_px: int = 2,
    ) -> None:
        self.calibration = calibration
        self.knowledge = knowledge
        self.similarity_threshold = (
            knowledge.similarity_threshold if similarity_threshold is None else float(similarity_threshold)
        )
        self.crop_inset_px = max(0, int(crop_inset_px))

    def scan(self, frame: Any) -> TileScanResult:
        cells = extract_grid_cells(frame, self.calibration, inset_px=self.crop_inset_px)
        classified = [
            ClassifiedGridCell(
                crop=cell,
                classification=self.knowledge.classify(
                    cell.image,
                    threshold=self.similarity_threshold,
                ),
            )
            for cell in cells
        ]
        return TileScanResult(frame=frame.copy(), cells=classified)

    def teach(self, cell: ClassifiedGridCell, category: TileClass) -> str:
        example = self.knowledge.add_example(cell.crop.image, category)
        return example.id
