from __future__ import annotations

from types import SimpleNamespace
import unittest

import cv2
import numpy as np

from pc_agent.kage_pilot.position_map_continuity import merge_nonorigin_keyframes
from pc_agent.kage_pilot.visual_position_v351 import VisualPositionTracker


class PositionMapContinuityTests(unittest.TestCase):
    @staticmethod
    def _frame(seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        frame = rng.integers(15, 220, size=(180, 260, 3), dtype=np.uint8)
        cv2.circle(frame, (100 + seed, 80), 18, (20, 240, 90), 3)
        return frame

    @staticmethod
    def _state():
        return SimpleNamespace(
            arena_rect=(0, 0, 260, 180),
            player_center=(130.0, 90.0),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0, points=24),
        )

    def test_nonorigin_keyframes_survive_exact_anchor_refresh(self):
        state = self._state()
        old = VisualPositionTracker(cell_size=32.0)
        old.set_anchor(self._frame(1), state, mode="32")
        old.x, old.y = 8.0, 3.0
        old._create_keyframe(self._frame(2), state, quality=0.92)
        preserved = tuple(old.keyframes)

        refreshed = VisualPositionTracker(cell_size=32.0)
        refreshed.set_anchor(self._frame(3), state, mode="32")
        added = merge_nonorigin_keyframes(refreshed, preserved)

        self.assertEqual(added, 1)
        self.assertEqual(sum(1 for item in refreshed.keyframes if item.origin), 1)
        locations = {(round(item.x, 2), round(item.y, 2)) for item in refreshed.keyframes}
        self.assertIn((8.0, 3.0), locations)

    def test_near_duplicate_keyframe_is_not_added_twice(self):
        state = self._state()
        source = VisualPositionTracker(cell_size=32.0)
        source.set_anchor(self._frame(4), state, mode="32")
        source.x, source.y = 4.0, 1.0
        source._create_keyframe(self._frame(5), state, quality=0.90)
        preserved = tuple(source.keyframes)

        destination = VisualPositionTracker(cell_size=32.0)
        destination.set_anchor(self._frame(6), state, mode="32")
        destination.x, destination.y = 4.1, 1.1
        destination._create_keyframe(self._frame(7), state, quality=0.91)

        self.assertEqual(merge_nonorigin_keyframes(destination, preserved), 0)

    def test_merge_respects_bounded_keyframe_capacity(self):
        state = self._state()
        source = VisualPositionTracker(cell_size=32.0, max_keyframes=12)
        source.set_anchor(self._frame(8), state, mode="32")
        for index in range(1, 10):
            source.x = float(index * 2)
            source.y = float(index % 3)
            source._create_keyframe(self._frame(8 + index), state, quality=0.5 + index * 0.03)

        destination = VisualPositionTracker(cell_size=32.0, max_keyframes=5)
        destination.set_anchor(self._frame(30), state, mode="32")
        merge_nonorigin_keyframes(destination, source.keyframes)

        self.assertLessEqual(len(destination.keyframes), 5)
        self.assertEqual(sum(1 for item in destination.keyframes if item.origin), 1)


if __name__ == "__main__":
    unittest.main()
