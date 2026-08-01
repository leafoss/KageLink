from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from pc_agent.kage_pilot.visual_position_guard import install_visual_position_guard
from pc_agent.kage_pilot.visual_position_v351 import (
    PositionState,
    VisualMotionEstimate,
    VisualPositionTracker,
)


class VisualPositionLostGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_visual_position_guard()

    def test_continuous_motion_after_loss_does_not_resurrect_absolute_position(self):
        events: list[tuple[str, dict[str, object]]] = []
        tracker = VisualPositionTracker(
            cell_size=32.0,
            telemetry=lambda event, fields: events.append((event, fields)),
        )
        tracker.anchored = True
        tracker.state = PositionState.LOST
        tracker.x = 20.0
        tracker.y = 10.0
        tracker.confidence = 0.20
        estimate = VisualMotionEstimate(
            dx_pixels=32.0,
            dy_pixels=0.0,
            dx_cells=1.0,
            dy_cells=0.0,
            confidence=0.95,
            accepted=True,
        )
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        state = SimpleNamespace(
            arena_rect=(0, 0, 100, 100),
            player_center=(50.0, 50.0),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0, points=20),
        )

        with mock.patch.object(tracker.odometry, "observe", return_value=estimate):
            tracker.observe(frame, state, commanded_direction="right")

        self.assertEqual(tracker.state, PositionState.LOST)
        self.assertEqual((tracker.x, tracker.y), (20.0, 10.0))
        self.assertLessEqual(tracker.confidence, 0.20)
        self.assertTrue(any(event == "DOJO_POSITION_REMAINS_LOST" for event, _ in events))
        self.assertTrue(any(event == "DOJO_MOVE_OBSERVED_POSITION_LOST" for event, _ in events))

    def test_new_anchor_is_allowed_to_restore_known_origin(self):
        tracker = VisualPositionTracker(cell_size=32.0)
        tracker.anchored = True
        tracker.state = PositionState.LOST
        tracker.x = 12.0
        tracker.y = -7.0
        frame = np.random.default_rng(7).integers(0, 255, size=(120, 160, 3), dtype=np.uint8)
        state = SimpleNamespace(
            arena_rect=(0, 0, 160, 120),
            player_center=(80.0, 60.0),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0, points=20),
        )

        tracker.set_anchor(frame, state, mode="32")

        self.assertEqual(tracker.state, PositionState.KNOWN)
        self.assertEqual((tracker.x, tracker.y), (0.0, 0.0))
        self.assertEqual(tracker.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
