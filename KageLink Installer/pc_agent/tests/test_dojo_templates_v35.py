from __future__ import annotations

import base64
import hashlib
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
    def _custom_png(width: int, height: int, marker: int) -> bytes:
        image = np.zeros((height, width, 3), dtype=np.uint8)
        image[:, :] = (marker, 80, 25)
        cv2.rectangle(image, (2, 2), (width - 3, height - 3), (255, marker, 80), 2)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise AssertionError("test PNG encode failed")
        return bytes(encoded)

    def test_first_run_materializes_factory_defaults_without_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            records = ensure_canonical_raw_templates(store)

            self.assertEqual(store.public_status()["configured_modes"], ["32", "64"])
            self.assertTrue(store.public_status()["raw_only"])
            self.assertEqual(store.public_status()["template_processing"], "denied")

            for mode in ("32", "64"):
                record = records[mode]
                self.assertTrue(record.configured)
                self.assertEqual(record.source, "default")
                self.assertEqual((record.width, record.height), RAW_TEMPLATE_PIXEL_SIZE[mode])
                self.assertEqual(record.cell_size, int(RAW_TEMPLATE_CELL_SIZE[mode]))
                self.assertEqual(record.sha256, RAW_TEMPLATE_SHA256[mode])
                self.assertEqual(record.path.read_bytes(), RAW_TEMPLATE_BYTES[mode])
                self.assertEqual(
                    base64.b64decode(store.image_base64(mode), validate=True),
                    RAW_TEMPLATE_BYTES[mode],
                )

    def test_store_accepts_arbitrary_valid_png_and_preserves_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            raw = self._custom_png(72, 73, 90)
            record = store.save("64", raw, original_filename="trainer-new.png")

            self.assertTrue(record.configured)
            self.assertTrue(record.active)
            self.assertEqual(record.source, "user")
            self.assertEqual((record.width, record.height), (72, 73))
            self.assertEqual(record.cell_size, 64)
            self.assertEqual(record.sha256, hashlib.sha256(raw).hexdigest())
            self.assertEqual(record.path.read_bytes(), raw)
            self.assertEqual(base64.b64decode(store.image_base64("64")), raw)

    def test_remove_persists_and_factory_initializer_does_not_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            ensure_canonical_raw_templates(store)
            store.remove("64")
            self.assertFalse(store.record("64").configured)
            self.assertTrue(store.record("64").removed_by_user)

            reopened = DojoTemplateStore(directory)
            ensure_canonical_raw_templates(reopened)
            record = reopened.record("64")
            self.assertFalse(record.configured)
            self.assertTrue(record.removed_by_user)
            self.assertFalse(reopened.template_path("64").exists())

    def test_restore_default_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            ensure_canonical_raw_templates(store)
            store.remove("32")
            restored = store.restore_default("32")
            self.assertTrue(restored.configured)
            self.assertEqual(restored.source, "default")
            self.assertEqual(restored.path.read_bytes(), RAW_TEMPLATE_BYTES["32"])

    def test_detector_uses_custom_native_dimensions_without_scaling(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            raw = self._custom_png(72, 73, 123)
            store.save("64", raw, original_filename="trainer-72x73.png")
            store.remove("32")
            detector = UserDojoLeaderDetector(
                threshold=0.99,
                template_root=directory,
                scales=(1.0,),
            )
            template = detector._raw_templates[0]
            frame = np.zeros((260, 420, 3), dtype=np.uint8)
            x, y = 171, 93
            frame[y : y + template.height, x : x + template.width] = template.pixels[:, :, :3]

            with patch.object(cv2, "resize", side_effect=AssertionError("resize denied")), patch.object(
                cv2,
                "cvtColor",
                side_effect=AssertionError("color conversion denied"),
            ):
                match = detector.find(frame, arena_rect=(0, 0, 40, 40), now=1.0)

            self.assertIsNotNone(match)
            self.assertEqual(match.bbox, (x, y, 72, 73))
            self.assertEqual(match.scale, 1.0)
            self.assertEqual(detector.last_accepted_template_mode, "64")
            self.assertEqual(detector.effective_tile_size, 64.0)
            self.assertGreaterEqual(match.score, 0.999)

    def test_start_guard_allows_any_active_template(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            store.save("64", self._custom_png(72, 73, 77))
            service = _FakeService()
            install_template_start_guard(service, store)

            self.assertTrue(service.start("config"))
            self.assertEqual(service.calls, ["config"])
            self.assertIsNone(service.last_error)

    def test_start_guard_fails_closed_when_no_template_is_active(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            store.remove("32")
            store.remove("64")
            service = _FakeService()
            install_template_start_guard(service, store)

            self.assertFalse(service.start(object()))
            self.assertEqual(service.last_phase, DojoTrainingPhase.ERROR)
            self.assertEqual(service.last_error, "DOJO_TRAINER_RAW_TEMPLATE_REQUIRED")
            self.assertEqual(service.calls, [])

    def test_small_raw_previews_are_enlarged_crisply_without_distortion(self):
        self.assertEqual(preview_scale_steps(30, 31), (1, 4))
        self.assertEqual(preview_scale_steps(61, 64), (1, 2))
        self.assertEqual(preview_scale_steps(72, 73), (1, 1))

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
