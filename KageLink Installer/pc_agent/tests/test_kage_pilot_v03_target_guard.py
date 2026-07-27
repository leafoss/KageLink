from __future__ import annotations

import unittest

from pc_agent.kage_pilot.entity_observer import Candidate, EntityTrack
from pc_agent.kage_pilot.entity_tracker_v03 import TrackContext
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.target_guard_v03 import TargetGuardWaterAwareEntityTracker


def _track(*, state_score: float = 80.0, created: float = 0.0, seen: float = 1.0) -> EntityTrack:
    track = EntityTrack(
        track_id=1,
        bbox=(290, 95, 40, 10),
        center=(310.0, 100.0),
        created_at=created,
        last_seen=seen,
        observations=8,
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

    def test_recent_lost_track_can_only_keep_not_acquire(self):
        tracker = self._tracker()
        track = _track()
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="LOST", relative_side="RIGHT", last_visible_side="RIGHT")

        tracker._apply_target_guard(player_center=(20.0, 300.0), now=1.4)

        self.assertLess(track.enemy_score, tracker.config.target_acquire_threshold)
        self.assertGreaterEqual(track.enemy_score, tracker.config.target_keep_threshold)

    def test_old_lost_track_falls_below_keep_threshold(self):
        tracker = self._tracker()
        track = _track()
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="LOST", relative_side="RIGHT", last_visible_side="RIGHT")

        tracker._apply_target_guard(player_center=(20.0, 300.0), now=2.0)

        self.assertLess(track.enemy_score, tracker.config.target_keep_threshold)

    def test_occluded_contact_is_not_capped(self):
        tracker = self._tracker()
        track = _track(created=0.9, seen=1.0)
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="OCCLUDED", relative_side="RIGHT", last_visible_side="RIGHT")

        tracker._apply_target_guard(player_center=(300.0, 100.0), now=1.1)

        self.assertEqual(track.enemy_score, 80.0)

    def test_mature_dynamic_region_caps_noncombat_target(self):
        tracker = self._tracker()
        candidate = _scenery_candidate()
        for index in range(8):
            tracker.background.observe_and_filter(
                [candidate],
                [()],
                player_center=(20.0, 300.0),
                now=index * 0.1,
            )

        track = _track(seen=0.7)
        track.residual_velocity = (2.0, 0.0)
        track.approaching_player = False
        track.hostility_memory = 0.0
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="VISIBLE", relative_side="UP", last_visible_side="UP")

        self.assertGreaterEqual(tracker.background.region_strength_bbox(track.bbox), 0.48)
        tracker._apply_target_guard(player_center=(20.0, 300.0), now=0.8)

        self.assertLess(track.enemy_score, tracker.config.target_acquire_threshold)
        self.assertLess(track.enemy_score, tracker.config.target_keep_threshold)

    def test_background_memory_ttl_is_extended(self):
        tracker = self._tracker()
        self.assertGreaterEqual(tracker.config.background_memory_ttl, 30.0)


if __name__ == "__main__":
    unittest.main()
