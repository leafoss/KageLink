from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from pc_agent.kage_pilot import dojo_resolution_bridge_v351 as bridge
from pc_agent.kage_pilot import dojo_resolution_runtime_fix_v351 as runtime_fix
from pc_agent.kage_pilot.dojo_templates import DojoTemplateStore


class DojoResolutionRuntimeFixV351Tests(unittest.TestCase):
    @staticmethod
    def _template(width: int, height: int, marker: str) -> np.ndarray:
        image = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.rectangle(image, (2, 2), (width - 3, height - 3), (30, 220, 80), 2)
        cv2.line(image, (4, height - 6), (width - 5, 5), (230, 70, 180), 3)
        cv2.circle(image, (width // 2, height // 2), max(3, min(width, height) // 7), (245, 210, 25), -1)
        cv2.putText(
            image,
            marker,
            (max(2, width // 3), max(12, height * 2 // 3)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
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

    def test_64_only_template_uses_bounded_half_scale_scan(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"LOCALAPPDATA": directory},
        ):
            bridge.reset_dojo_geometry()
            bridge._LAST_SOURCE_WIDTH = 1920
            bridge._LAST_SOURCE_HEIGHT = 1080
            template = self._template(54, 70, "K")
            store = DojoTemplateStore(Path(directory) / "templates")
            store.save("64", self._png(template), original_filename="trainer64.png")

            scaled = cv2.resize(
                template,
                (round(template.shape[1] * 0.50), round(template.shape[0] * 0.50)),
                interpolation=cv2.INTER_AREA,
            )
            frame = np.zeros((360, 640, 3), dtype=np.uint8)
            frame[:] = (45, 55, 65)
            y, x = 140, 260
            frame[y : y + scaled.shape[0], x : x + scaled.shape[1]] = scaled

            detector = runtime_fix.BoundedResolutionIndependentDojoLeaderDetector(
                threshold=0.88,
                template_root=store.root,
            )
            match = None
            for index in range(8):
                match = detector.find(frame, now=1.0 + index * 0.2)
                if match is not None:
                    break

            self.assertIsNotNone(match)
            self.assertEqual(detector.last_accepted_template_mode, "64")
            self.assertLessEqual(len(detector.active_scan_scales), 7)
            self.assertAlmostEqual(float(match.scale), 0.50, delta=0.07)
            self.assertAlmostEqual(float(detector.effective_tile_size), 32.0, delta=4.5)

    def test_two_modes_scan_one_mode_and_four_broad_scales_per_frame(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"LOCALAPPDATA": directory},
        ):
            bridge.reset_dojo_geometry()
            bridge._LAST_SOURCE_WIDTH = 1920
            bridge._LAST_SOURCE_HEIGHT = 1080
            store = DojoTemplateStore(Path(directory) / "templates")
            store.save("32", self._png(self._template(42, 39, "3")))
            store.save("64", self._png(self._template(54, 70, "6")))
            detector = runtime_fix.BoundedResolutionIndependentDojoLeaderDetector(
                threshold=0.88,
                template_root=store.root,
            )

            self.assertFalse(detector._assign_scales(broad=False))
            first_mode = detector.active_scan_mode
            self.assertEqual(len(detector._visual_templates), 1)
            self.assertLessEqual(len(detector._visual_templates[0][4]), 4)

            self.assertFalse(detector._assign_scales(broad=False))
            second_mode = detector.active_scan_mode
            self.assertEqual(len(detector._visual_templates), 1)
            self.assertLessEqual(len(detector._visual_templates[0][4]), 4)
            self.assertNotEqual(first_mode, second_mode)

    def test_search_grid_uses_real_arena_dimensions_and_scaled_pulses(self):
        runtime_fix.install_resolution_runtime_fix()
        from pc_agent.kage_pilot.post_combat_v03e import ObstacleAwarePostCombatRecoveryEngine

        engine = ObstacleAwarePostCombatRecoveryEngine(
            leader_detector=SimpleNamespace(last_raw_score=-1.0, last_raw_location=None),
            search_timeout_seconds=30.0,
        )
        state = SimpleNamespace(
            arena_rect=(20, 30, 660, 350),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0),
        )
        frame = np.zeros((360, 680, 3), dtype=np.uint8)

        with patch.object(
            runtime_fix,
            "_desired_geometry",
            return_value=("32", 16.0, "test-geometry"),
        ):
            engine.observe_movement_frame(frame, state, now=1.0)

        self.assertEqual(engine.search.pulses_per_cell, 2)
        self.assertEqual(engine.search.arena_width_cells, 40)
        self.assertEqual(engine.search.arena_height_cells, 20)
        self.assertEqual(engine.search.max_radius, 39)


if __name__ == "__main__":
    unittest.main()
