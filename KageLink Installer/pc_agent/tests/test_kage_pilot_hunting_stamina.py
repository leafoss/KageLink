from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np

from pc_agent.hunting_api import hunting_status_payload
from pc_agent.kage_pilot.hunting_recovery import StaminaHudReader
from pc_agent.kage_pilot.hunting_service import HuntingService


class StaminaHudReaderTests(unittest.TestCase):
    def setUp(self):
        self.reader = StaminaHudReader()

    def _frame_with_fill(self, width: int, bgr: tuple[int, int, int]) -> np.ndarray:
        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        x, y, rw, rh = self.reader.STAMINA_ROI
        x0 = int(round(x * frame.shape[1]))
        y0 = int(round(y * frame.shape[0]))
        height = max(4, min(int(round(rh * frame.shape[0])), 6))
        if width > 0:
            frame[y0:y0 + height, x0:x0 + width] = bgr
        return frame

    def test_reader_is_calibrated(self):
        self.assertTrue(self.reader.calibrated)

    def test_green_full_bar_reads_full(self):
        frame = self._frame_with_fill(30, (51, 153, 51))
        self.assertAlmostEqual(self.reader.read(frame) or 0.0, 1.0, places=3)

    def test_yellow_ninety_percent_bar_reads_ninety_percent(self):
        frame = self._frame_with_fill(27, (51, 153, 153))
        self.assertAlmostEqual(self.reader.read(frame) or 0.0, 0.90, places=3)

    def test_orange_half_bar_reads_half(self):
        frame = self._frame_with_fill(15, (51, 102, 153))
        self.assertAlmostEqual(self.reader.read(frame) or 0.0, 0.50, places=3)

    def test_dark_brown_empty_tail_is_not_counted_as_stamina(self):
        frame = self._frame_with_fill(30, (0, 61, 102))
        self.assertEqual(self.reader.read(frame), 0.0)

    def test_empty_frame_returns_zero(self):
        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        self.assertEqual(self.reader.read(frame), 0.0)

    def test_api_exposes_calibration_before_first_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "kage_pilot_round.py").write_text("print('stub')\n", encoding="utf-8")
            service = HuntingService(project_dir=root, python_executable="python")
            payload = hunting_status_payload(service)
        self.assertTrue(payload["stamina_calibrated"])
        self.assertTrue(payload["recovery_contract"]["stamina_visual_reader"])
        self.assertFalse(payload["recovery_contract"]["fail_closed_without_stamina_calibration"])


if __name__ == "__main__":
    unittest.main()
