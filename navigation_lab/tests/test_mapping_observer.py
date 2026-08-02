from __future__ import annotations

import unittest

import cv2
import numpy as np

from navigation_lab.mapping.sparse_map import SparseTileMap
from navigation_lab.models import CellState, Point
from navigation_lab.observer.command_verifier import MovementCommandVerifier
from navigation_lab.observer.engine import MappingObserverEngine
from navigation_lab.observer.motion import MotionSample, PhaseCorrelationMotionEstimator
from navigation_lab.observer.tile_odometry import TileOdometry


class MotionEstimatorTests(unittest.TestCase):
    def test_detects_leftward_screen_translation(self) -> None:
        rng = np.random.default_rng(1234)
        previous = rng.integers(0, 255, size=(240, 320), dtype=np.uint8)
        matrix = np.float32([[1, 0, -8], [0, 1, 3]])
        current = cv2.warpAffine(previous, matrix, (320, 240), borderMode=cv2.BORDER_WRAP)
        estimator = PhaseCorrelationMotionEstimator(
            min_response=0.10,
            crop_top=0,
            crop_bottom=0,
            crop_left=0,
            crop_right=0,
        )
        sample = estimator.estimate(previous, current)
        self.assertTrue(sample.accepted, sample)
        self.assertAlmostEqual(sample.screen_dx_px, -8.0, delta=0.5)
        self.assertAlmostEqual(sample.screen_dy_px, 3.0, delta=0.5)


class MovementCommandVerifierTests(unittest.TestCase):
    def test_right_key_accepts_leftward_following_camera_shift(self) -> None:
        verifier = MovementCommandVerifier(camera_mode="following", min_shift_px=2.0)
        self.assertTrue(verifier.begin("right", started_at=0.0))
        result = verifier.observe(MotionSample(-5.0, 0.2, 0.90, True, "screen_translation"), now=0.2)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.moved)
        self.assertEqual(result.world_delta, Point(1, 0))

    def test_no_motion_after_key_marks_attempt_blocked(self) -> None:
        verifier = MovementCommandVerifier(camera_mode="following", timeout_seconds=0.5)
        self.assertTrue(verifier.begin("down", started_at=0.0))
        result = verifier.observe(MotionSample(0.0, 0.0, 0.98, False, "below_deadzone"), now=0.6)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.blocked)
        self.assertEqual(result.world_delta, Point(0, 1))

    def test_sideways_animation_does_not_confirm_wrong_direction(self) -> None:
        verifier = MovementCommandVerifier(camera_mode="following", timeout_seconds=0.5)
        self.assertTrue(verifier.begin("up", started_at=0.0))
        self.assertIsNone(
            verifier.observe(MotionSample(8.0, 0.2, 0.90, True, "screen_translation"), now=0.2)
        )
        result = verifier.observe(MotionSample(0.0, 0.0, 0.90, False, "below_deadzone"), now=0.6)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.blocked)


class TileOdometryTests(unittest.TestCase):
    def test_accumulates_partial_motion_into_one_64px_cell(self) -> None:
        odometry = TileOdometry(tile_size_px=64, camera_mode="following")
        updates = [odometry.update(-16, 0, 0.9) for _ in range(4)]
        self.assertEqual(updates[-1].position, Point(1, 0))
        self.assertEqual(updates[-1].tile_dx, 1)
        self.assertAlmostEqual(updates[-1].residual_x_px, 0.0)

    def test_screen_motion_is_inverted_into_world_motion(self) -> None:
        odometry = TileOdometry(tile_size_px=64, camera_mode="following")
        update = odometry.update(0, 64, 0.9)
        self.assertEqual(update.position, Point(0, -1))

    def test_fixed_camera_does_not_infer_tiles_from_background(self) -> None:
        odometry = TileOdometry(tile_size_px=64, camera_mode="fixed")
        update = odometry.update(-64, 0, 0.9)
        self.assertFalse(update.accepted)
        self.assertEqual(update.position, Point(0, 0))


