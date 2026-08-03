from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from navigation_lab.enemy_perception.background_reference import BackgroundReferenceStore
from navigation_lab.enemy_perception.debug_recorder import DebugRecorder
from navigation_lab.enemy_perception.entity_extractor import EntityExtractor
from navigation_lab.enemy_perception.entity_features import EntityFeatureExtractor
from navigation_lab.enemy_perception.entity_knowledge import EntityKnowledgeBase
from navigation_lab.enemy_perception.entity_tracker import EntityTracker
from navigation_lab.enemy_perception.hostility_analyzer import HostilityAnalyzer
from navigation_lab.enemy_perception.models import (
    CellDebugRecord,
    EntityClass,
    EntityClassification,
    EntityObservation,
    EntityRegion,
    FramePerception,
    HostilityState,
    OverlayMetrics,
)
from navigation_lab.enemy_perception.overlay_detector import OverlayDetector
from navigation_lab.observer.grid_calibration import GridCalibration
from navigation_lab.observer.grid_cells import extract_grid_cells


def tile(value: int = 40) -> np.ndarray:
    return np.full((60, 60, 3), value, np.uint8)


def region(
    world: tuple[int, int] = (1, 1),
    value: int = 160,
    bbox: tuple[int, int, int, int] = (64, 64, 96, 112),
) -> EntityRegion:
    crop = np.full(
        (bbox[3] - bbox[1], bbox[2] - bbox[0], 3),
        value,
        np.uint8,
    )
    mask = np.full(crop.shape[:2], 255, np.uint8)
    return EntityRegion(
        bbox,
        world,
        world,
        [world],
        crop,
        mask,
        crop.copy(),
    )


def observation(
    world: tuple[int, int] = (1, 1),
    value: int = 160,
    category: EntityClass = EntityClass.UNKNOWN_ENTITY,
    confidence: float = 0.2,
    frame: int = 1,
) -> EntityObservation:
    entity_region = region(world, value)
    feature = EntityFeatureExtractor().extract(
        entity_region.crop,
        entity_region.mask,
    )
    return EntityObservation(
        entity_region,
        feature,
        EntityClassification(
            category,
            confidence,
            category != EntityClass.UNKNOWN_ENTITY,
        ),
        frame,
    )


class BackgroundTests(unittest.TestCase):
    def test_01_missing_reference(self) -> None:
        self.assertFalse(BackgroundReferenceStore().choose((0, 0), tile()).available)

    def test_02_add_and_choose(self) -> None:
        store = BackgroundReferenceStore()
        reference_id = store.add_reference((0, 0), "walkable", tile())
        match = store.choose((0, 0), tile())
        self.assertEqual(match.reference_id, reference_id)
        self.assertGreater(match.confidence, 0.99)

    def test_03_best_animated_reference(self) -> None:
        store = BackgroundReferenceStore()
        store.add_reference((0, 0), "water", tile(20))
        expected = store.add_reference((0, 0), "water", tile(90))
        self.assertEqual(store.choose((0, 0), tile(92)).reference_id, expected)

    def test_04_requires_stable_frames(self) -> None:
        store = BackgroundReferenceStore(stable_frames=3)
        self.assertIsNone(store.observe_empty_candidate((0, 0), "walkable", tile(), True))
        self.assertIsNone(store.observe_empty_candidate((0, 0), "walkable", tile(), True))
        self.assertIsNotNone(store.observe_empty_candidate((0, 0), "walkable", tile(), True))

    def test_05_ineligible_not_learned(self) -> None:
        store = BackgroundReferenceStore()
        for _ in range(4):
            store.observe_empty_candidate((0, 0), "walkable", tile(), False)
        self.assertFalse(store.choose((0, 0), tile()).available)

    def test_06_unstable_candidate_resets(self) -> None:
        store = BackgroundReferenceStore(stable_frames=3)
        store.observe_empty_candidate((0, 0), "walkable", tile(20), True)
        store.observe_empty_candidate((0, 0), "walkable", tile(200), True)
        self.assertIsNone(store.observe_empty_candidate((0, 0), "walkable", tile(200), True))

    def test_07_max_references(self) -> None:
        store = BackgroundReferenceStore(max_references=2)
        for value in (10, 50, 100):
            store.add_reference((0, 0), "water", tile(value))
        self.assertEqual(len(store.references[(0, 0)]), 2)

    def test_08_persistence_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = BackgroundReferenceStore(Path(directory))
            store.add_reference((2, 3), "walkable", tile(77))
            restored = BackgroundReferenceStore(Path(directory))
            self.assertTrue(restored.choose((2, 3), tile(77)).available)


