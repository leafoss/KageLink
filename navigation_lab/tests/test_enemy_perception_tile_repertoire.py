from __future__ import annotations

import unittest

import numpy as np

from navigation_lab.enemy_perception.background_reference import BackgroundReferenceStore
from navigation_lab.enemy_perception.entity_candidate_validator import EntityCandidateValidator
from navigation_lab.enemy_perception.entity_classifier import EntityClassifier
from navigation_lab.enemy_perception.entity_extractor import EntityExtractor
from navigation_lab.enemy_perception.entity_knowledge import EntityKnowledgeBase
from navigation_lab.enemy_perception.entity_tracker import EntityTracker
from navigation_lab.enemy_perception.hostility_analyzer import HostilityAnalyzer
from navigation_lab.enemy_perception.models import TileKnowledgeState
from navigation_lab.enemy_perception.overlay_detector import OverlayDetector
from navigation_lab.enemy_perception.perception_engine import EnemyPerceptionEngine
from navigation_lab.enemy_perception.player_locator import PlayerLocator
from navigation_lab.observer.continuous_mapping import ContinuousMappingResult
from navigation_lab.observer.grid_cells import GridCellCrop
from navigation_lab.observer.motion import MotionSample
from navigation_lab.observer.tile_knowledge import TileClass, TileClassification
from navigation_lab.observer.tile_map_engine import ClassifiedGridCell, TileScanResult


PLAYER_CELL = (2, 1)
TARGET_CELL = (3, 1)


class FakeMapper:
    def __init__(self, mapping: ContinuousMappingResult) -> None:
        self.mapping = mapping

    def process_frame(self, _frame):
        return self.mapping


class ForbiddenConsensus:
    def observe(self, *_args, **_kwargs):
        raise AssertionError(
            "Scene consensus must not run in the operational pipeline"
        )


def build_mapping(
    frame: np.ndarray,
    target_class: TileClass = TileClass.UNKNOWN,
    target_confidence: float = 0.0,
) -> ContinuousMappingResult:
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
            if (column, row) == PLAYER_CELL:
                classification = TileClassification(
                    TileClass.PLAYER,
                    0.99,
                    True,
                    "player-example",
                )
            elif (column, row) == TARGET_CELL:
                classification = TileClassification(
                    target_class,
                    target_confidence,
                    target_class != TileClass.UNKNOWN,
                    (
                        "target-example"
                        if target_class != TileClass.UNKNOWN
                        else None
                    ),
                )
            else:
                classification = TileClassification(
                    TileClass.WALKABLE,
                    0.99,
                    True,
                    "walkable-example",
                )
            cells.append(ClassifiedGridCell(crop, classification))
    return ContinuousMappingResult(
        frame_index=1,
        scan=TileScanResult(frame.copy(), cells),
        player_screen=PLAYER_CELL,
        player_world=(0, 0),
        motion=MotionSample.baseline(),
        mapped_cells=0,
        confirmed_cells=0,
        provisional_cells=0,
        unknown_cells=1,
        settled=True,
        localization_reason="test",
    )


def build_engine(
    frame: np.ndarray,
    backgrounds: BackgroundReferenceStore,
    target_class: TileClass = TileClass.UNKNOWN,
    target_confidence: float = 0.0,
) -> EnemyPerceptionEngine:
    return EnemyPerceptionEngine(
        mapper=FakeMapper(
            build_mapping(frame, target_class, target_confidence)
        ),
        backgrounds=backgrounds,
        classifier=EntityClassifier(EntityKnowledgeBase()),
        tracker=EntityTracker(10, interest_radius_cells=4),
        hostility=HostilityAnalyzer(),
        detector=OverlayDetector(
            pixel_threshold=24,
            min_changed_ratio=0.03,
            min_component_area=12,
        ),
        extractor=EntityExtractor(64, 12, join_gap_px=1),
        recorder=None,
        playfield_bottom_ratio=0.75,
        interest_radius_cells=4,
        processing_radius_cells=5,
        semantic_entity_threshold=0.90,
        background_strong_threshold=0.95,
        background_usable_threshold=0.88,
        background_diagnostic_threshold=0.70,
        max_background_changed_ratio=0.65,
        max_background_mean_difference=55.0,
        candidate_validator=EntityCandidateValidator(64, 4),
        player_locator=PlayerLocator(64),
        scene_consensus=ForbiddenConsensus(),
    )


def target_record(result):
    return next(
        item for item in result.cells if item.screen_cell == TARGET_CELL
    )


