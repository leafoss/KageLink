from __future__ import annotations

import unittest

from pc_agent.kage_pilot.grid_geometry_v351 import (
    GridGeometry,
    InvalidGridGeometryError,
)
from pc_agent.kage_pilot.grid_target_observer_v03d import (
    TileCalibratedGridTargetObserver,
)
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig


class GridGeometryAuthorityV351Tests(unittest.TestCase):
    def test_mode_64_ignores_72x73_trainer_template_dimensions(self):
        geometry = GridGeometry.from_mode(
            "64",
            template_dimensions=(72, 73),
        )
        self.assertEqual(geometry.cell_size, 64)
        self.assertEqual(geometry.mode, "64")
        self.assertTrue(geometry.template_dimensions_ignored)

    def test_mode_32_ignores_arbitrary_template_dimensions(self):
        first = GridGeometry.from_mode("32", template_dimensions=(30, 31))
        second = GridGeometry.from_mode("32", template_dimensions=(400, 17))
        self.assertEqual(first.cell_size, 32)
        self.assertEqual(second.cell_size, 32)

    def test_bbox_or_sprite_dimensions_are_not_grid_inputs(self):
        geometry = GridGeometry.from_mode("64")
        body_bboxes = ((0, 0, 20, 70), (0, 0, 80, 30), (0, 0, 72, 73))
        for _bbox in body_bboxes:
            self.assertEqual(geometry.cell_size, 64)

    def test_mode_and_cell_size_must_match(self):
        with self.assertRaisesRegex(
            InvalidGridGeometryError,
            "DOJO_INVALID_GRID_GEOMETRY",
        ):
            GridGeometry.from_mode("64", cell_size=32)

    def test_there_is_no_third_cell_size(self):
        for invalid in (16, 48, 72, 96, 64.5):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    InvalidGridGeometryError,
                    "DOJO_INVALID_GRID_GEOMETRY",
                ):
                    GridGeometry.from_cell_size(invalid)

    def test_grid_observer_refuses_to_start_with_invalid_geometry(self):
        config = V03ObserverConfig().normalized()
        with self.assertRaisesRegex(
            InvalidGridGeometryError,
            "DOJO_INVALID_GRID_GEOMETRY",
        ):
            TileCalibratedGridTargetObserver(config, tile_size=48.0)

    def test_grid_observer_keeps_exact_raw_cell_size(self):
        config = V03ObserverConfig().normalized()
        observer_32 = TileCalibratedGridTargetObserver(config, tile_size=32.0)
        observer_64 = TileCalibratedGridTargetObserver(config, tile_size=64.0)
        self.assertEqual(observer_32.tile_size, 32.0)
        self.assertEqual(observer_64.tile_size, 64.0)
        self.assertEqual(observer_32.grid_geometry.cell_size, 32)
        self.assertEqual(observer_64.grid_geometry.cell_size, 64)


if __name__ == "__main__":
    unittest.main()