class OverlayTests(unittest.TestCase):
    def test_09_identical_no_overlay(self) -> None:
        self.assertFalse(OverlayDetector().detect(tile(), tile()).metrics.overlay_detected)

    def test_10_small_variation_tolerated(self) -> None:
        self.assertFalse(
            OverlayDetector(pixel_threshold=20)
            .detect(tile(40), tile(45))
            .metrics.overlay_detected
        )

    def test_11_sprite_detected(self) -> None:
        background = tile()
        current = background.copy()
        current[10:35, 20:40] = 220
        self.assertTrue(OverlayDetector().detect(current, background).metrics.overlay_detected)

    def test_12_noise_removed(self) -> None:
        background = tile()
        current = background.copy()
        current[1, 1] = 255
        self.assertFalse(
            OverlayDetector(min_component_area=5, morphology_kernel=1)
            .detect(current, background)
            .metrics.overlay_detected
        )

    def test_13_metrics_correct(self) -> None:
        background = tile()
        current = background.copy()
        current[0:10, 0:10] = 255
        metrics = OverlayDetector(
            min_changed_ratio=0.01,
            min_component_area=1,
            morphology_kernel=1,
        ).detect(current, background).metrics
        self.assertEqual(metrics.changed_pixel_count, 100)
        self.assertEqual(metrics.component_count, 1)

    def test_14_input_not_modified(self) -> None:
        background = tile()
        current = background.copy()
        before = current.copy()
        OverlayDetector().detect(current, background)
        self.assertTrue(np.array_equal(current, before))


class ExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = np.zeros((128, 128, 3), np.uint8)
        self.cells = extract_grid_cells(self.frame, GridCalibration(tile_size_px=64))

    @staticmethod
    def _result(mask: np.ndarray):
        from navigation_lab.enemy_perception.models import OverlayResult

        area = int(mask.sum() / 255)
        return OverlayResult(
            OverlayMetrics(
                changed_pixel_count=area,
                changed_pixel_ratio=float((mask > 0).mean()),
                component_count=1,
                largest_component_area=area,
                overlay_detected=True,
            ),
            np.dstack([mask] * 3),
            mask,
        )

    def test_15_single_component(self) -> None:
        mask = np.zeros((60, 60), np.uint8)
        mask[20:40, 20:40] = 255
        output = EntityExtractor().extract(
            self.frame,
            [(self.cells[0], self._result(mask), (0, 0))],
        )
        self.assertEqual(len(output), 1)

    def test_16_cross_cell_merge(self) -> None:
        left = np.zeros((60, 60), np.uint8)
        right = left.copy()
        left[20:40, 52:60] = 255
        right[20:40, 0:8] = 255
        output = EntityExtractor(join_gap_px=4).extract(
            self.frame,
            [
                (self.cells[0], self._result(left), (0, 0)),
                (self.cells[1], self._result(right), (1, 0)),
            ],
        )
        self.assertEqual(len(output), 1)

    def test_17_separate_entities(self) -> None:
        first = np.zeros((60, 60), np.uint8)
        second = first.copy()
        first[5:15, 5:15] = 255
        second[45:55, 45:55] = 255
        output = EntityExtractor(join_gap_px=1).extract(
            self.frame,
            [
                (self.cells[0], self._result(first), (0, 0)),
                (self.cells[3], self._result(second), (1, 1)),
            ],
        )
        self.assertEqual(len(output), 2)

    def test_18_anchor_is_bottom_cell(self) -> None:
        mask = np.zeros((60, 60), np.uint8)
        mask[40:59, 20:40] = 255
        output = EntityExtractor().extract(
            self.frame,
            [(self.cells[3], self._result(mask), (1, 1))],
        )
        self.assertEqual(output[0].anchor_screen_cell, (1, 1))

    def test_19_small_component_removed(self) -> None:
        mask = np.zeros((60, 60), np.uint8)
        mask[1:2, 1:2] = 255
        output = EntityExtractor(min_entity_area=5, join_gap_px=0).extract(
            self.frame,
            [(self.cells[0], self._result(mask), (0, 0))],
        )
        self.assertEqual(output, [])


