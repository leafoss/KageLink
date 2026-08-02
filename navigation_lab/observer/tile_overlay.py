from __future__ import annotations

from typing import Any

from .tile_knowledge import TileClass
from .tile_map_engine import ClassifiedGridCell, TileScanResult


CATEGORY_COLORS_BGR: dict[TileClass, tuple[int, int, int]] = {
    TileClass.UNKNOWN: (0, 170, 255),
    TileClass.WALKABLE: (60, 210, 80),
    TileClass.WALL: (40, 40, 230),
    TileClass.WALKABLE_WITH_JUTSU: (230, 210, 40),
    TileClass.BLOCKING_OBJECT: (30, 130, 240),
    TileClass.PLAYER: (255, 255, 255),
    TileClass.NPC: (180, 90, 255),
    TileClass.TRANSITION: (210, 60, 210),
    TileClass.DANGER: (20, 230, 230),
    TileClass.IGNORE_DYNAMIC: (150, 150, 150),
}

CATEGORY_SYMBOLS: dict[TileClass, str] = {
    TileClass.UNKNOWN: "?",
    TileClass.WALKABLE: ".",
    TileClass.WALL: "#",
    TileClass.WALKABLE_WITH_JUTSU: "J",
    TileClass.BLOCKING_OBJECT: "B",
    TileClass.PLAYER: "P",
    TileClass.NPC: "N",
    TileClass.TRANSITION: "T",
    TileClass.DANGER: "!",
    TileClass.IGNORE_DYNAMIC: "I",
}

CATEGORY_SHORT_LABELS: dict[TileClass, str] = {
    TileClass.UNKNOWN: "DESC",
    TileClass.WALKABLE: "CHAO",
    TileClass.WALL: "PAREDE",
    TileClass.WALKABLE_WITH_JUTSU: "JUTSU",
    TileClass.BLOCKING_OBJECT: "BLOQ",
    TileClass.PLAYER: "PLAYER",
    TileClass.NPC: "NPC",
    TileClass.TRANSITION: "TRANS",
    TileClass.DANGER: "PERIGO",
    TileClass.IGNORE_DYNAMIC: "IGNORAR",
}


def display_category(cell: ClassifiedGridCell) -> TileClass:
    """Return UNKNOWN whenever the nearest example did not pass the active threshold."""

    return cell.classification.category if cell.classification.known else TileClass.UNKNOWN


def tile_overlay_text(cell: ClassifiedGridCell) -> tuple[str, str]:
    category = display_category(cell)
    confidence = max(0.0, min(1.0, float(cell.classification.confidence)))
    return (
        f"{CATEGORY_SYMBOLS[category]} {confidence:.0%}",
        CATEGORY_SHORT_LABELS[category],
    )


def render_tile_classification_overlay(
    scan: TileScanResult,
    *,
    selected_cell_id: str | None = None,
    auto_threshold: float = 0.95,
    review_threshold: float = 0.90,
    fill_opacity: float = 0.20,
) -> Any:
    """Render the captured game frame with the calibrated tile grid and classifier output."""

    import cv2

    if scan.frame is None or not hasattr(scan.frame, "shape") or scan.frame.size == 0:
        raise ValueError("scan.frame must be a non-empty image")
    if not 0.0 <= fill_opacity <= 1.0:
        raise ValueError("fill_opacity must be between 0.0 and 1.0")
    if not 0.0 <= review_threshold <= auto_threshold <= 1.0:
        raise ValueError("thresholds must satisfy review_threshold <= auto_threshold")

    frame = scan.frame.copy()
    tint = frame.copy()
    for cell in scan.cells:
        category = display_category(cell)
        cv2.rectangle(
            tint,
            (cell.crop.x0, cell.crop.y0),
            (cell.crop.x1 - 1, cell.crop.y1 - 1),
            CATEGORY_COLORS_BGR[category],
            -1,
        )
    if scan.cells and fill_opacity > 0.0:
        cv2.addWeighted(tint, fill_opacity, frame, 1.0 - fill_opacity, 0.0, frame)

    for cell in scan.cells:
        category = display_category(cell)
        confidence = float(cell.classification.confidence)
        selected = cell.crop.id == selected_cell_id
        if selected:
            border = (255, 255, 255)
            thickness = 4
        elif category == TileClass.UNKNOWN or confidence < review_threshold:
            border = CATEGORY_COLORS_BGR[TileClass.UNKNOWN]
            thickness = 3
        elif confidence < auto_threshold:
            border = (0, 230, 255)
            thickness = 2
        else:
            border = CATEGORY_COLORS_BGR[category]
            thickness = 2

        cv2.rectangle(
            frame,
            (cell.crop.x0, cell.crop.y0),
            (cell.crop.x1 - 1, cell.crop.y1 - 1),
            border,
            thickness,
        )
        primary, secondary = tile_overlay_text(cell)
        x = cell.crop.x0 + 4
        y = cell.crop.y0 + 16
        _put_outlined_text(frame, primary, (x, y), 0.39)
        _put_outlined_text(frame, secondary, (x, y + 15), 0.30)

    return frame


def _put_outlined_text(frame: Any, text: str, origin: tuple[int, int], scale: float) -> None:
    import cv2

    cv2.putText(
        frame,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (0, 0, 0),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
