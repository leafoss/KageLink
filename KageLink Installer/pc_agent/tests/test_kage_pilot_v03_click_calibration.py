from __future__ import annotations

import unittest

from kage_pilot_observer import _calibrate_player_from_click


class KagePilotV03ClickCalibrationTests(unittest.TestCase):
    def test_click_maps_preview_point_to_arena_coordinates(self):
        arena = (40, 20, 920, 460)
        calibrated = _calibrate_player_from_click(489, 231, arena)
        self.assertIsNotNone(calibrated)
        player_x, player_y = calibrated or (0.0, 0.0)
        self.assertAlmostEqual(player_x, 0.5102, delta=0.002)
        self.assertAlmostEqual(player_y, 0.4795, delta=0.002)

    def test_click_outside_arena_is_ignored(self):
        arena = (40, 20, 920, 460)
        self.assertIsNone(_calibrate_player_from_click(1000, 200, arena))


if __name__ == "__main__":
    unittest.main()
