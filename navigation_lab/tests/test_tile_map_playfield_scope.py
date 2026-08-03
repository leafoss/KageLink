from __future__ import annotations

import unittest

from navigation_lab.observer.grid_cells import GridCellCrop
from navigation_lab.observer.playfield_learning_scope import PlayfieldLearningScope
from navigation_lab.observer.tile_knowledge import TileClass, TileClassification
from navigation_lab.observer.tile_map_engine import ClassifiedGridCell


def _cell(identifier_row: int, y0: int, y1: int) -> ClassifiedGridCell:
    return ClassifiedGridCell(
        crop=GridCellCrop(
            row=identifier_row,
            column=0,
            x0=0,
            y0=y0,
            x1=64,
            y1=y1,
            image=None,
        ),
        classification=TileClassification(
            category=TileClass.UNKNOWN,
            confidence=0.0,
            known=False,
        ),
    )


class PlayfieldLearningScopeTests(unittest.TestCase):
    def test_default_cutoff_matches_three_quarters_of_frame(self) -> None:
        scope = PlayfieldLearningScope()
        self.assertEqual(scope.cutoff_y(500), 375)

    def test_full_cell_above_cutoff_is_eligible(self) -> None:
        scope = PlayfieldLearningScope(0.75)
        self.assertTrue(scope.is_eligible(_cell(0, 288, 352), 500))

    def test_cell_crossing_cutoff_is_not_eligible(self) -> None:
        scope = PlayfieldLearningScope(0.75)
        self.assertFalse(scope.is_eligible(_cell(1, 352, 416), 500))

    def test_hud_cells_are_removed_from_learning_queue(self) -> None:
        scope = PlayfieldLearningScope(0.75)
        playfield = _cell(0, 288, 352)
        hud = _cell(1, 416, 480)
        self.assertEqual(scope.filter_eligible([playfield, hud], 500), [playfield])

    def test_ratio_validation_rejects_unsafe_values(self) -> None:
        with self.assertRaises(ValueError):
            PlayfieldLearningScope(0.49)
        with self.assertRaises(ValueError):
            PlayfieldLearningScope(1.01)


if __name__ == "__main__":
    unittest.main()