class KnowledgeTests(unittest.TestCase):
    def test_20_feature_length_stable(self) -> None:
        extractor = EntityFeatureExtractor()
        first = region()
        second = region(value=80)
        self.assertEqual(
            len(extractor.extract(first.crop, first.mask)),
            len(extractor.extract(second.crop, second.mask)),
        )

    def test_21_identical_similarity(self) -> None:
        extractor = EntityFeatureExtractor()
        item = region()
        feature = extractor.extract(item.crop, item.mask)
        self.assertGreater(extractor.similarity(feature, feature), 0.999)

    def test_22_known_classification(self) -> None:
        knowledge = EntityKnowledgeBase(auto_threshold=0.95, review_threshold=0.90)
        item = region()
        knowledge.add_example(item.crop, item.mask, EntityClass.ENEMY)
        feature = knowledge.extractor.extract(item.crop, item.mask)
        self.assertEqual(knowledge.classify_feature(feature).category, EntityClass.ENEMY)

    def test_23_unknown_classification(self) -> None:
        self.assertFalse(EntityKnowledgeBase().classify_feature([1, 0, 0]).known)

    def test_24_unknown_grouping(self) -> None:
        knowledge = EntityKnowledgeBase()
        item = region()
        feature = knowledge.extractor.extract(item.crop, item.mask)
        first = knowledge.group_unknown(feature, item.crop, 1)
        second = knowledge.group_unknown(feature, item.crop, 2)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.count, 2)

    def test_25_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            knowledge = EntityKnowledgeBase(Path(directory))
            item = region()
            knowledge.add_example(item.crop, item.mask, EntityClass.NEUTRAL_NPC)
            restored = EntityKnowledgeBase(Path(directory))
            self.assertEqual(restored.examples[0].category, EntityClass.NEUTRAL_NPC)


class TrackerTests(unittest.TestCase):
    def test_26_new_track(self) -> None:
        tracker = EntityTracker()
        item = observation()
        tracker.update([item], 1)
        self.assertEqual(item.track_id, "ENT-000001")

    def test_27_stationary_same_track(self) -> None:
        tracker = EntityTracker()
        first = observation(frame=1)
        tracker.update([first], 1)
        second = observation(frame=2)
        tracker.update([second], 2)
        self.assertEqual(first.track_id, second.track_id)

    def test_28_neighbor_move_same_track(self) -> None:
        tracker = EntityTracker()
        first = observation((1, 1), frame=1)
        tracker.update([first], 1)
        second = observation((2, 1), frame=2)
        tracker.update([second], 2)
        self.assertEqual(first.track_id, second.track_id)
        self.assertTrue(second.movement_detected)

    def test_29_far_move_new_track(self) -> None:
        tracker = EntityTracker(max_cell_distance=1)
        first = observation((1, 1))
        tracker.update([first], 1)
        second = observation((5, 5), frame=2)
        tracker.update([second], 2)
        self.assertNotEqual(first.track_id, second.track_id)

    def test_30_expire_after_ttl(self) -> None:
        tracker = EntityTracker(ttl_frames=2)
        item = observation()
        tracker.update([item], 1)
        _events, expired = tracker.update([], 4)
        self.assertEqual(len(expired), 1)

    def test_31_distinct_visuals_do_not_swap(self) -> None:
        tracker = EntityTracker(min_similarity=0.95)
        first = observation((1, 1), 30)
        second = observation((2, 1), 220)
        tracker.update([first, second], 1)
        first_next = observation((2, 1), 30, frame=2)
        second_next = observation((1, 1), 220, frame=2)
        tracker.update([first_next, second_next], 2)
        self.assertEqual(first.track_id, first_next.track_id)
        self.assertEqual(second.track_id, second_next.track_id)

    def test_32_stationary_count(self) -> None:
        tracker = EntityTracker()
        first = observation()
        tracker.update([first], 1)
        second = observation(frame=2)
        tracker.update([second], 2)
        self.assertEqual(tracker.tracks[second.track_id].stationary_frame_count, 1)


