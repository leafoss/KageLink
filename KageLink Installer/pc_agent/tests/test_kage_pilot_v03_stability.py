from __future__ import annotations

import unittest
from types import SimpleNamespace

from pc_agent.kage_pilot.entity_observer import Candidate, FlowEstimate
from pc_agent.kage_pilot.entity_tracker_v03 import MeleeAwareEntityTracker
from pc_agent.kage_pilot.observer_runtime_v03 import (
    V03ObserverConfig,
    choose_locked_target,
    player_box_rect,
)


def candidate(x: float, y: float, *, w: int = 18, h: int = 38) -> Candidate:
    return Candidate(
        bbox=(round(x - w / 2), round(y - h / 2), w, h),
        center=(x, y),
        contour_area=float(w * h * 0.62),
        motion_energy=0.35,
        edge_density=0.22,
        shape_score=0.92,
    )


class KagePilotV03StabilityTests(unittest.TestCase):
    def test_player_box_is_tight_vertical_rectangle(self):
        config = V03ObserverConfig(player_box_width=18, player_box_height=38).normalized()
        self.assertEqual(player_box_rect((100.0, 100.0), config), (91, 81, 18, 38))

    def test_new_candidate_inside_player_box_is_not_spawned(self):
        config = V03ObserverConfig(player_box_width=18, player_box_height=38).normalized()
        tracker = MeleeAwareEntityTracker(config)
        tracker.update(
            [candidate(100.0, 100.0)],
            flow=FlowEstimate(),
            player_center=(100.0, 100.0),
            now=0.0,
        )
        self.assertEqual(tracker.tracks, ())

    def test_known_enemy_may_enter_player_box_without_losing_id(self):
        config = V03ObserverConfig(
            player_box_width=18,
            player_box_height=38,
            track_match_distance=105,
            track_ttl_seconds=2.0,
        ).normalized()
        tracker = MeleeAwareEntityTracker(config)
        player = (100.0, 100.0)

        tracker.update([candidate(145.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.0)
        first_id = tracker.tracks[0].track_id
        tracker.update([candidate(106.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.3)

        self.assertEqual(len(tracker.tracks), 1)
        self.assertEqual(tracker.tracks[0].track_id, first_id)
        self.assertEqual(tracker.tracks[0].observations, 2)

    def test_velocity_prediction_reacquires_same_track_after_large_jump(self):
        config = V03ObserverConfig(
            player_box_width=18,
            player_box_height=38,
            track_match_distance=90,
            track_ttl_seconds=2.0,
        ).normalized()
        tracker = MeleeAwareEntityTracker(config)
        player = (20.0, 100.0)

        tracker.update([candidate(220.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.0)
        first_id = tracker.tracks[0].track_id
        tracker.update([candidate(180.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.2)
        tracker.update([candidate(75.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.8)

        self.assertEqual(len(tracker.tracks), 1)
        self.assertEqual(tracker.tracks[0].track_id, first_id)
        self.assertEqual(tracker.tracks[0].observations, 3)

    def test_target_hysteresis_keeps_lock_below_acquire_threshold(self):
        tracks = [
            SimpleNamespace(track_id=4, enemy_score=44.0),
            SimpleNamespace(track_id=7, enemy_score=51.0),
        ]
        locked = choose_locked_target(
            tracks,
            current_target_id=4,
            acquire_threshold=55.0,
            keep_threshold=38.0,
        )
        self.assertEqual(locked, 4)

    def test_target_hysteresis_releases_and_requires_new_acquire(self):
        tracks = [
            SimpleNamespace(track_id=4, enemy_score=31.0),
            SimpleNamespace(track_id=7, enemy_score=54.0),
        ]
        locked = choose_locked_target(
            tracks,
            current_target_id=4,
            acquire_threshold=55.0,
            keep_threshold=38.0,
        )
        self.assertIsNone(locked)

        tracks[1].enemy_score = 61.0
        locked = choose_locked_target(
            tracks,
            current_target_id=None,
            acquire_threshold=55.0,
            keep_threshold=38.0,
        )
        self.assertEqual(locked, 7)


if __name__ == "__main__":
    unittest.main()
