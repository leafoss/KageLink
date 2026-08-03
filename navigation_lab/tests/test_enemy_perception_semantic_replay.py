from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from navigation_lab.enemy_perception.async_debug_writer import AsyncDebugWriter
from navigation_lab.enemy_perception.background_reference import BackgroundReferenceStore
from navigation_lab.enemy_perception.debug_recorder import DebugRecorder
from navigation_lab.enemy_perception.entity_candidate_validator import EntityCandidateValidator
from navigation_lab.enemy_perception.entity_classifier import EntityClassifier
from navigation_lab.enemy_perception.entity_extractor import EntityExtractor
from navigation_lab.enemy_perception.entity_knowledge import EntityKnowledgeBase
from navigation_lab.enemy_perception.entity_tracker import EntityTracker
from navigation_lab.enemy_perception.hostility_analyzer import HostilityAnalyzer
from navigation_lab.enemy_perception.models import PlayerLocationSource
from navigation_lab.enemy_perception.overlay_detector import OverlayDetector
from navigation_lab.enemy_perception.perception_engine import EnemyPerceptionEngine
from navigation_lab.enemy_perception.player_locator import PlayerLocator
from navigation_lab.enemy_perception.scene_consensus import SceneConsensusLearner
from navigation_lab.observer.continuous_mapping import ContinuousMappingResult
from navigation_lab.observer.grid_cells import GridCellCrop
from navigation_lab.observer.motion import MotionSample
from navigation_lab.observer.tile_knowledge import TileClass, TileClassification
from navigation_lab.observer.tile_map_engine import ClassifiedGridCell, TileScanResult


def mapping_for(frame: np.ndarray, frame_index: int = 1, visual_player: bool = False):
    cells = []
    for row in range(4):
        for column in range(5):
            x0, y0 = column * 64, row * 64
            crop = GridCellCrop(
                row,
                column,
                x0,
                y0,
                x0 + 64,
                y0 + 64,
                frame[y0 : y0 + 64, x0 : x0 + 64].copy(),
            )
            if (column, row) == (3, 2):
                classification = TileClassification(
                    TileClass.NPC,
                    0.947,
                    True,
                    "npc-example",
                )
            elif visual_player and (column, row) == (2, 2):
                classification = TileClassification(
                    TileClass.PLAYER,
                    0.98,
                    True,
                    "player-example",
                )
            else:
                classification = TileClassification(
                    TileClass.UNKNOWN,
                    0.70,
                    False,
                    None,
                )
            cells.append(ClassifiedGridCell(crop, classification))
    return ContinuousMappingResult(
        frame_index=frame_index,
        scan=TileScanResult(frame.copy(), cells),
        player_screen=(2, 2) if visual_player else None,
        player_world=(0, 0) if visual_player else None,
        motion=MotionSample.baseline(),
        mapped_cells=0,
        confirmed_cells=0,
        provisional_cells=0,
        unknown_cells=19,
        settled=True,
        localization_reason="test",
    )


class FakeMapper:
    def __init__(self, mappings):
        self.mappings = list(mappings)
        self.index = 0

    def process_frame(self, _frame):
        result = self.mappings[self.index]
        self.index += 1
        return result


class PlayerLocatorTests(unittest.TestCase):
    def test_playfield_ratio_fallback_selects_expected_cell(self) -> None:
        frame = np.zeros((320, 320, 3), np.uint8)
        mapping = mapping_for(frame)
        locator = PlayerLocator(
            tile_size_px=64,
            anchor_x_ratio=0.50,
            anchor_y_ratio=0.57,
        )
        result = locator.locate(mapping, frame_width=320, playfield_cutoff_y=240)
        self.assertEqual(result.source, PlayerLocationSource.CALIBRATED_ANCHOR_FALLBACK)
        self.assertEqual(result.screen_cell, (2, 2))

    def test_visual_confirmation_has_priority(self) -> None:
        frame = np.zeros((320, 320, 3), np.uint8)
        locator = PlayerLocator(tile_size_px=64)
        result = locator.locate(
            mapping_for(frame, visual_player=True),
            frame_width=320,
            playfield_cutoff_y=240,
        )
        self.assertEqual(result.source, PlayerLocationSource.VISUAL_CONFIRMED)
        self.assertGreater(result.confidence, 0.95)

    def test_temporal_prediction_requires_prior_visual_confirmation(self) -> None:
        frame = np.zeros((320, 320, 3), np.uint8)
        locator = PlayerLocator(tile_size_px=64, temporal_ttl_frames=10)
        first = locator.locate(
            mapping_for(frame, frame_index=1),
            frame_width=320,
            playfield_cutoff_y=240,
        )
        self.assertEqual(first.source, PlayerLocationSource.CALIBRATED_ANCHOR_FALLBACK)
        second = locator.locate(
            mapping_for(frame, frame_index=2),
            frame_width=320,
            playfield_cutoff_y=240,
        )
        self.assertEqual(second.source, PlayerLocationSource.CALIBRATED_ANCHOR_FALLBACK)