class HostilityTests(unittest.TestCase):
    @staticmethod
    def _tracked(world: tuple[int, int] = (3, 0)):
        tracker = EntityTracker()
        item = observation(world)
        tracker.update([item], 1)
        return tracker, tracker.tracks[item.track_id], item

    def test_33_manhattan(self) -> None:
        self.assertEqual(HostilityAnalyzer.manhattan((3, 2), (0, 0)), 5)

    def test_34_player_moves_npc_static_no_approach(self) -> None:
        tracker, track, first = self._tracked()
        analyzer = HostilityAnalyzer()
        analyzer.update(track, first, (0, 0), False, 1)
        second = observation((3, 0), frame=2)
        tracker.update([second], 2)
        analyzer.update(track, second, (1, 0), False, 2)
        self.assertFalse(second.approaching)

    def test_35_entity_approach_scores(self) -> None:
        tracker, track, first = self._tracked()
        analyzer = HostilityAnalyzer()
        analyzer.update(track, first, (0, 0), True, 1)
        second = observation((2, 0), frame=2)
        tracker.update([second], 2)
        analyzer.update(track, second, (0, 0), True, 2)
        self.assertGreaterEqual(track.hostility_score, 6)

    def test_36_single_approach_not_confirmed(self) -> None:
        tracker, track, first = self._tracked()
        analyzer = HostilityAnalyzer()
        analyzer.update(track, first, (0, 0), True, 1)
        second = observation((2, 0), frame=2)
        tracker.update([second], 2)
        analyzer.update(track, second, (0, 0), True, 2)
        self.assertNotEqual(track.hostility_state, HostilityState.HOSTILE_CONFIRMED)

    def test_37_repeated_approach_increases(self) -> None:
        tracker, track, first = self._tracked((4, 0))
        analyzer = HostilityAnalyzer()
        analyzer.update(track, first, (0, 0), True, 1)
        scores: list[int] = []
        for frame, position in enumerate(((3, 0), (2, 0)), 2):
            item = observation(position, frame=frame)
            tracker.update([item], frame)
            analyzer.update(track, item, (0, 0), True, frame)
            scores.append(track.hostility_score)
        self.assertGreater(scores[1], scores[0])

    def test_38_attack_and_hp_confirm(self) -> None:
        _tracker, track, item = self._tracked()
        HostilityAnalyzer().update(track, item, (0, 0), True, 1, True, True)
        self.assertEqual(track.hostility_state, HostilityState.HOSTILE_CONFIRMED)

    def test_39_visual_enemy_not_immediate_confirm(self) -> None:
        tracker = EntityTracker()
        item = observation(
            (3, 0),
            category=EntityClass.ENEMY,
            confidence=0.99,
        )
        tracker.update([item], 1)
        track = tracker.tracks[item.track_id]
        HostilityAnalyzer().update(track, item, (0, 0), True, 1)
        self.assertNotEqual(track.hostility_state, HostilityState.HOSTILE_CONFIRMED)

    def test_40_decay(self) -> None:
        _tracker, track, item = self._tracked()
        analyzer = HostilityAnalyzer(decay_interval_frames=2)
        track.hostility_score = 5
        track.last_scored_frame = 1
        analyzer.update(track, item, (0, 0), True, 3)
        self.assertEqual(track.hostility_score, 4)


