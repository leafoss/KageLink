from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

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

    @staticmethod
    def _template(width: int = 46, height: int = 58) -> np.ndarray:
        image = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.rectangle(image, (2, 2), (width - 3, height - 3), (35, 220, 85), 2)
        cv2.line(image, (5, height - 8), (width - 6, 7), (235, 60, 180), 3)
        cv2.circle(image, (width // 2, height // 2), 8, (245, 210, 30), -1)
        cv2.putText(
            image,
            "K",
            (width // 3, height * 2 // 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (20, 40, 250),
            2,
            cv2.LINE_AA,
        )
        return image

    @staticmethod
    def _png(image: np.ndarray) -> bytes:
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise AssertionError("PNG encode failed")
        return bytes(encoded)

    def test_letterbox_content_is_detected_without_stretching(self):
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

    def test_click_and_hud_coordinates_are_relative_to_real_content(self):
        frame, (left, top, width, height) = self._letterboxed_frame(
            content_width=640,
            content_height=480,
        )
        point = (left + (width - 1) * 0.25, top + (height - 1) * 0.75)
        normalized = normalized_content_point(frame, point)
        self.assertAlmostEqual(normalized[0], 0.25, places=3)
        self.assertAlmostEqual(normalized[1], 0.75, places=3)

        crop = content_crop(frame, (0.25, 0.25, 0.50, 0.50))
        self.assertEqual(crop.shape[:2], (round(height * 0.50), round(width * 0.50)))

    def test_auto_scale_detector_matches_32_mode_at_half_size(self):
        self.assertLessEqual(min(AUTO_TEMPLATE_SCALES), 0.25)
        self.assertGreaterEqual(max(AUTO_TEMPLATE_SCALES), 2.50)
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"LOCALAPPDATA": directory},
        ):
            template = self._template()
            store = DojoTemplateStore(Path(directory) / "templates")
            store.save("32", self._png(template), original_filename="trainer32.png")

            scaled = cv2.resize(
                template,
                (round(template.shape[1] * 0.50), round(template.shape[0] * 0.50)),
                interpolation=cv2.INTER_AREA,
            )
            frame = np.zeros((300, 420, 3), dtype=np.uint8)
            frame[:] = (45, 55, 65)
            y, x = 120, 190
            frame[y : y + scaled.shape[0], x : x + scaled.shape[1]] = scaled

            detector = ResolutionIndependentDojoLeaderDetector(
                threshold=0.88,
                template_root=store.root,
            )
            match = detector.find(frame, now=1.0)
            self.assertIsNotNone(match)
            self.assertEqual(detector.last_accepted_template_mode, "32")
            self.assertAlmostEqual(float(match.scale), 0.50, delta=0.06)
            self.assertAlmostEqual(float(detector.effective_tile_size), 16.0, delta=2.0)
            geometry = read_dojo_geometry()
            self.assertIsNotNone(geometry)
            self.assertAlmostEqual(geometry.effective_tile_size, 16.0, delta=2.0)

    def test_effective_geometry_is_passed_to_isolated_round(self):
        geometry = DojoGeometry(
            version=1,
            saved_at=1.0,
            template_mode="32",
            template_scale=0.50,
            effective_tile_size=16.0,
            source_width=1920,
            source_height=1080,
            canonical_width=960,
            canonical_height=540,
            content_left=0,
            content_top=0,
            content_width=960,
            content_height=540,
        )
        args = geometry_cli_args(geometry)
        self.assertEqual(args[args.index("--grid-size") + 1], "16.0000")
        self.assertEqual(args[args.index("--player-box-width") + 1], "9.0000")
        self.assertEqual(args[args.index("--player-box-height") + 1], "19.0000")
        self.assertAlmostEqual(effective_tile_size_for("64", 0.50), 32.0)

    def test_visual_tracker_patch_and_search_geometry_scale_together(self):
        reset_calls = []
        odometry = SimpleNamespace(
            cell_size=32.0,
            player_patch_width=22,
            player_patch_height=38,
            reset=lambda: reset_calls.append(True),
        )
        tracker = SimpleNamespace(cell_size=32.0, odometry=odometry)
        applied = apply_tracker_geometry(tracker, 16.0)
        self.assertEqual(applied, 16.0)
        self.assertEqual(tracker.cell_size, 16.0)
        self.assertEqual(odometry.cell_size, 16.0)
        self.assertEqual(odometry.player_patch_width, 11)
        self.assertEqual(odometry.player_patch_height, 19)
        self.assertEqual(reset_calls, [True])


if __name__ == "__main__":
    unittest.main()
