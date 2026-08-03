from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from navigation_lab.enemy_perception.background_reference import (
    SCHEMA_VERSION,
    BackgroundReferenceStore,
)
from navigation_lab.enemy_perception.entity_candidate_validator import (
    EntityCandidateValidator,
)
from navigation_lab.enemy_perception.entity_tracker import EntityTracker
from navigation_lab.enemy_perception.models import (
    EntityClass,
    EntityClassification,
    EntityObservation,
    EntityRegion,
)
from navigation_lab.enemy_perception.runtime import (
    _reset_background_references,
    _reset_unknown_entity_knowledge,
)


def tile(value: int = 40) -> np.ndarray:
    return np.full((60, 60, 3), value, np.uint8)


def region(
    world: tuple[int, int] | None = (0, -1),
    bbox: tuple[int, int, int, int] = (960, 320, 1010, 390),
    covered: list[tuple[int, int]] | None = None,
) -> EntityRegion:
    x0, y0, x1, y1 = bbox
    crop = np.full((y1 - y0, x1 - x0, 3), 140, np.uint8)
    mask = np.full(crop.shape[:2], 255, np.uint8)
    return EntityRegion(
        bbox,
        (15, 5),
        world,
        covered or [(15, 5)],
        crop,
        mask,
        crop.copy(),
    )


def observation(world: tuple[int, int], frame: int = 1) -> EntityObservation:
    item = region(world=world)
    return EntityObservation(
        item,
        [0.1, 0.2, 0.3],
        EntityClassification(EntityClass.UNKNOWN_ENTITY, 0.0, False),
        frame,
    )


