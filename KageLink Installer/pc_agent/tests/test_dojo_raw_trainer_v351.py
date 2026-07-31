from __future__ import annotations

import hashlib
import inspect
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from pc_agent.kage_pilot.dojo_user_templates_v351 import (
    RAW_TEMPLATE_BYTES,
    RAW_TEMPLATE_CELL_SIZE,
    RAW_TEMPLATE_PIXEL_SIZE,
    RAW_TEMPLATE_SHA256,
    DojoTemplateStore,
    UserDojoLeaderDetector,
    ensure_factory_defaults,
)


class DojoRawTrainerV351Tests(unittest.TestCase):
    @staticmethod
    def _png(width: int, height: int) -> bytes:
        image = np.zeros((height, width, 3), dtype=np.uint8)
        image[:, :] = (31, 97, 163)
        cv2.rectangle(image, (3, 3), (width - 4, height - 4), (220, 75, 12), 2)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise AssertionError("test PNG encode failed")
        return bytes(encoded)

    def test_factory_raw_assets_keep_exact_hashes_and_crop_sizes(self):
        self.assertEqual(
            RAW_TEMPLATE_SHA256["32"],
            "fbc5dcc0f0d46ac315e17fd6cb25436c01f60a460cfcf58a0a6f9204b3b21d51",
        )
        self.assertEqual(
            RAW_TEMPLATE_SHA256["64"],
            "9e0ff270e5c531f7a2784e5cc57c62084b46500e44069cdac045e6daa323004c",
        )
        self.assertEqual(RAW_TEMPLATE_PIXEL_SIZE["32"], (30, 31))
        self.assertEqual(RAW_TEMPLATE_PIXEL_SIZE["64"], (61, 64))
        self.assertEqual(RAW_TEMPLATE_CELL_SIZE["32"], 32.0)
        self.assertEqual(RAW_TEMPLATE_CELL_SIZE["64"], 64.0)

        for mode in ("32", "64"):
            raw = RAW_TEMPLATE_BYTES[mode]
            self.assertEqual(hashlib.sha256(raw).hexdigest(), RAW_TEMPLATE_SHA256[mode])
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            self.assertIsNotNone(image)
            height, width = image.shape[:2]
            self.assertEqual((width, height), RAW_TEMPLATE_PIXEL_SIZE[mode])

    def test_store_writes_exact_user_png_bytes_without_reencoding(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            raw = self._png(72, 73)
            record = store.save("64", raw, original_filename="trainer.png")
            self.assertTrue(record.configured)
            self.assertEqual(store.template_path("64").read_bytes(), raw)
            self.assertEqual(record.sha256, hashlib.sha256(raw).hexdigest())
            self.assertEqual(record.cell_size, 64)
            self.assertEqual((record.width, record.height), (72, 73))
            self.assertEqual(record.source, "user")

    def test_store_rejects_invalid_png_but_not_different_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            with self.assertRaisesRegex(ValueError, "DOJO_RAW_TEMPLATE_NOT_PNG"):
                store.save("32", b"not a png")
            custom = self._png(47, 51)
            record = store.save("32", custom)
            self.assertTrue(record.configured)
            self.assertEqual((record.width, record.height), (47, 51))

    def test_detector_finds_user_sprite_at_original_size_outside_arena_roi(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            store.save("64", self._png(72, 73))
            store.remove("32")
            detector = UserDojoLeaderDetector(threshold=0.99, template_root=store.root)
            template = detector._raw_templates[0]
            frame = np.full((480, 800, 3), 17, dtype=np.uint8)
            x, y = 613, 351
            frame[y : y + template.height, x : x + template.width] = template.pixels[:, :, :3]

            match = detector.find(frame, arena_rect=(0, 0, 120, 100), now=1.0)

            self.assertIsNotNone(match)
            self.assertEqual(match.bbox, (x, y, 72, 73))
            self.assertEqual(match.scale, 1.0)
            self.assertEqual(detector.last_accepted_template_mode, "64")
            self.assertEqual(detector.effective_tile_size, 64.0)
            self.assertEqual(detector.last_search_roi, (0, 0, 800, 480))

    def test_detector_never_calls_template_resize_or_color_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            ensure_factory_defaults(store)
            detector = UserDojoLeaderDetector(threshold=0.99, template_root=directory)
            template = next(item for item in detector._raw_templates if item.mode == "32")
            frame = np.zeros((240, 360, 3), dtype=np.uint8)
            x, y = 211, 121
            frame[y : y + template.height, x : x + template.width] = template.pixels[:, :, :3]

            with patch.object(
                cv2,
                "resize",
                side_effect=AssertionError("template resize is forbidden"),
            ), patch.object(
                cv2,
                "cvtColor",
                side_effect=AssertionError("template color conversion is forbidden"),
            ):
                match = detector.find(frame, now=1.0)

            self.assertIsNotNone(match)
            self.assertEqual(match.bbox, (x, y, 30, 31))

    def test_raw_matcher_source_contains_no_forbidden_template_processing(self):
        source = inspect.getsource(UserDojoLeaderDetector)
        forbidden = (
            "cv2.resize(",
            "cv2.cvtColor(",
            "cv2.equalizeHist(",
            "cv2.createCLAHE(",
            "cv2.threshold(",
            "cv2.adaptiveThreshold(",
            "cv2.GaussianBlur(",
            "cv2.morphologyEx(",
            "cv2.Canny(",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_cell_mode_is_not_confused_with_crop_dimensions(self):
        self.assertEqual(RAW_TEMPLATE_CELL_SIZE["32"], 32.0)
        self.assertEqual(RAW_TEMPLATE_CELL_SIZE["64"], 64.0)
        self.assertNotEqual((72, 73), (64, 64))


if __name__ == "__main__":
    unittest.main()
