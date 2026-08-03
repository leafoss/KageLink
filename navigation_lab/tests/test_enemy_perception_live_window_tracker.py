from __future__ import annotations

import unittest

import numpy as np

from navigation_lab.enemy_perception.entity_tracker import EntityTracker
from navigation_lab.enemy_perception.models import (
    EntityClass,
    EntityClassification,
    EntityObservation,
    EntityRegion,
)
from navigation_lab.enemy_perception.perception_window import EnemyPerceptionWindow


def observation(
    bbox: tuple[int, int, int, int],
    world: tuple[int, int],
    frame_index: int,
) -> EntityObservation:
    x0, y0, x1, y1 = bbox
    crop = np.full((max(1, y1 - y0), max(1, x1 - x0), 3), 120, np.uint8)
    mask = np.full(crop.shape[:2], 255, np.uint8)
    region = EntityRegion(
        bounding_box_px=bbox,
        anchor_screen_cell=(15 + world[0], 6 + world[1]),
        anchor_world_cell=world,
        covered_cells=[(15 + world[0], 6 + world[1])],
        crop=crop,
        mask=mask,
        difference=crop.copy(),
    )
    return EntityObservation(
        region=region,
        feature=[0.2] * 16,
        classification=EntityClassification(
            EntityClass.UNKNOWN_ENTITY,
            0.0,
            False,
        ),
        frame_index=frame_index,
        distance_to_player=abs(world[0]) + abs(world[1]),
        candidate_sources=["background_residual"],
    )


class LiveWindowTests(unittest.TestCase):
    def test_default_view_combines_decisions_and_tracks(self) -> None:
        self.assertEqual(
            EnemyPerceptionWindow.VIEW_OPTIONS[0][0],
            EnemyPerceptionWindow.LIVE_VIEW_KEY,
        )


class TrackerShapeContinuityTests(unittest.TestCase):
    def test_humanoid_track_does_not_inherit_tiny_artifact(self) -> None:
        tracker = EntityTracker(
            ttl_frames=10,
            min_similarity=0.0,
            max_cell_distance=2,
            interest_radius_cells=4,
        )
        humanoid = observation((1044, 405, 1074, 468), (1, 0), 1)
        tracker.update([humanoid], 1, player_world=(0, 0))
        humanoid_track = humanoid.track_id
        self.assertIsNotNone(humanoid_track)

        artifact = observation((852, 449, 860, 453), (-2, 0), 2)
        tracker.tracks[humanoid_track].current_world_cell = (-1, 0)
        events, _expired = tracker.update(
            [artifact],
            2,
            player_world=(0, 0),
        )

        self.assertIsNotNone(artifact.track_id)
        self.assertNotEqual(artifact.track_id, humanoid_track)
        self.assertTrue(
            any(
                event.get("event") == "track_match_rejected_shape"
                and event.get("track_id") == humanoid_track
                for event in events
            )
        )

    def test_normal_animation_scale_change_keeps_track(self) -> None:
        tracker = EntityTracker(
            ttl_frames=10,
            min_similarity=0.0,
            interest_radius_cells=4,
        )
        first = observation((1044, 405, 1074, 468), (1, 0), 1)
        tracker.update([first], 1, player_world=(0, 0))
        second = observation((1038, 407, 1075, 466), (1, 0), 2)
        tracker.update([second], 2, player_world=(0, 0))
        self.assertEqual(second.track_id, first.track_id)


if __name__ == "__main__":
    unittest.main()
