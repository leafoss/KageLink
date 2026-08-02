from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from navigation_lab.observer import GridCalibration, MappingObserverEngine
from navigation_lab.storage import JsonRepository


class GridCalibrationTests(unittest.TestCase):
    def test_offsets_are_normalized_inside_square_cell(self) -> None:
        calibration = GridCalibration(tile_size_px=64, offset_x_px=70, offset_y_px=-1)
        self.assertEqual(calibration.offset_x_px, 6)
        self.assertEqual(calibration.offset_y_px, 63)

    def test_line_positions_use_one_size_for_both_axes(self) -> None:
        calibration = GridCalibration(tile_size_px=64, offset_x_px=10, offset_y_px=5)
        self.assertEqual(calibration.vertical_lines(200), (10, 74, 138))
        self.assertEqual(calibration.horizontal_lines(150), (5, 69, 133))

    def test_center_alignment_places_grid_crossing_on_frame_center(self) -> None:
        calibration = GridCalibration(tile_size_px=64)
        calibration.center_on(1920, 1037)
        self.assertEqual(calibration.offset_x_px, 0)
        self.assertEqual(calibration.offset_y_px, 6)

    def test_round_trip_preserves_visual_settings(self) -> None:
        original = GridCalibration(48, 7, 9, 3, 0.40)
        restored = GridCalibration.from_dict(original.to_dict())
        self.assertEqual(restored.tile_size_px, 48)
        self.assertEqual(restored.offset_x_px, 7)
        self.assertEqual(restored.offset_y_px, 9)
        self.assertEqual(restored.line_thickness, 3)
        self.assertAlmostEqual(restored.line_opacity, 0.40)

    def test_repository_persists_calibration_by_region(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = JsonRepository(root=Path(temporary), profile="test")
            calibration = GridCalibration(56, 4, 11, 2, 0.60)
            path = repository.save_grid_calibration("konoha/east", calibration.to_dict())
            self.assertTrue(path.is_file())
            self.assertTrue(repository.has_grid_calibration("konoha/east"))
            restored = GridCalibration.from_dict(repository.load_grid_calibration("konoha/east"))
            self.assertEqual(restored.tile_size_px, 56)
            self.assertEqual(restored.offset_y_px, 11)

    def test_mapping_engine_uses_saved_visual_grid_values(self) -> None:
        engine = MappingObserverEngine(
            "calibration",
            tile_size_px=52,
            grid_offset_x_px=3,
            grid_offset_y_px=8,
            grid_line_thickness=2,
            grid_line_opacity=0.5,
        )
        self.assertEqual(engine.region_map.tile_size_px, 52)
        self.assertEqual(engine.grid_calibration.offset_x_px, 3)
        self.assertEqual(engine.grid_calibration.offset_y_px, 8)
        self.assertEqual(engine.grid_calibration.line_thickness, 2)


if __name__ == "__main__":
    unittest.main()
