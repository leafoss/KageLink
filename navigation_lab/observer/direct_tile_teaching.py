from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .continuous_mapping import ContinuousSemanticMapper
from .tile_knowledge import TileClass
from .tile_map_engine import ClassifiedGridCell


@dataclass(slots=True)
class DirectTileSelection:
    """Stable copy of one visible tile selected directly from the live preview."""

    cell_id: str
    row: int
    column: int
    bounds: tuple[int, int, int, int]
    estimated_category: TileClass
    confidence: float
    known: bool
    image: Any = field(repr=False, compare=False)

    @classmethod
    def from_cell(cls, cell: ClassifiedGridCell) -> "DirectTileSelection":
        classification = cell.classification
        category = classification.category if classification.known else TileClass.UNKNOWN
        return cls(
            cell_id=cell.crop.id,
            row=cell.crop.row,
            column=cell.crop.column,
            bounds=(cell.crop.x0, cell.crop.y0, cell.crop.x1, cell.crop.y1),
            estimated_category=category,
            confidence=float(classification.confidence),
            known=bool(classification.known),
            image=cell.crop.image.copy(),
        )


def teach_direct_selection(
    mapper: ContinuousSemanticMapper,
    selection: DirectTileSelection,
    category: TileClass,
) -> tuple[Any, int]:
    """Teach one clicked crop immediately and remove review groups it now resolves."""

    if category == TileClass.UNKNOWN:
        raise ValueError("UNKNOWN cannot be taught")

    example = mapper.knowledge.add_example(
        selection.image,
        category,
        notes=f"direct live-preview selection {selection.cell_id}",
    )

    # Direct corrections must win an exact-confidence tie against an older example.
    mapper.knowledge.examples.remove(example)
    mapper.knowledge.examples.insert(0, example)

    removed = 0
    for group_id, group in list(mapper.review_queue.groups.items()):
        image = group.representative_image
        if image is None:
            continue
        classification = mapper.knowledge.classify(
            image,
            threshold=mapper.review_threshold,
        )
        if classification.known:
            mapper.review_queue.remove(group_id)
            removed += 1

    return example, removed
