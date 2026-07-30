from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from pc_agent.kage_pilot.dojo_vision_black_box_v351 import DojoVisionBlackBox


class VisionBlackBoxV351Tests(unittest.TestCase):
    @staticmethod
    def _metadata(index: int) -> dict[str, object]:
        return {
            "state": "MEDITATING",
            "hp": 0.894,
            "chakra": 0.35,
            "meditation_state": "MEDITATING",
            "meditation_elapsed": 100.0 + index,
            "v_cooldown_remaining": 0.0,
            "position_state": "KNOWN",
            "position_x": -0.38,
            "position_y": -0.16,
            "position_confidence": 1.0,
            "trainer_box": (500, 170, 42, 39),
            "arena_rect": (0, 0, 960, 540),
            "player_point": (480.0, 270.0),
            "last_action": "hold",
            "next_action": "hold",
            "blocked_reason": "meditation_transition_active",
        }

    def test_incident_saves_raw_annotated_frames_manifest_and_contact_sheet(self):
        with tempfile.TemporaryDirectory() as directory:
            box = DojoVisionBlackBox(
                enabled=True,
                base_dir=directory,
                sample_fps=2.0,
                buffer_seconds=10.0,
            )
            frame = np.zeros((540, 960, 3), dtype=np.uint8)
            self.assertTrue(box.record(frame, self._metadata(0), now=1.0))
            self.assertTrue(box.record(frame, self._metadata(1), now=1.5))
            self.assertTrue(box.record(frame, self._metadata(2), now=2.0))

            destination = box.save_incident(
                "meditation_timeout",
                extra={"hp": 0.894, "chakra": 0.35},
            )

            self.assertIsNotNone(destination)
            incident = Path(destination)
            self.assertTrue((incident / "latest_raw.jpg").is_file())
            self.assertTrue((incident / "latest_annotated.jpg").is_file())
            self.assertTrue((incident / "contact_sheet.jpg").is_file())
            self.assertTrue((incident / "manifest.json").is_file())
            self.assertEqual(len(list((incident / "frames").glob("frame_*.jpg"))), 3)
            manifest = json.loads((incident / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["reason"], "meditation_timeout")
            self.assertEqual(manifest["frame_count"], 3)
            self.assertEqual(manifest["extra"]["hp"], 0.894)

    def test_disabled_black_box_does_not_buffer_or_write(self):
        with tempfile.TemporaryDirectory() as directory:
            box = DojoVisionBlackBox(enabled=False, base_dir=directory)
            frame = np.zeros((540, 960, 3), dtype=np.uint8)

            self.assertFalse(box.record(frame, self._metadata(0), now=1.0))
            self.assertIsNone(box.save_incident("disabled"))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_duplicate_reason_is_saved_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            box = DojoVisionBlackBox(enabled=True, base_dir=directory, sample_fps=1.0)
            frame = np.zeros((540, 960, 3), dtype=np.uint8)
            box.record(frame, self._metadata(0), now=1.0)

            first = box.save_incident("meditation_timeout")
            second = box.save_incident("meditation_timeout")

            self.assertIsNotNone(first)
            self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()
