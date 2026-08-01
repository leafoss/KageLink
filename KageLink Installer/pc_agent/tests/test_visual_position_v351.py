from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

import cv2
import numpy as np

from pc_agent.kage_pilot.visual_position_v351 import (
    PositionState,
    VisualOdometry,
    VisualPositionTracker,
)


class _State:
    def __init__(
        self,
        *,
        width: int,
        height: int,
        player_center: tuple[float, float],
        flow_dx: float = 0.0,
        flow_dy: float = 0.0,
        points: int = 24,
    ) -> None:
        self.arena_rect = (0, 0, width, height)
        self.player_center = player_center
        self.global_flow = SimpleNamespace(dx=flow_dx, dy=flow_dy, points=points)


def _scene(width: int = 320, height: int = 240, *, player=(160, 120), seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    frame = rng.integers(15, 80, size=(height, width, 3), dtype=np.uint8)
    for y in range(20, height, 32):
        cv2.line(frame, (0, y), (width - 1, y), (110, 90, 70), 1)
    for x in range(16, width, 32):
        cv2.line(frame, (x, 0), (x, height - 1), (60, 100, 80), 1)
    px, py = int(player[0]), int(player[1])
    cv2.rectangle(frame, (px - 8, py - 17), (px + 8, py + 17), (220, 220, 235), -1)
    cv2.circle(frame, (px, py - 8), 5, (25, 25, 25), -1)
    cv2.line(frame, (px - 7, py + 4), (px + 7, py + 4), (30, 160, 210), 2)
    return frame


def _shift(frame: np.ndarray, dx: float, dy: float) -> np.ndarray:
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(frame, matrix, (frame.shape[1], frame.shape[0]), borderMode=cv2.BORDER_REFLECT)


class VisualPositionV351Tests(unittest.TestCase):
    def test_camera_motion_with_centered_player_becomes_world_motion(self):
        odometry = VisualOdometry(cell_size=32.0, minimum_confidence=0.20)
        first = _scene()
        state_first = _State(width=320, height=240, player_center=(160, 120))
        odometry.observe(first, state_first)

        second = _shift(first, -32, 0)
        state_second = _State(
            width=320,
            height=240,
            player_center=(160, 120),
            flow_dx=-32,
            flow_dy=0,
            points=30,
        )
        # In camera-follow mode the player remains at the same screen coordinate.
        with mock.patch.object(odometry, "_match_player", return_value=(0.0, 0.0, 0.95)):
            estimate = odometry.observe(second, state_second)

        self.assertTrue(estimate.accepted)
        self.assertAlmostEqual(estimate.dx_cells, 1.0, delta=0.10)
        self.assertAlmostEqual(estimate.dy_cells, 0.0, delta=0.10)

    def test_stationary_camera_uses_player_screen_displacement(self):
        odometry = VisualOdometry(cell_size=32.0, minimum_confidence=0.15)
        first = _scene(player=(130, 120))
        odometry.observe(first, _State(width=320, height=240, player_center=(130, 120)))
        second = _scene(player=(162, 120))
        estimate = odometry.observe(
            second,
            _State(width=320, height=240, player_center=(162, 120), points=0),
        )
        self.assertTrue(estimate.accepted)
        self.assertAlmostEqual(estimate.dx_cells, 1.0, delta=0.45)

    def test_anchor_external_displacement_and_blocked_command(self):
        events: list[tuple[str, dict[str, object]]] = []
        tracker = VisualPositionTracker(
            cell_size=32.0,
            telemetry=lambda event, fields: events.append((event, fields)),
        )
        frame = _scene()
        state = _State(width=320, height=240, player_center=(160, 120))
        tracker.set_anchor(frame, state, mode="64")
        self.assertEqual(tracker.snapshot().state, PositionState.KNOWN)
        self.assertEqual((tracker.x, tracker.y), (0.0, 0.0))

        moved = _shift(frame, -32, 0)
        with mock.patch.object(tracker.odometry, "_match_player", return_value=(0.0, 0.0, 0.95)):
            tracker.observe(
                moved,
                _State(width=320, height=240, player_center=(160, 120), flow_dx=-32, points=30),
            )
        self.assertGreater(tracker.x, 0.5)
        self.assertTrue(any(event == "DOJO_EXTERNAL_DISPLACEMENT" for event, _ in events))

        before = (tracker.x, tracker.y)
        tracker.note_command("up")
        with mock.patch.object(tracker.odometry, "_match_player", return_value=(0.0, 0.0, 0.95)):
            tracker.observe(
                moved,
                _State(width=320, height=240, player_center=(160, 120), flow_dx=0, points=30),
            )
        self.assertAlmostEqual(tracker.x, before[0], delta=0.2)
        self.assertAlmostEqual(tracker.y, before[1], delta=0.2)
        self.assertTrue(any(event == "DOJO_MOVE_BLOCKED" for event, _ in events))

    def test_low_confidence_discontinuity_never_invents_coordinates(self):
        tracker = VisualPositionTracker(cell_size=32.0)
        first = _scene(seed=4)
        state = _State(width=320, height=240, player_center=(160, 120))
        tracker.set_anchor(first, state)
        tracker.x = 4.0
        tracker.y = 3.0

        unrelated = _scene(seed=400)
        tracker.observe(
            unrelated,
            _State(width=320, height=240, player_center=(40, 40), flow_dx=500, flow_dy=500, points=1),
        )
        self.assertEqual(tracker.state, PositionState.LOST)
        self.assertAlmostEqual(tracker.x, 4.0)
        self.assertAlmostEqual(tracker.y, 3.0)

    def test_keyframe_relocalization_restores_known_coordinates(self):
        tracker = VisualPositionTracker(
            cell_size=32.0,
            keyframe_distance_cells=0.5,
            relocalization_threshold=0.75,
            relocalization_margin=0.01,
        )
        origin = _scene(seed=12)
        state = _State(width=320, height=240, player_center=(160, 120))
        tracker.set_anchor(origin, state, mode="32")

        tracker.x = 5.0
        tracker.y = -2.0
        second = _scene(seed=33)
        self.assertTrue(tracker._create_keyframe(second, state, quality=0.95))
        tracker.state = PositionState.LOST
        tracker.x = 99.0
        tracker.y = 99.0

        self.assertTrue(tracker.relocalize(second.copy(), state))
        self.assertEqual(tracker.state, PositionState.KNOWN)
        self.assertAlmostEqual(tracker.x, 5.0)
        self.assertAlmostEqual(tracker.y, -2.0)

    def test_ambiguous_relocalization_is_rejected(self):
        tracker = VisualPositionTracker(
            cell_size=32.0,
            relocalization_threshold=0.70,
            relocalization_margin=0.10,
        )
        frame = _scene(seed=8)
        state = _State(width=320, height=240, player_center=(160, 120))
        tracker.set_anchor(frame, state)
        tracker.x = 2.0
        tracker._create_keyframe(frame.copy(), state, quality=0.90)
        tracker.state = PositionState.LOST

        self.assertFalse(tracker.relocalize(frame.copy(), state))
        self.assertEqual(tracker.state, PositionState.LOST)

    def test_return_direction_reduces_distance_and_respects_block(self):
        tracker = VisualPositionTracker(cell_size=32.0)
        frame = _scene()
        state = _State(width=320, height=240, player_center=(160, 120))
        tracker.set_anchor(frame, state)
        tracker.x = 20.0
        tracker.y = 10.0
        tracker.state = PositionState.KNOWN

        self.assertEqual(tracker.choose_return_direction(now=1.0), "left")
        tracker.mark_blocked("left", now=1.0, ttl_seconds=10.0)
        self.assertEqual(tracker.choose_return_direction(now=2.0), "up")

    def test_32_and_64_cell_conversion(self):
        first = _scene()
        for cell_size in (32.0, 64.0):
            odometry = VisualOdometry(cell_size=cell_size, minimum_confidence=0.20)
            odometry.observe(first, _State(width=320, height=240, player_center=(160, 120)))
            shifted = _shift(first, -cell_size, 0)
            with mock.patch.object(odometry, "_match_player", return_value=(0.0, 0.0, 0.95)):
                estimate = odometry.observe(
                    shifted,
                    _State(
                        width=320,
                        height=240,
                        player_center=(160, 120),
                        flow_dx=-cell_size,
                        points=30,
                    ),
                )
            self.assertAlmostEqual(estimate.dx_cells, 1.0, delta=0.10)


if __name__ == "__main__":
    unittest.main()