class VisualBackgroundCatalogueTests(unittest.TestCase):
    def test_visual_match_does_not_require_same_world_cell(self) -> None:
        store = BackgroundReferenceStore()
        expected = store.add_reference((99, 99), "walkable", tile())
        match = store.choose(tile(), terrain_class="walkable")
        self.assertEqual(match.reference_id, expected)
        self.assertEqual(match.source_world_cell, (99, 99))

    def test_localized_sprite_is_ignored_during_background_search(self) -> None:
        store = BackgroundReferenceStore(trim_changed_fraction=0.20)
        store.add_reference((3, 4), "walkable", tile())
        current = tile()
        current[12:30, 20:40] = 220
        match = store.choose(current, terrain_class="walkable")
        self.assertGreaterEqual(match.confidence, 0.985)
        self.assertLess(match.raw_similarity, match.confidence)

    def test_semantic_class_limits_catalogue_when_known(self) -> None:
        store = BackgroundReferenceStore()
        store.add_reference((0, 0), "wall", tile(90))
        self.assertFalse(store.choose(tile(90), terrain_class="walkable").available)

    def test_dynamic_full_cell_class_can_search_all_empty_terrain(self) -> None:
        store = BackgroundReferenceStore()
        expected = store.add_reference((0, 0), "walkable", tile(65))
        self.assertEqual(store.choose(tile(65), terrain_class=None).reference_id, expected)

    def test_schema_v1_is_not_loaded_silently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.json").write_text(
                json.dumps({"schema_version": 1, "references": []}),
                encoding="utf-8",
            )
            store = BackgroundReferenceStore(root)
            self.assertTrue(store.outdated_schema_detected)
            self.assertEqual(store.outdated_schema_version, 1)
            self.assertEqual(store.references_by_class, {})
            self.assertTrue((root / "BACKGROUND_SCHEMA_OUTDATED.txt").is_file())

    def test_new_schema_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = BackgroundReferenceStore(root)
            store.add_reference((1, 2), "walkable", tile())
            payload = json.loads((root / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
            self.assertEqual(
                payload["matching_semantics"],
                "semantic_class_plus_visual_cluster",
            )
            self.assertEqual(len(payload["clusters"]), 1)


class CandidateScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = EntityCandidateValidator(
            tile_size_px=64,
            interest_radius_cells=4,
            max_covered_cells=9,
            max_width_cells=3,
            max_height_cells=3,
            max_aspect_ratio=4.0,
        )

    def test_d1_regression_is_accepted(self) -> None:
        result = self.validator.validate(region((0, -1)), (0, 0), 777)
        self.assertTrue(result.valid)
        self.assertEqual(result.distance_to_player, 1)

    def test_d4_is_accepted(self) -> None:
        self.assertTrue(
            self.validator.validate(region((4, 0)), (0, 0), 777).valid
        )

    def test_d5_anchor_is_rejected(self) -> None:
        result = self.validator.validate(region((5, 0)), (0, 0), 777)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "outside_interest_radius")

    def test_hud_intersection_is_rejected(self) -> None:
        result = self.validator.validate(
            region((0, -1), bbox=(960, 740, 1010, 790)),
            (0, 0),
            777,
        )
        self.assertEqual(result.reason, "touches_hud")

    def test_giant_component_is_rejected(self) -> None:
        result = self.validator.validate(
            region(
                (0, -1),
                bbox=(448, 149, 1280, 700),
                covered=[(x, y) for x in range(7) for y in range(5)],
            ),
            (0, 0),
            777,
        )
        self.assertFalse(result.valid)
        self.assertIn(
            result.reason,
            {"too_many_covered_cells", "bounding_box_too_wide", "bounding_box_too_tall"},
        )

    def test_extreme_aspect_ratio_is_rejected(self) -> None:
        result = self.validator.validate(
            region((0, -1), bbox=(900, 300, 1080, 320)),
            (0, 0),
            777,
        )
        self.assertEqual(result.reason, "aspect_ratio_too_extreme")


class TrackerScopeTests(unittest.TestCase):
    def test_d1_receives_track_id(self) -> None:
        tracker = EntityTracker(interest_radius_cells=4)
        item = observation((0, -1))
        item.distance_to_player = 1
        tracker.update([item], 1, player_world=(0, 0))
        self.assertIsNotNone(item.track_id)
        self.assertEqual(len(tracker.tracks), 1)

    def test_d5_never_receives_track_id(self) -> None:
        tracker = EntityTracker(interest_radius_cells=4)
        item = observation((5, 0))
        item.distance_to_player = 5
        events, _ = tracker.update([item], 1, player_world=(0, 0))
        self.assertIsNone(item.track_id)
        self.assertEqual(tracker.tracks, {})
        self.assertTrue(any(event["event"] == "track_skipped_outside_radius" for event in events))

    def test_existing_track_is_removed_when_it_leaves_scope(self) -> None:
        tracker = EntityTracker(interest_radius_cells=4)
        first = observation((0, -1), 1)
        first.distance_to_player = 1
        tracker.update([first], 1, player_world=(0, 0))
        track = next(iter(tracker.tracks.values()))
        track.current_world_cell = (6, 0)
        events, expired = tracker.update([], 2, player_world=(0, 0))
        self.assertEqual(tracker.tracks, {})
        self.assertEqual(len(expired), 1)
        self.assertTrue(any(event["event"] == "entity_out_of_scope" for event in events))


class SafeResetTests(unittest.TestCase):
    def test_background_reset_only_removes_background_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backgrounds = root / "backgrounds"
            tile_knowledge = root / "tile_knowledge.json"
            backgrounds.mkdir()
            (backgrounds / "index.json").write_text("{}", encoding="utf-8")
            tile_knowledge.write_text("preserve", encoding="utf-8")
            _reset_background_references(backgrounds)
            self.assertFalse(backgrounds.exists())
            self.assertEqual(tile_knowledge.read_text(encoding="utf-8"), "preserve")

    def test_unknown_reset_preserves_taught_examples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "unknown").mkdir(parents=True)
            (root / "unknown" / "u.png").write_bytes(b"x")
            payload = {
                "schema_version": 1,
                "examples": [{"id": "known"}],
                "unknown_groups": [{"id": "unknown"}],
            }
            (root / "index.json").write_text(json.dumps(payload), encoding="utf-8")
            _reset_unknown_entity_knowledge(root)
            restored = json.loads((root / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(restored["examples"], [{"id": "known"}])
            self.assertEqual(restored["unknown_groups"], [])
            self.assertFalse((root / "unknown").exists())


if __name__ == "__main__":
    unittest.main()
