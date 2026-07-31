from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from pc_agent.kage_pilot.dojo_raw_trainer_v351 import (
    RAW_TEMPLATE_BYTES,
    RawDojoLeaderDetector,
)
from pc_agent.kage_pilot.dojo_resolution_bridge_v351 import (
    AUTO_TEMPLATE_SCALES,
    DojoGeometry,
    ResolutionIndependentDojoLeaderDetector,
    apply_tracker_geometry,
    arena_rect_for_content,
    content_crop,
    content_rect_for_frame,
    effective_tile_size_for,
    geometry_cli_args,
    normalized_content_point,
    read_dojo_geometry,
    reset_dojo_geometry,
)
from pc_agent.kage_pilot.dojo_templates import DojoTemplateStore


class DojoResolutionBridgeV351Tests(unittest.TestCase):
    @staticmethod
    def _letterboxed_frame(
        *,
        content_width: int = 720,
        content_height: int = 540,
        output_width: int = 960,
        output_height: int = 540,
    ) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        frame = np.zeros((output_height, output_width, 3), dtype=np.uint8)
        frame[:] = (10, 7, 5)
        left = (output_width - content_width) // 2
        top = (output_height - content_height) // 2
        rng = np.random.default_rng(351)
        content = rng.integers(
            45,
            220,
            size=(content_height, content_width, 3),
            dtype=np.uint8,
        )
        frame[top : top + content_height, left : left + content_width] = content
        return frame, (left, top, content_width, content_height)

    def test_letterbox_helpers_remain_available_for_non_trainer_consumers(self):
        frame, expected = self._letterboxed_frame(content_width=720, content_height=540)
        self.assertEqual(content_rect_for_frame(frame), expected)
        config = SimpleNamespace(
            arena_left=0.10,
            arena_top=0.20,
            arena_right=0.90,
            arena_bottom=0.80,
        )
        left, top, width, height = expected
        self.assertEqual(
            arena_rect_for_content(frame, config),
            (
                left + round(width * 0.10),
                top + round(height * 0.20),
                left + round(width * 0.90),
                top + round(height * 0.80),
            ),
        )
        crop = content_crop(frame, (0.25, 0.25, 0.50, 0.50))
        self.assertEqual(crop.shape[:2], (round(height * 0.50), round(width * 0.50)))

    def test_raw_click_coordinates_use_the_original_client_frame(self):
        frame = np.zeros((600, 1000, 3), dtype=np.uint8)
        normalized = normalized_content_point(frame, (250.0, 450.0))
        self.assertAlmostEqual(normalized[0], 250.0 / 999.0, places=6)
        self.assertAlmostEqual(normalized[1], 450.0 / 599.0, places=6)

    def test_resolution_detector_is_exact_raw_and_has_no_scale_range(self):
        self.assertIs(ResolutionIndependentDojoLeaderDetector, RawDojoLeaderDetector)
        self.assertEqual(AUTO_TEMPLATE_SCALES, (1.0,))

    def test_raw_32_match_records_scale_one_and_cell_32(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"LOCALAPPDATA": directory},
        ):
            reset_dojo_geometry()
            store = DojoTemplateStore(Path(directory) / "templates")
            store.save("32", RAW_TEMPLATE_BYTES["32"], original_filename="raw32.png")
            store.save("64", RAW_TEMPLATE_BYTES["64"], original_filename="raw64.png")
            detector = ResolutionIndependentDojoLeaderDetector(
                threshold=0.99,
                template_root=store.root,
            )
            template = next(item for item in detector._raw_templates if item.mode == "32")
            frame = np.full((320, 500, 3), 11, dtype=np.uint8)
            x, y = 201, 137
            frame[y : y + template.height, x : x + template.width] = template.pixels[:, :, :3]
            match = detector.find(frame, arena_rect=(0, 0, 40, 40), now=1.0)
            self.assertIsNotNone(match)
            self.assertEqual(match.bbox, (x, y, 30, 31))
            self.assertEqual(match.scale, 1.0)
            self.assertEqual(detector.last_accepted_template_mode, "32")
            self.assertEqual(detector.effective_tile_size, 32.0)
            geometry = read_dojo_geometry()
            self.assertIsNotNone(geometry)
            self.assertEqual(geometry.template_scale, 1.0)
            self.assertEqual(geometry.effective_tile_size, 32.0)

    def test_non_raw_intermediate_scale_is_rejected(self):
        self.assertEqual(effective_tile_size_for("32", 1.0), 32.0)
        self.assertEqual(effective_tile_size_for("64", 1.0), 64.0)
        with self.assertRaisesRegex(ValueError, "DOJO_RAW_TEMPLATE_SCALE_DENIED"):
            effective_tile_size_for("64", 0.50)

    def test_effective_geometry_is_passed_to_isolated_round(self):
        geometry = DojoGeometry(
            version=2,
            saved_at=1.0,
            template_mode="64",
            template_scale=1.0,
            effective_tile_size=64.0,
            source_width=1280,
            source_height=720,
            canonical_width=960,
            canonical_height=540,
            content_left=0,
            content_top=0,
            content_width=1280,
            content_height=720,
        )
        args = geometry_cli_args(geometry)
        self.assertEqual(args[args.index("--grid-size") + 1], "64.0000")
        self.assertEqual(args[args.index("--player-box-width") + 1], "36.0000")
        self.assertEqual(args[args.index("--player-box-height") + 1], "76.0000")

    def test_visual_tracker_accepts_only_real_32_or_64_cell_modes(self):
        reset_calls = []
        odometry = SimpleNamespace(
            cell_size=32.0,
            player_patch_width=22,
            player_patch_height=38,
            reset=lambda: reset_calls.append(True),
        )
        tracker = SimpleNamespace(cell_size=32.0, odometry=odometry)
        applied = apply_tracker_geometry(tracker, 64.0)
        self.assertEqual(applied, 64.0)
        self.assertEqual(tracker.cell_size, 64.0)
        self.assertEqual(odometry.cell_size, 64.0)
        self.assertEqual(odometry.player_patch_width, 44)
        self.assertEqual(odometry.player_patch_height, 76)
        self.assertEqual(reset_calls, [True])
        with self.assertRaisesRegex(ValueError, "DOJO_RAW_CELL_MODE_INVALID"):
            apply_tracker_geometry(tracker, 16.0)


if __name__ == "__main__":
    unittest.main()
