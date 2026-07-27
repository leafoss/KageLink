from __future__ import annotations

import unittest

from pc_agent.kage_pilot.entity_observer import Candidate, EntityTrack
from pc_agent.kage_pilot.entity_tracker_v03 import TrackContext
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.target_guard_v03 import TargetGuardWaterAwareEntityTracker


def _track(
    *,
    state_score: float = 80.0,
    created: float = 0.0,
    seen: float = 1.0,
    center: tuple[float, float] = (310.0, 100.0),
    observations: int = 8,
) -> EntityTrack:
    track = EntityTrack(
        track_id=1,
        bbox=(round(center[0] - 20), round(center[1] - 5), 40, 10),
        center=center,
        created_at=created,
        last_seen=seen,
        observations=observations,
        motion_energy=0.3,
        edge_density=0.2,
        shape_score=0.5,
    )
    track.enemy_score = state_score
    return track


def _scenery_candidate() -> Candidate:
    return Candidate(
        bbox=(290, 95, 40, 10),
        center=(310.0, 100.0),
        contour_area=260.0,
        motion_energy=0.35,
        edge_density=0.18,
        shape_score=0.45,
    )


class KagePilotV03TargetGuardTests(unittest.TestCase):
    def _tracker(self) -> TargetGuardWaterAwareEntityTracker:
        config = V03ObserverConfig(
            target_acquire_threshold=55,
            target_keep_threshold=38,
            background_min_dense_hits=4,
            background_min_age=0.3,
            background_player_guard=60,
        ).normalized()
        return TargetGuardWaterAwareEntityTracker(config)

    def test_lost_track_is_never_active_target(self):
        tracker = self._tracker()
        track = _track()
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="LOST", relative_side="RIGHT", last_visible_side="RIGHT")

        tracker._apply_target_guard(player_center=(20.0, 300.0), now=1.4)

        self.assertLess(track.enemy_score, tracker.config.target_keep_threshold)
        self.assertFalse(
            tracker.target_eligible(1, player_center=(20.0, 300.0), now=1.4, for_keep=True)
        )

    def test_occluded_contact_remains_target_eligible(self):
        tracker = self._tracker()
        track = _track(created=0.9, seen=1.0, center=(110.0, 100.0))
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="OCCLUDED", relative_side="RIGHT", last_visible_side="RIGHT")

        tracker._apply_target_guard(player_center=(100.0, 100.0), now=1.1)

        self.assertEqual(track.enemy_score, 80.0)
        self.assertTrue(
            tracker.target_eligible(1, player_center=(100.0, 100.0), now=1.1)
        )

    def test_near_persistent_visible_entity_is_target_eligible(self):
        tracker = self._tracker()
        track = _track(created=0.0, seen=1.0, center=(210.0, 100.0), observations=8)
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="VISIBLE", relative_side="RIGHT", last_visible_side="RIGHT")

        self.assertTrue(
            tracker.target_eligible(1, player_center=(100.0, 100.0), now=1.0)
        )

    def test_very_young_visible_entity_cannot_acquire_target(self):
        tracker = self._tracker()
        track = _track(created=0.8, seen=1.0, center=(210.0, 100.0), observations=2)
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="VISIBLE", relative_side="RIGHT", last_visible_side="RIGHT")

        self.assertFalse(
            tracker.target_eligible(1, player_center=(100.0, 100.0), now=1.0)
        )

    def test_mature_dynamic_region_blocks_far_visible_target(self):
        tracker = self._tracker()
        candidate = _scenery_candidate()
        for index in range(10):
            tracker.background.observe_and_filter(
                [candidate],
                [()],
                player_center=(20.0, 300.0),
                now=index * 0.1,
            )

        track = _track(created=0.0, seen=0.9, center=(310.0, 100.0), observations=10)
        track.residual_velocity = (40.0, 0.0)
        track.approaching_player = True
        track.approach_speed = 30.0
        track.hostility_memory = 0.4
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="VISIBLE", relative_side="UP", last_visible_side="UP")

        self.assertGreaterEqual(
            tracker.background.region_strength_bbox(track.bbox),
            tracker.target_dynamic_region_strength,
        )
        self.assertFalse(
            tracker.target_eligible(1, player_center=(20.0, 300.0), now=1.0)
        )

    def test_background_memory_ttl_is_extended(self):
        tracker = self._tracker()
        self.assertGreaterEqual(tracker.config.background_memory_ttl, 30.0)


if __name__ == "__main__":
    unittest.main()
