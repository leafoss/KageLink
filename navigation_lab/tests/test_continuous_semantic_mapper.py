from __future__ import annotations

import unittest

import numpy as np

from navigation_lab.observer.continuous_mapping import (
    ContinuousSemanticMapper,
    SemanticWorldMap,
    UnknownReviewQueue,
)
from navigation_lab.observer.grid_calibration import GridCalibration
from navigation_lab.observer.grid_cells import extract_grid_cells
from navigation_lab.observer.tile_knowledge import TileClass, TileFeatureExtractor, TileKnowledgeBase


class SemanticWorldMapTests(unittest.TestCase):
    def test_player_and_npc_do_not_replace_terrain(self) -> None:
        world = SemanticWorldMap()
        world.observe(4, 7, TileClass.WALKABLE, 0.98, True, 1, "t1")
        world.observe(4, 7, TileClass.PLAYER, 0.99, True, 1, "t1")
        world.observe(5, 7, TileClass.NPC, 0.96, True, 1, "t1")

        player_cell = world.cells[(4, 7)]
        npc_cell = world.cells[(5, 7)]
        self.assertEqual(player_cell.resolved_terrain, TileClass.WALKABLE)
        self.assertIn(TileClass.PLAYER, player_cell.occupants)
        self.assertIsNone(npc_cell.resolved_terrain)
        self.assertIn(TileClass.NPC, npc_cell.occupants)

    def test_dynamic_occupants_expire_without_erasing_terrain(self) -> None:
        world = SemanticWorldMap()
        world.observe(1, 2, TileClass.WALKABLE, 0.97, True, 1, "t1")
        world.observe(1, 2, TileClass.NPC, 0.95, True, 1, "t1")
        world.expire_dynamic(frame_index=20, ttl_frames=8)
        cell = world.cells[(1, 2)]
        self.assertEqual(cell.resolved_terrain, TileClass.WALKABLE)
        self.assertNotIn(TileClass.NPC, cell.occupants)

    def test_world_round_trip_preserves_evidence(self) -> None:
        world = SemanticWorldMap()
        world.observe(-2, 3, TileClass.WALL, 0.99, True, 4, "t4")
        restored = SemanticWorldMap.from_dict(world.to_dict())
        self.assertEqual(restored.cells[(-2, 3)].resolved_terrain, TileClass.WALL)
        self.assertEqual(restored.terrain_count, 1)


class UnknownReviewQueueTests(unittest.TestCase):
    def test_identical_unknown_tiles_form_one_group(self) -> None:
        crop = np.full((60, 60, 3), (40, 90, 180), dtype=np.uint8)
        feature = TileFeatureExtractor().extract(crop)
        queue = UnknownReviewQueue(grouping_threshold=0.99)
        first = queue.add(crop, feature, 0.42, "r01_c01", 1)
        second = queue.add(crop, feature, 0.44, "r04_c08", 2)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(queue.groups), 1)
        self.assertEqual(first.count, 2)
        self.assertEqual(first.latest_screen_cell, "r04_c08")

    def test_queue_round_trip_keeps_group_counts(self) -> None:
        crop = np.full((60, 60, 3), 80, dtype=np.uint8)
        feature = TileFeatureExtractor().extract(crop)
        queue = UnknownReviewQueue()
        queue.add(crop, feature, 0.10, "r00_c00", 3)
        restored = UnknownReviewQueue.from_dict(queue.to_dict())
        self.assertEqual(len(restored.groups), 1)
        self.assertEqual(next(iter(restored.groups.values())).count, 1)


class ContinuousSemanticMapperTests(unittest.TestCase):
    def _knowledge_for_frame(self, frame: np.ndarray, calibration: GridCalibration) -> TileKnowledgeBase:
        cells = extract_grid_cells(frame, calibration)
        knowledge = TileKnowledgeBase(similarity_threshold=0.99)
        knowledge.add_example(cells[0].image, TileClass.WALKABLE)
        knowledge.add_example(cells[-1].image, TileClass.PLAYER)
        return knowledge

    def test_first_settled_frame_builds_relative_world_around_player(self) -> None:
        calibration = GridCalibration(tile_size_px=64)
        frame = np.zeros((128, 128, 3), dtype=np.uint8)
        frame[:, :] = (35, 150, 75)
        frame[64:128, 64:128] = (30, 30, 220)
        knowledge = self._knowledge_for_frame(frame, calibration)
        mapper = ContinuousSemanticMapper(
            calibration,
            knowledge,
            auto_threshold=0.99,
            review_threshold=0.98,
        )

        result = mapper.process_frame(frame)
        self.assertEqual(result.player_screen, (1, 1))
        self.assertEqual(result.player_world, (0, 0))
        self.assertTrue(result.settled)
        self.assertGreaterEqual(mapper.world.terrain_count, 3)
        self.assertIn(TileClass.PLAYER, mapper.world.cells[(0, 0)].occupants)
        self.assertIsNone(mapper.world.cells[(0, 0)].resolved_terrain)

    def test_player_screen_cell_change_updates_relative_world_position(self) -> None:
        calibration = GridCalibration(tile_size_px=64)
        first = np.zeros((128, 128, 3), dtype=np.uint8)
        first[:, :] = (35, 150, 75)
        first[64:128, 64:128] = (30, 30, 220)
        knowledge = self._knowledge_for_frame(first, calibration)
        mapper = ContinuousSemanticMapper(
            calibration,
            knowledge,
            auto_threshold=0.99,
            review_threshold=0.98,
        )
        mapper.process_frame(first)

        second = np.zeros((128, 128, 3), dtype=np.uint8)
        second[:, :] = (35, 150, 75)
        second[64:128, 0:64] = (30, 30, 220)
        result = mapper.process_frame(second)
        self.assertEqual(result.player_screen, (0, 1))
        self.assertEqual(result.player_world, (-1, 0))
        self.assertEqual(result.localization_reason, "player_screen_cell_delta")

    def test_mapper_state_round_trip_preserves_world_and_review_queue(self) -> None:
        calibration = GridCalibration(tile_size_px=64)
        knowledge = TileKnowledgeBase(similarity_threshold=0.99)
        mapper = ContinuousSemanticMapper(calibration, knowledge)
        mapper.player_world = (8, -3)
        mapper.world.observe(8, -3, TileClass.WALKABLE, 0.96, True, 1, "t1")
        crop = np.full((60, 60, 3), 90, dtype=np.uint8)
        feature = knowledge.extractor.extract(crop)
        mapper.review_queue.add(crop, feature, 0.22, "r02_c03", 1)

        restored = ContinuousSemanticMapper(calibration, TileKnowledgeBase())
        restored.restore_state(mapper.to_dict())
        self.assertEqual(restored.player_world, (8, -3))
        self.assertEqual(restored.world.cells[(8, -3)].resolved_terrain, TileClass.WALKABLE)
        self.assertEqual(len(restored.review_queue.groups), 1)


if __name__ == "__main__":
    unittest.main()
