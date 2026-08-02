from __future__ import annotations

import unittest

import numpy as np

from navigation_lab.observer.grid_cells import GridCellCrop
from navigation_lab.observer.tile_knowledge import TileClass, TileClassification
from navigation_lab.observer.tile_map_engine import ClassifiedGridCell, TileScanResult
from navigation_lab.observer.tile_overlay import (
    display_category,
    render_tile_classification_overlay,
    tile_overlay_text,
)


class TileOverlayTests(unittest.TestCase):
    def _cell(
        self,
        column: int,
        category: TileClass,
        confidence: float,
        known: bool,
    ) -> ClassifiedGridCell:
        x0 = column * 64
        return ClassifiedGridCell(
            crop=GridCellCrop(
                row=0,
                column=column,
                x0=x0,
                y0=0,
                x1=x0 + 64,
                y1=64,
                image=np.zeros((60, 60, 3), dtype=np.uint8),
            ),
            classification=TileClassification(
                category=category,
                confidence=confidence,
                known=known,
            ),
        )

    def test_unknown_display_category_ignores_nearest_unaccepted_class(self) -> None:
        cell = self._cell(0, TileClass.WALKABLE, 0.78, False)
        self.assertEqual(display_category(cell), TileClass.UNKNOWN)
        self.assertEqual(tile_overlay_text(cell), ("? 78%", "DESC"))

    def test_overlay_keeps_frame_size_and_marks_each_cell(self) -> None:
        frame = np.full((64, 128, 3), 30, dtype=np.uint8)
        scan = TileScanResult(
            frame=frame,
            cells=[
                self._cell(0, TileClass.WALKABLE, 0.98, True),
                self._cell(1, TileClass.UNKNOWN, 0.43, False),
            ],
        )

        rendered = render_tile_classification_overlay(scan)

        self.assertEqual(rendered.shape, frame.shape)
        self.assertFalse(np.array_equal(rendered[:, :64], frame[:, :64]))
        self.assertFalse(np.array_equal(rendered[:, 64:], frame[:, 64:]))

    def test_selected_cell_receives_white_border(self) -> None:
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        cell = self._cell(0, TileClass.WALL, 0.99, True)

        rendered = render_tile_classification_overlay(
            TileScanResult(frame=frame, cells=[cell]),
            selected_cell_id=cell.crop.id,
        )

        self.assertTrue(
            np.array_equal(
                rendered[0, 0],
                np.array([255, 255, 255], dtype=np.uint8),
            )
        )


if __name__ == "__main__":
    unittest.main()
