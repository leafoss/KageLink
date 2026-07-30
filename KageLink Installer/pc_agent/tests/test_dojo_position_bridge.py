from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import cv2
import numpy as np

from pc_agent.kage_pilot.dojo_position_bridge import (
    restore_tracker_state,
    save_tracker_state,
    tracker_payload,
)
from pc_agent.kage_pilot.visual_position_v351 import PositionState, VisualPositionTracker


class DojoPositionBridgeTests(unittest.TestCase):
    @staticmethod
    def _frame(seed: int = 4) -> np.ndarray:
        rng = np.random.default_rng(seed)
        frame = rng.integers(20, 180, size=(220, 300, 3), dtype=np.uint8)
        cv2.rectangle(frame, (120, 80), (180, 150), (20, 230, 100), 3)
        return frame

    @staticmethod
    def _state():
        return SimpleNamespace(
            arena_rect=(0, 0, 300, 220),
            player_center=(150.0, 110.0),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0, points=30),
        )

    def test_save_and_restore_preserves_anchor_position_mode_and_keyframes(self):
        source = VisualPositionTracker(cell_size=64.0)
        frame = self._frame()
        state = self._state()
        source.set_anchor(frame, state, mode="64")
        source.x = 20.0
        source.y = 10.0
        source.confidence = 0.91
        source.state = PositionState.KNOWN
        source._create_keyframe(self._frame(8), state, quality=0.88)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "round.position.json"
            save_tracker_state(source, path)
            self.assertTrue(path.exists())

            destination = VisualPositionTracker(cell_size=32.0)
            self.assertTrue(restore_tracker_state(destination, path))
            snapshot = destination.snapshot()
            self.assertTrue(snapshot.anchored)
            self.assertEqual(snapshot.state, PositionState.KNOWN)
            self.assertAlmostEqual(snapshot.x, 20.0)
            self.assertAlmostEqual(snapshot.y, 10.0)
            self.assertAlmostEqual(snapshot.confidence, 0.91)
            self.assertEqual(destination.mode, "64")
            self.assertEqual(destination.cell_size, 64.0)
            self.assertGreaterEqual(snapshot.keyframes, 2)

    def test_delete_after_load_removes_ephemeral_bridge_file(self):
        source = VisualPositionTracker(cell_size=32.0)
        source.set_anchor(self._frame(), self._state(), mode="32")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "round.position.json"
            save_tracker_state(source, path)
            destination = VisualPositionTracker(cell_size=64.0)
            self.assertTrue(restore_tracker_state(destination, path, delete_after_load=True))
            self.assertFalse(path.exists())

    def test_corrupt_state_fails_closed_without_inventing_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.position.json"
            path.write_text("not-json", encoding="utf-8")
            tracker = VisualPositionTracker(cell_size=32.0)
            tracker.x = 99.0
            tracker.y = -44.0
            tracker.state = PositionState.KNOWN
            tracker.anchored = True

            self.assertFalse(restore_tracker_state(tracker, path))
            self.assertFalse(tracker.anchored)
            self.assertEqual(tracker.state, PositionState.LOST)
            self.assertEqual((tracker.x, tracker.y), (0.0, 0.0))

    def test_payload_is_utf8_json_safe_and_does_not_store_full_frames(self):
        tracker = VisualPositionTracker(cell_size=32.0)
        tracker.set_anchor(self._frame(), self._state(), mode="32")
        payload = tracker_payload(tracker)
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["position"]["mode"], "32")
        self.assertTrue(payload["keyframes"])
        self.assertIn("descriptor_png_base64", payload["keyframes"][0])
        self.assertNotIn("frame", payload["keyframes"][0])

    def test_canonical_loop_starts_monitor_confirms_click_and_passes_session_state(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "kage_pilot_loop.py").read_text(encoding="utf-8")
        self.assertIn("DojoAnchorMonitor", source)
        self.assertIn("monitor.confirm_click(click)", source)
        self.assertIn("monitor.stop_and_save(_SESSION_STATE_PATH)", source)
        self.assertIn('command.extend(["--position-state", str(saved)])', source)
        self.assertIn("DOJO_SESSION_MAP_RESTORED", source)
        self.assertIn("_SESSION_STATE_PATH.unlink", source)

    def test_round_adapter_keeps_state_until_updated_map_is_saved(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "kage_pilot_visual_return.py").read_text(encoding="utf-8")
        self.assertIn("_extract_position_state_argument(sys.argv)", source)
        self.assertIn("restore_tracker_state", source)
        self.assertIn("delete_after_load=False", source)
        self.assertIn("DOJO_POSITION_BRIDGE_RESTORED", source)
        self.assertIn("save_tracker_state(position, position_path)", source)
        self.assertIn("DOJO_SESSION_MAP_SAVED", source)


if __name__ == "__main__":
    unittest.main()
