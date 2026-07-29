from __future__ import annotations

import unittest

import cv2
import numpy as np

from pc_agent.kage_pilot.entity_observer import (
    Candidate,
    EntityTracker,
    FlowEstimate,
    ObserverConfig,
    direction_name,
    estimate_global_flow,
)


class KagePilotV03Tests(unittest.TestCase):
    def test_lucas_kanade_estimates_global_translation(self):
        config = ObserverConfig().normalized()
        previous = np.zeros((240, 320), dtype=np.uint8)
        for y in range(30, 220, 35):
            for x in range(30, 300, 45):
                cv2.circle(previous, (x, y), 3, 255, thickness=-1)
        transform = np.float32([[1.0, 0.0, 7.0], [0.0, 1.0, -4.0]])
        current = cv2.warpAffine(previous, transform, (320, 240))

        flow = estimate_global_flow(previous, current, config)

        self.assertGreaterEqual(flow.points, 6)
        self.assertAlmostEqual(flow.dx, 7.0, delta=1.0)
        self.assertAlmostEqual(flow.dy, -4.0, delta=1.0)

    def test_tracker_preserves_id_after_camera_motion(self):
        config = ObserverConfig(track_match_distance=90.0).normalized()
        tracker = EntityTracker(config)
        player = (160.0, 130.0)
        first = Candidate(
            bbox=(220, 90, 24, 42),
            center=(232.0, 111.0),
            contour_area=700.0,
            motion_energy=0.25,
            edge_density=0.20,
            shape_score=0.90,
        )
        tracks = tracker.update([first], flow=FlowEstimate(), player_center=player, now=1.0)
        entity_id = tracks[0].track_id

        second = Candidate(
            bbox=(228, 87, 24, 42),
            center=(240.0, 108.0),
            contour_area=700.0,
            motion_energy=0.25,
            edge_density=0.20,
            shape_score=0.90,
        )
        tracks = tracker.update(
            [second],
            flow=FlowEstimate(dx=8.0, dy=-3.0, points=20),
            player_center=player,
            now=1.1,
        )

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].track_id, entity_id)
        self.assertLess(tracks[0].residual_speed, 5.0)

    def test_enemy_score_grows_for_persistent_approaching_entity(self):
        config = ObserverConfig(track_match_distance=100.0).normalized()
        tracker = EntityTracker(config)
        player = (160.0, 120.0)

        distances = [130.0, 115.0, 95.0, 72.0, 54.0]
        scores = []
        for index, distance in enumerate(distances):
            center = (player[0] + distance, player[1])
            candidate = Candidate(
                bbox=(round(center[0] - 12), round(center[1] - 22), 24, 44),
                center=center,
                contour_area=760.0,
                motion_energy=0.30,
                edge_density=0.22,
                shape_score=0.95,
            )
            tracks = tracker.update(
                [candidate],
                flow=FlowEstimate(),
                player_center=player,
                now=2.0 + index * 0.25,
            )
            scores.append(tracks[0].enemy_score)

        target = tracks[0]
        self.assertTrue(target.approaching_player)
        self.assertGreater(target.residual_speed, 5.0)
        self.assertGreater(scores[-1], scores[0])
        self.assertGreater(target.enemy_score, 45.0)

    def test_direction_names(self):
        self.assertEqual(direction_name((20.0, 0.0)), "E")
        self.assertEqual(direction_name((-20.0, 0.0)), "W")
        self.assertEqual(direction_name((15.0, -15.0)), "NE")
        self.assertEqual(direction_name((0.0, 0.0)), "-")


if __name__ == "__main__":
    unittest.main()
