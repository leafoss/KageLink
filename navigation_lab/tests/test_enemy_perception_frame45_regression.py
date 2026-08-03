from __future__ import annotations

import unittest

import numpy as np

from navigation_lab.enemy_perception.background_reference import BackgroundReferenceStore
from navigation_lab.enemy_perception.entity_candidate_validator import EntityCandidateValidator
from navigation_lab.enemy_perception.overlay_detector import OverlayDetector
from navigation_lab.enemy_perception.models import EntityRegion


class Frame45RegressionTests(unittest.TestCase):
    def test_large_localized_foreground_preserves_empty_tile_match(self) -> None:
        background = np.full((60, 60, 3), 40, np.uint8)
        current = background.copy()
        # Approximate the frame-45 D=1 cell: about 44% of the tile changes while
        # a substantial portion of the underlying terrain remains visible.
        current[6:54, 13:46] = 150
        store = BackgroundReferenceStore()
        store.add_reference((99, 99), "walkable", background)
        match = store.choose(current, terrain_class=None)
        self.assertTrue(match.available)
        # A large foreground is USABLE rather than falsely called a perfect
        # empty-tile match. The semantic NPC path does not depend on this score.
        self.assertGreaterEqual(match.confidence, 0.88)
        self.assertLess(match.raw_similarity, match.confidence)
        overlay = OverlayDetector(
            pixel_threshold=24,
            min_changed_ratio=0.03,
            min_component_area=12,
        ).detect(current, match.image)
        self.assertTrue(overlay.metrics.overlay_detected)
        self.assertLess(overlay.metrics.changed_pixel_ratio, 0.65)

    def test_frame45_equivalent_d1_candidate_is_trackable(self) -> None:
        crop = np.full((64, 49, 3), 120, np.uint8)
        mask = np.full((64, 49), 255, np.uint8)
        region = EntityRegion(
            bounding_box_px=(967, 341, 1016, 405),
            anchor_screen_cell=(15, 5),
            anchor_world_cell=(0, -2),
            covered_cells=[(15, 5)],
            crop=crop,
            mask=mask,
            difference=crop.copy(),
        )
        result = EntityCandidateValidator(
            tile_size_px=64,
            interest_radius_cells=4,
        ).validate(region, player_world=(0, -1), playfield_cutoff_y=777)
        self.assertTrue(result.valid)
        self.assertEqual(result.distance_to_player, 1)


if __name__ == "__main__":
    unittest.main()