class SemanticNpcPathTests(unittest.TestCase):
    def build_engine(self, mapping):
        backgrounds = BackgroundReferenceStore()
        return EnemyPerceptionEngine(
            mapper=FakeMapper([mapping]),
            backgrounds=backgrounds,
            classifier=EntityClassifier(EntityKnowledgeBase()),
            tracker=EntityTracker(10, interest_radius_cells=4),
            hostility=HostilityAnalyzer(),
            detector=OverlayDetector(24, 0.03, 12),
            extractor=EntityExtractor(64, 12, join_gap_px=1),
            recorder=None,
            playfield_bottom_ratio=0.75,
            interest_radius_cells=4,
            processing_radius_cells=5,
            semantic_entity_threshold=0.90,
            background_strong_threshold=0.95,
            background_usable_threshold=0.88,
            background_diagnostic_threshold=0.70,
            candidate_validator=EntityCandidateValidator(64, 4),
            player_locator=PlayerLocator(
                64,
                anchor_x_ratio=0.50,
                anchor_y_ratio=0.57,
            ),
            scene_consensus=SceneConsensusLearner(backgrounds, 8, 4, 0.94),
        )

    def test_npc_0947_creates_d1_track_without_background(self) -> None:
        frame = np.zeros((320, 320, 3), np.uint8)
        frame[128:192, 192:256] = 180
        result, _images = self.build_engine(mapping_for(frame)).process_frame(frame)
        self.assertTrue(result.player["recognized"])
        self.assertEqual(
            result.player["source"],
            PlayerLocationSource.CALIBRATED_ANCHOR_FALLBACK.value,
        )
        self.assertEqual(result.counters["semantic_candidates"], 1)
        self.assertEqual(result.counters["residual_candidates"], 0)
        self.assertEqual(len(result.entities), 1)
        self.assertIsNotNone(result.entities[0].track_id)
        self.assertEqual(result.entities[0].distance_to_player, 1)
        self.assertIn("semantic_npc", result.entities[0].candidate_sources)
        self.assertEqual(result.entities[0].semantic_confidence, 0.947)

    def test_npc_is_not_confirmed_hostile_from_semantics_alone(self) -> None:
        frame = np.zeros((320, 320, 3), np.uint8)
        frame[128:192, 192:256] = 180
        result, _images = self.build_engine(mapping_for(frame)).process_frame(frame)
        entity = result.entities[0]
        self.assertLess(entity.hostility_score, 8)
        self.assertFalse(entity.attack_recommended)


class BackgroundClusterTests(unittest.TestCase):
    def test_visual_clusters_separate_different_walkable_appearances(self) -> None:
        store = BackgroundReferenceStore(cluster_similarity=0.94)
        store.add_reference(None, "walkable", np.full((64, 64, 3), 40, np.uint8))
        store.add_reference(None, "walkable", np.full((64, 64, 3), 180, np.uint8))
        self.assertEqual(len(store.clusters_by_class["walkable"]), 2)


class DebugModeTests(unittest.TestCase):
    def test_async_writer_flushes_all_jobs(self) -> None:
        values = []
        writer = AsyncDebugWriter(max_queue_size=4)
        for value in range(8):
            writer.submit(values.append, value)
        writer.close()
        self.assertEqual(values, list(range(8)))

    def test_balanced_mode_keeps_frame_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = DebugRecorder(
                Path(directory),
                "balanced",
                debug_mode="Balanced",
                debug_stride=5,
            )
            self.assertTrue(recorder.enabled)
            self.assertEqual(recorder.debug_mode, "balanced")
            recorder.finalize({})


if __name__ == "__main__":
    unittest.main()
