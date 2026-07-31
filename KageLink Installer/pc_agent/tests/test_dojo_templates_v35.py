from __future__ import annotations

import base64
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from pc_agent.dojo_templates_api_v35 import install_template_start_guard
from pc_agent.kage_pilot.dojo_templates import (
    RAW_TEMPLATE_BYTES,
    RAW_TEMPLATE_CELL_SIZE,
    RAW_TEMPLATE_PIXEL_SIZE,
    RAW_TEMPLATE_SHA256,
    DojoTemplateStore,
    UserDojoLeaderDetector,
    ensure_canonical_raw_templates,
)
from pc_agent.kage_pilot.dojo_training import DojoTrainingPhase
from unified_dojo_templates_ui_v35 import (
    CANONICAL_SIDEBAR_ORDER,
    preview_scale_steps,
)


class _FakeService:
    def __init__(self) -> None:
        self.calls = []
        self.last_phase = None
        self.last_error = None

    def start(self, config):
        self.calls.append(config)
        return True

    def _set_phase(self, phase, *, running, last_error):
        del running
        self.last_phase = phase
        self.last_error = last_error


class DojoTemplatesV35Tests(unittest.TestCase):
    @staticmethod
    def _noncanonical_png(width: int, height: int, marker: int) -> bytes:
        image = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.rectangle(image, (2, 2), (width - 3, height - 3), (marker, 255, 80), 2)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise AssertionError("test PNG encode failed")
        return bytes(encoded)

    def test_store_materializes_the_two_exact_raw_references(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            records = ensure_canonical_raw_templates(store)

            self.assertEqual(store.public_status()["configured_modes"], ["32", "64"])
            self.assertTrue(store.public_status()["raw_only"])
            self.assertEqual(store.public_status()["template_processing"], "denied")

            for mode in ("32", "64"):
                record = records[mode]
                self.assertTrue(record.configured)
                self.assertEqual((record.width, record.height), RAW_TEMPLATE_PIXEL_SIZE[mode])
                self.assertEqual(record.cell_size, int(RAW_TEMPLATE_CELL_SIZE[mode]))
                self.assertEqual(record.sha256, RAW_TEMPLATE_SHA256[mode])
                self.assertEqual(record.path.read_bytes(), RAW_TEMPLATE_BYTES[mode])
                decoded = base64.b64decode(store.image_base64(mode), validate=True)
                self.assertEqual(decoded, RAW_TEMPLATE_BYTES[mode])

    def test_store_rejects_any_noncanonical_template_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            with self.assertRaisesRegex(ValueError, "DOJO_RAW_TEMPLATE_HASH_INVALID"):
                store.save("32", self._noncanonical_png(32, 32, 90))
            self.assertFalse(store.record("32").configured)

    def test_detector_selects_the_matching_raw_cell_mode_without_scaling(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            ensure_canonical_raw_templates(store)
            detector = UserDojoLeaderDetector(
                threshold=0.99,
                template_root=directory,
                scales=(1.0,),
            )
            template = next(item for item in detector._raw_templates if item.mode == "64")
            frame = np.zeros((240, 360, 3), dtype=np.uint8)
            x, y = 171, 93
            frame[y : y + template.height, x : x + template.width] = template.pixels[:, :, :3]

            match = detector.find(frame, arena_rect=(0, 0, 40, 40), now=1.0)

            self.assertIsNotNone(match)
            self.assertEqual(match.bbox, (x, y, 61, 64))
            self.assertEqual(match.scale, 1.0)
            self.assertEqual(detector.last_accepted_template_mode, "64")
            self.assertTrue(detector.last_accepted_template_source.startswith("raw-64-"))
            self.assertEqual(detector.effective_tile_size, 64.0)
            self.assertGreaterEqual(match.score, 0.999)

    def test_start_guard_materializes_raw_references_and_allows_start(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            service = _FakeService()
            install_template_start_guard(service, store)

            self.assertTrue(service.start("config"))
            self.assertEqual(service.calls, ["config"])
            self.assertEqual(store.template_path("32").read_bytes(), RAW_TEMPLATE_BYTES["32"])
            self.assertEqual(store.template_path("64").read_bytes(), RAW_TEMPLATE_BYTES["64"])
            self.assertIsNone(service.last_error)

    def test_start_guard_fails_closed_when_raw_reference_validation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            service = _FakeService()
            install_template_start_guard(service, store)

            with patch(
                "pc_agent.dojo_templates_api_v35.ensure_canonical_raw_templates",
                side_effect=RuntimeError("hash verification failed"),
            ):
                self.assertFalse(service.start(object()))

            self.assertEqual(service.last_phase, DojoTrainingPhase.ERROR)
            self.assertIn("DOJO_RAW_TEMPLATE_REQUIRED", service.last_error)
            self.assertEqual(service.calls, [])

    def test_small_raw_previews_are_enlarged_crisply_without_distortion(self):
        self.assertEqual(preview_scale_steps(30, 31), (1, 4))
        self.assertEqual(preview_scale_steps(61, 64), (1, 2))

    def test_large_preview_is_reduced_before_display(self):
        self.assertEqual(preview_scale_steps(420, 300), (3, 1))

    def test_settings_is_the_canonical_last_sidebar_item(self):
        self.assertEqual(CANONICAL_SIDEBAR_ORDER[-1], "settings")
        self.assertLess(
            CANONICAL_SIDEBAR_ORDER.index("dojo"),
            CANONICAL_SIDEBAR_ORDER.index("settings"),
        )


if __name__ == "__main__":
    unittest.main()