class DebugTests(unittest.TestCase):
    @staticmethod
    def _result(
        index: int = 1,
        with_entity: bool = False,
        settled: bool = True,
    ) -> FramePerception:
        entities: list[EntityObservation] = []
        if with_entity:
            item = observation()
            item.track_id = "ENT-000001"
            entities = [item]
        cell = CellDebugRecord(
            (0, 0),
            (0, 0),
            (0, 0, 64, 64),
            "walkable",
            0.99,
            True,
            "bg",
            0.99,
            OverlayMetrics(),
            "empty_tile",
            "matches",
        )
        return FramePerception(
            "s",
            index,
            datetime.now(timezone.utc).isoformat(),
            {},
            {"tile_size_px": 64},
            {"settled": settled},
            {"recognized": True},
            [cell],
            entities,
            [],
            processing_time_ms=1.5,
        )

    def test_41_frame_directory_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = DebugRecorder(Path(directory), "s")
            image = np.zeros((64, 64, 3), np.uint8)
            recorder.record_frame(self._result(), {"00_raw_window.png": image})
            self.assertTrue((Path(directory) / "s/frames/frame_000001").is_dir())

    def test_42_frame_json_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = DebugRecorder(Path(directory), "s")
            recorder.record_frame(
                self._result(),
                {"00_raw_window.png": np.zeros((64, 64, 3), np.uint8)},
            )
            self.assertTrue(
                (Path(directory) / "s/frames/frame_000001/frame.json").is_file()
            )

    def test_43_all_images_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = DebugRecorder(Path(directory), "s")
            recorder.record_frame(
                self._result(),
                {"00_raw_window.png": np.zeros((64, 64, 3), np.uint8)},
            )
            root = Path(directory) / "s/frames/frame_000001"
            self.assertTrue(all((root / name).is_file() for name in recorder.REQUIRED_IMAGES))

    def test_44_entity_artifacts_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = DebugRecorder(Path(directory), "s")
            recorder.record_frame(
                self._result(with_entity=True),
                {"00_raw_window.png": np.zeros((64, 64, 3), np.uint8)},
            )
            self.assertTrue(
                (
                    Path(directory)
                    / "s/frames/frame_000001/entities/ENT-000001.json"
                ).is_file()
            )

    def test_45_events_jsonl_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self._result()
            result.events = [{"event": "frame_captured"}]
            recorder = DebugRecorder(Path(directory), "s")
            recorder.record_frame(
                result,
                {"00_raw_window.png": np.zeros((64, 64, 3), np.uint8)},
            )
            json.loads((Path(directory) / "s/events.jsonl").read_text().strip())

    def test_46_summary_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = DebugRecorder(Path(directory), "s")
            recorder.record_frame(
                self._result(),
                {"00_raw_window.png": np.zeros((64, 64, 3), np.uint8)},
            )
            recorder.finalize({})
            self.assertTrue((Path(directory) / "s/summary.csv").is_file())
            self.assertEqual(
                json.loads((Path(directory) / "s/session.json").read_text())["status"],
                "finished",
            )

    def test_47_max_frames_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = DebugRecorder(Path(directory), "s", max_frames=1)
            image = np.zeros((64, 64, 3), np.uint8)
            recorder.record_frame(self._result(1), {"00_raw_window.png": image})
            self.assertRaises(
                StopIteration,
                recorder.record_frame,
                self._result(2),
                {"00_raw_window.png": image},
            )


if __name__ == "__main__":
    unittest.main()
