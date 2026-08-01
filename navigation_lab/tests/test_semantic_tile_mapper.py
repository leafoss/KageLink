from __future__ import annotations

import unittest

import numpy as np

from navigation_lab.observer.grid_calibration import GridCalibration
from navigation_lab.observer.grid_cells import extract_grid_cells, grid_boundaries
from navigation_lab.observer.tile_knowledge import TileClass, TileKnowledgeBase
from navigation_lab.observer.tile_map_engine import SemanticTileMapEngine


class GridCellExtractionTests(unittest.TestCase):
    def test_exact_128_image_yields_four_64px_cells(self) -> None:
        frame = np.zeros((128, 128, 3), dtype=np.uint8)
        calibration = GridCalibration(tile_size_px=64, offset_x_px=0, offset_y_px=0)
        cells = extract_grid_cells(frame, calibration, inset_px=2)
        self.assertEqual(grid_boundaries(128, 64, 0), (0, 64, 128))
        self.assertEqual(len(cells), 4)
        self.assertEqual({cell.id for cell in cells}, {"r00_c00", "r00_c01", "r01_c00", "r01_c01"})
        self.assertTrue(all(cell.image.shape[:2] == (60, 60) for cell in cells))

    def test_offset_excludes_partial_border_cells(self) -> None:
        frame = np.zeros((150, 150, 3), dtype=np.uint8)
        calibration = GridCalibration(tile_size_px=64, offset_x_px=10, offset_y_px=10)
        cells = extract_grid_cells(frame, calibration)
        self.assertEqual(grid_boundaries(150, 64, 10), (10, 74, 138))
        self.assertEqual(len(cells), 4)


class TileKnowledgeTests(unittest.TestCase):
    def test_identical_crop_is_recognized_after_teaching(self) -> None:
        crop = np.zeros((60, 60, 3), dtype=np.uint8)
        crop[:, :] = (25, 140, 70)
        knowledge = TileKnowledgeBase(similarity_threshold=0.99)
        example = knowledge.add_example(crop, TileClass.WALKABLE)
        result = knowledge.classify(crop)
        self.assertTrue(result.known)
        self.assertEqual(result.category, TileClass.WALKABLE)
        self.assertEqual(result.matched_example_id, example.id)
        self.assertGreaterEqual(result.confidence, 0.999)

    def test_empty_knowledge_returns_unknown(self) -> None:
        crop = np.zeros((60, 60, 3), dtype=np.uint8)
        result = TileKnowledgeBase().classify(crop)
        self.assertFalse(result.known)
        self.assertEqual(result.category, TileClass.UNKNOWN)

    def test_round_trip_preserves_examples(self) -> None:
        crop = np.full((60, 60, 3), 120, dtype=np.uint8)
        knowledge = TileKnowledgeBase(similarity_threshold=0.94)
        knowledge.add_example(crop, TileClass.WALL, notes="stone wall")
        restored = TileKnowledgeBase.from_dict(knowledge.to_dict())
        self.assertEqual(len(restored.examples), 1)
        self.assertEqual(restored.examples[0].category, TileClass.WALL)
        self.assertEqual(restored.examples[0].notes, "stone wall")
        self.assertAlmostEqual(restored.similarity_threshold, 0.94)

    def test_npc_category_is_taught_and_restored_separately(self) -> None:
        crop = np.zeros((60, 60, 3), dtype=np.uint8)
        crop[12:52, 20:42] = (180, 70, 40)
        knowledge = TileKnowledgeBase(similarity_threshold=0.99)
        knowledge.add_example(crop, TileClass.NPC, notes="village NPC")

        recognized = knowledge.classify(crop)
        self.assertTrue(recognized.known)
        self.assertEqual(recognized.category, TileClass.NPC)

        restored = TileKnowledgeBase.from_dict(knowledge.to_dict())
        self.assertEqual(restored.examples[0].category, TileClass.NPC)
        self.assertEqual(restored.counts()[TileClass.NPC], 1)
        self.assertEqual(restored.counts()[TileClass.BLOCKING_OBJECT], 0)


class SemanticTileMapEngineTests(unittest.TestCase):
    def test_one_example_reclassifies_matching_screen_cells(self) -> None:
        frame = np.zeros((64, 128, 3), dtype=np.uint8)
        frame[:, :64] = (30, 160, 80)
        frame[:, 64:] = (30, 160, 80)
        calibration = GridCalibration(tile_size_px=64)
        knowledge = TileKnowledgeBase(similarity_threshold=0.99)
        engine = SemanticTileMapEngine(calibration, knowledge)

        initial = engine.scan(frame)
        self.assertEqual(len(initial.unknown_cells), 2)
        knowledge.add_example(initial.cells[0].crop.image, TileClass.WALKABLE)
        learned = engine.scan(frame)
        self.assertEqual(len(learned.unknown_cells), 0)
        self.assertTrue(all(cell.classification.category == TileClass.WALKABLE for cell in learned.cells))


if __name__ == "__main__":
    unittest.main()