class SparseMapTests(unittest.TestCase):
    def test_round_trip_preserves_cells_and_position(self) -> None:
        mapping = SparseTileMap("test_region", 64)
        mapping.set_current_position(Point(2, -1))
        mapping.mark_landmark(Point(1, -1), "gate")
        restored = SparseTileMap.from_dict(mapping.to_dict())
        self.assertEqual(restored.current_position, Point(2, -1))
        self.assertEqual(restored.tile_size_px, 64)
        self.assertEqual(restored.get(Point(1, -1)).state, CellState.LANDMARK)
        self.assertIn("gate", restored.get(Point(1, -1)).labels)


class MappingObserverEngineTests(unittest.TestCase):
    def test_continuous_compatibility_accumulates_four_shifts(self) -> None:
        rng = np.random.default_rng(9876)
        base = rng.integers(0, 255, size=(240, 320), dtype=np.uint8)
        engine = MappingObserverEngine(
            "calibration",
            tile_size_px=64,
            map_radius=4,
            min_motion_response=0.10,
            mapping_strategy="continuous",
        )
        engine.process_frame(base)
        for offset in (-16, -32, -48, -64):
            matrix = np.float32([[1, 0, offset], [0, 1, 0]])
            frame = cv2.warpAffine(base, matrix, (320, 240), borderMode=cv2.BORDER_WRAP)
            engine.process_frame(frame)
        self.assertEqual(engine.odometry.position, Point(1, 0))
        self.assertEqual(engine.region_map.current_position, Point(1, 0))

    def test_one_right_key_creates_exactly_one_cell_even_for_eight_pixel_shift(self) -> None:
        rng = np.random.default_rng(2222)
        base = rng.integers(0, 255, size=(240, 320), dtype=np.uint8)
        shifted = cv2.warpAffine(
            base,
            np.float32([[1, 0, -8], [0, 1, 0]]),
            (320, 240),
            borderMode=cv2.BORDER_WRAP,
        )
        engine = MappingObserverEngine(
            "calibration",
            tile_size_px=64,
            min_motion_response=0.10,
            mapping_strategy="input",
            min_command_shift_px=2.0,
        )
        engine.process_frame(base, now=-0.1)
        self.assertTrue(engine.begin_movement("right", base, started_at=0.0))
        snapshot = engine.process_frame(shifted, now=0.2)
        self.assertIsNotNone(snapshot.command_resolution)
        self.assertEqual(engine.region_map.current_position, Point(1, 0))
        self.assertEqual(engine.region_map.get(Point(1, 0)).state, CellState.VISITED)

    def test_no_visual_movement_marks_attempted_neighbor_blocked(self) -> None:
        rng = np.random.default_rng(3333)
        base = rng.integers(0, 255, size=(240, 320), dtype=np.uint8)
        engine = MappingObserverEngine(
            "calibration",
            tile_size_px=64,
            min_motion_response=0.10,
            mapping_strategy="input",
            command_timeout_seconds=0.5,
        )
        engine.process_frame(base, now=-0.1)
        self.assertTrue(engine.begin_movement("right", base, started_at=0.0))
        snapshot = engine.process_frame(base.copy(), now=0.6)
        self.assertIsNotNone(snapshot.command_resolution)
        self.assertEqual(engine.region_map.current_position, Point(0, 0))
        self.assertEqual(engine.region_map.get(Point(1, 0)).state, CellState.BLOCKED)
        self.assertIn("#", snapshot.map_ascii)

    def test_export_and_restore_preserve_mapping_position(self) -> None:
        engine = MappingObserverEngine("calibration", tile_size_px=64)
        engine.odometry.position = Point(3, -2)
        engine.region_map.set_current_position(Point(3, -2))
        payload = engine.export_state()
        restored = MappingObserverEngine("calibration", tile_size_px=64)
        restored.restore_state(payload)
        self.assertEqual(restored.odometry.position, Point(3, -2))
        self.assertEqual(restored.region_map.current_position, Point(3, -2))


if __name__ == "__main__":
    unittest.main()
