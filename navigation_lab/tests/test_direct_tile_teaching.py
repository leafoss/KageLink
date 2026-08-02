from __future__ import annotations

import unittest

import numpy as np

from navigation_lab.observer.continuous_mapping import ContinuousSemanticMapper
from navigation_lab.observer.direct_tile_teaching import DirectTileSelection, teach_direct_selection
from navigation_lab.observer.grid_calibration import GridCalibration
from navigation_lab.observer.grid_cells import GridCellCrop
from navigation_lab.observer.tile_knowledge import TileClass, TileClassification, TileKnowledgeBase
from navigation_lab.observer.tile_map_engine import ClassifiedGridCell


class DirectTileTeachingTests(unittest.TestCase):
    def _cell(self, image: np.ndarray, category: TileClass, confidence: float, known: bool) -> ClassifiedGridCell:
        return ClassifiedGridCell(
            crop=GridCellCrop(
                row=3,
                column=5,
                x0=320,
                y0=192,
                x1=384,
                y1=256,
                image=image,
            ),
            classification=TileClassification(
                category=category,
                confidence=confidence,
                known=known,
            ),
        )

    def test_selection_keeps_an_independent_copy_of_clicked_crop(self) -> None:
        image = np.full((60, 60, 3), 90, dtype=np.uint8)
        selection = DirectTileSelection.from_cell(
            self._cell(image, TileClass.UNKNOWN, 0.51, False)
        )

        image[:, :] = 0

        self.assertEqual(selection.cell_id, "r03_c05")
        self.assertEqual(selection.bounds, (320, 192, 384, 256))
        self.assertEqual(selection.estimated_category, TileClass.UNKNOWN)
        self.assertAlmostEqual(selection.confidence, 0.51)
        self.assertTrue(np.all(selection.image == 90))

    def test_direct_correction_wins_exact_tie_and_prunes_resolved_group(self) -> None:
        crop = np.full((60, 60, 3), (40, 120, 180), dtype=np.uint8)
        knowledge = TileKnowledgeBase(similarity_threshold=0.90)
        knowledge.add_example(crop, TileClass.WALKABLE)
        mapper = ContinuousSemanticMapper(
            GridCalibration(tile_size_px=64),
            knowledge,
            review_threshold=0.90,
            auto_threshold=0.95,
        )
        feature = knowledge.extractor.extract(crop)
        mapper.review_queue.add(crop, feature, 0.50, "r03_c05", 1)
        selection = DirectTileSelection.from_cell(
            self._cell(crop, TileClass.WALKABLE, 1.0, True)
        )

        example, removed = teach_direct_selection(mapper, selection, TileClass.WALL)
        classified = mapper.knowledge.classify(crop, threshold=0.90)

        self.assertEqual(example.category, TileClass.WALL)
        self.assertEqual(classified.category, TileClass.WALL)
        self.assertTrue(classified.known)
        self.assertEqual(removed, 1)
        self.assertEqual(len(mapper.review_queue.groups), 0)


if __name__ == "__main__":
    unittest.main()
