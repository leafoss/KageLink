from __future__ import annotations

import unittest

import cv2
import numpy as np

from pc_agent.kage_pilot.entity_observer import (
    Candidate,
    FlowEstimate,
    ObserverConfig,
    estimate_global_flow,
)
from pc_agent.kage_pilot.entity_tracker_v03 import MeleeAwareEntityTracker


class KagePilotEntityObserverTests(unittest.TestCase):
    def test_lucas_kanade_estimates_global_translation(self):
        config = ObserverConfig().normalized()
        previous = np.zeros((220, 360), dtype=np.uint8)
        for y in range(20, 200, 30):
            for x in range(20, 340, 35):
                cv2.circle(previous, (x, y), 3, 255, -1)
                cv2.line(previous, (x - 5, y), (x + 5, y), 160, 1)
                cv2.line(previous, (x, y - 5), (x, y + 5), 160, 1)

        dx, dy = 6.0, -4.0
        transform = np.float32([[1.0, 0.0, dx], [0.0, 1.0, dy]])
        current = cv2.warpAffine(previous, transform, (previous.shape[1], previous.shape[0]))
        flow = estimate_global_flow(previous, current, config)

        self.assertGreater(flow.points, 10)
        self.assertAlmostEqual(flow.dx, dx, delta=1.2)
        self.assertAlmostEqual(flow.dy, dy, delta=1.2)

    def test_tracker_builds_enemy_score_for_persistent_approach(self):
        config = ObserverConfig(enemy_threshold=40.0, player_exclusion_radius=18.0).normalized()
        tracker = MeleeAwareEntityTracker(config)
        player = (100.0, 100.0)
        flow = FlowEstimate()

        # The final sample lands exactly on the player's exclusion boundary.
        # A known opponent must retain its ID and observation history there;
        # the exclusion radius is only allowed to suppress brand-new tracks.
        positions = [190.0, 176.0, 160.0, 144.0, 130.0, 118.0]
        now = 0.0
        for x in positions:
            candidate = Candidate(
                bbox=(round(x - 12), 80, 24, 40),
                center=(x, 100.0),
                contour_area=650.0,
                motion_energy=0.35,
                edge_density=0.22,
                shape_score=0.95,
            )
            tracker.update([candidate], flow=flow, player_center=player, now=now)
            now += 0.30

        tracks = tracker.tracks
        self.assertEqual(len(tracks), 1)
        track = tracks[0]
        self.assertGreaterEqual(track.observations, len(positions))
        self.assertTrue(track.approaching_player)
        self.assertGreater(track.total_residual_displacement, 40.0)
        self.assertGreater(track.enemy_score, 40.0)
        self.assertGreater(track.hostility_memory, 0.0)

    def test_player_anchor_exclusion_does_not_create_false_enemy(self):
        config = ObserverConfig(player_exclusion_radius=30.0).normalized()
        tracker = MeleeAwareEntityTracker(config)
        player = (100.0, 100.0)
        candidate = Candidate(
            bbox=(88, 78, 24, 44),
            center=(100.0, 100.0),
            contour_area=700.0,
            motion_energy=0.5,
            edge_density=0.3,
            shape_score=1.0,
        )
        tracker.update([candidate], flow=FlowEstimate(), player_center=player, now=0.0)
        self.assertEqual(tracker.tracks, ())

    def test_camera_flow_does_not_count_as_real_entity_motion(self):
        config = ObserverConfig(player_exclusion_radius=10.0).normalized()
        tracker = MeleeAwareEntityTracker(config)
        player = (100.0, 100.0)
        initial = Candidate(
            bbox=(188, 82, 24, 36),
            center=(200.0, 100.0),
            contour_area=500.0,
            motion_energy=0.25,
            edge_density=0.2,
            shape_score=0.9,
        )
        tracker.update([initial], flow=FlowEstimate(), player_center=player, now=0.0)

        camera = FlowEstimate(dx=8.0, dy=-3.0, points=80)
        shifted = Candidate(
            bbox=(196, 79, 24, 36),
            center=(208.0, 97.0),
            contour_area=500.0,
            motion_energy=0.25,
            edge_density=0.2,
            shape_score=0.9,
        )
        tracker.update([shifted], flow=camera, player_center=player, now=0.2)
        track = tracker.tracks[0]
        self.assertLess(track.residual_speed, 1.0)
        self.assertFalse(track.movement_real)


if __name__ == "__main__":
    unittest.main()