class TileRepertoirePipelineTests(unittest.TestCase):
    def test_02_background_composite_preserves_real_tile_pixels(self) -> None:
        frame = np.full((256, 320, 3), 45, np.uint8)
        store = BackgroundReferenceStore()
        store.add_reference(
            None,
            "walkable",
            np.full((64, 64, 3), 40, np.uint8),
            source="taught_tile",
        )
        result, images = build_engine(frame, store).process_frame(frame)
        record = target_record(result)
        self.assertEqual(
            record.tile_knowledge_state,
            TileKnowledgeState.KNOWN_CLEAN.value,
        )
        self.assertTrue(
            np.array_equal(
                images["02_background_composite.png"][96, 224],
                frame[96, 224],
            )
        )

    def test_known_clean_has_no_operational_difference_or_mask(self) -> None:
        frame = np.full((256, 320, 3), 40, np.uint8)
        store = BackgroundReferenceStore()
        store.add_reference(
            None,
            "walkable",
            frame[:64, :64],
            source="taught_tile",
        )
        result, images = build_engine(frame, store).process_frame(frame)
        record = target_record(result)
        self.assertEqual(record.tile_knowledge_state, "known_clean")
        self.assertFalse(record.difference_operational)
        self.assertFalse(record.residual_candidate_created)
        self.assertEqual(
            int(
                images["04_mask_composite.png"][64:128, 192:256].sum()
            ),
            0,
        )

    def test_known_terrain_with_localized_sprite_becomes_foreign_body(self) -> None:
        frame = np.full((256, 320, 3), 40, np.uint8)
        frame[76:116, 212:236] = 180
        store = BackgroundReferenceStore()
        store.add_reference(
            None,
            "walkable",
            np.full((64, 64, 3), 40, np.uint8),
            source="taught_tile",
        )
        result, images = build_engine(frame, store).process_frame(frame)
        record = target_record(result)
        self.assertEqual(
            record.tile_knowledge_state,
            TileKnowledgeState.KNOWN_WITH_FOREIGN_BODY.value,
        )
        self.assertTrue(record.valid_repertoire_match)
        self.assertTrue(record.difference_operational)
        self.assertTrue(record.residual_candidate_created)
        self.assertGreater(
            int(
                images["04_mask_composite.png"][64:128, 192:256].sum()
            ),
            0,
        )
        self.assertGreaterEqual(len(result.entities), 1)
        self.assertEqual(result.entities[0].distance_to_player, 1)

    def test_unknown_tile_never_generates_operational_mask_or_entity(self) -> None:
        frame = np.full((256, 320, 3), 40, np.uint8)
        frame[64:128, 192:256] = 220
        store = BackgroundReferenceStore()
        store.add_reference(
            None,
            "walkable",
            np.full((64, 64, 3), 40, np.uint8),
            source="taught_tile",
        )
        result, images = build_engine(frame, store).process_frame(frame)
        record = target_record(result)
        self.assertEqual(
            record.tile_knowledge_state,
            TileKnowledgeState.UNKNOWN_TILE.value,
        )
        self.assertFalse(record.valid_repertoire_match)
        self.assertFalse(record.difference_operational)
        self.assertFalse(record.residual_candidate_created)
        self.assertEqual(
            int(
                images["04_mask_composite.png"][64:128, 192:256].sum()
            ),
            0,
        )
        self.assertEqual(result.entities, [])

    def test_scene_consensus_reference_is_not_operational_repertoire(self) -> None:
        frame = np.full((256, 320, 3), 40, np.uint8)
        frame[64:128, 192:256] = 180
        store = BackgroundReferenceStore()
        store.add_reference(
            None,
            "walkable",
            np.full((64, 64, 3), 180, np.uint8),
            source="scene_consensus",
        )
        store.add_reference(
            None,
            "walkable",
            np.full((64, 64, 3), 40, np.uint8),
            source="taught_tile",
        )
        result, _images = build_engine(frame, store).process_frame(frame)
        record = target_record(result)
        self.assertEqual(record.tile_knowledge_state, "unknown_tile")
        self.assertFalse(record.valid_repertoire_match)
        self.assertFalse(result.background["scene_consensus_operational"])

    def test_semantic_npc_still_tracks_without_terrain_reference(self) -> None:
        frame = np.full((256, 320, 3), 40, np.uint8)
        frame[64:128, 192:256] = 180
        result, _images = build_engine(
            frame,
            BackgroundReferenceStore(),
            TileClass.NPC,
            0.947,
        ).process_frame(frame)
        record = target_record(result)
        self.assertEqual(record.tile_knowledge_state, "semantic_entity")
        self.assertTrue(record.semantic_candidate_created)
        self.assertEqual(len(result.entities), 1)
        self.assertEqual(result.entities[0].distance_to_player, 1)


if __name__ == "__main__":
    unittest.main()
