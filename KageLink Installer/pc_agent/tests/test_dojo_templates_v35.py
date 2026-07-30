from __future__ import annotations

import base64
import tempfile
import unittest

import cv2
import numpy as np

from pc_agent.dojo_templates_api_v35 import install_template_start_guard
from pc_agent.kage_pilot.dojo_templates import (
    DojoTemplateStore,
    UserDojoLeaderDetector,
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
        self.last_phase = phase
        self.last_error = last_error


class DojoTemplatesV35Tests(unittest.TestCase):
    @staticmethod
    def _png(width: int, height: int, marker: int) -> bytes:
        image = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.rectangle(image, (2, 2), (width - 3, height - 3), (marker, 255, 80), 2)
        cv2.circle(
            image,
            (width // 2, height // 2),
            max(2, min(width, height) // 5),
            (255, marker, 40),
            -1,
        )
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise AssertionError("test PNG encode failed")
        return bytes(encoded)

    def test_store_persists_independent_32_and_64_mode_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            first = store.save("32", self._png(32, 45, 90), original_filename="small.png")
            second = store.save("64", self._png(68, 77, 170), original_filename="large.png")

            self.assertTrue(first.configured)
            self.assertTrue(second.configured)
            self.assertEqual(first.width, 32)
            self.assertEqual(second.height, 77)
            self.assertEqual(store.public_status()["configured_modes"], ["32", "64"])
            decoded = base64.b64decode(store.image_base64("64"), validate=True)
            self.assertGreater(len(decoded), 20)

            store.remove("32")
            self.assertFalse(store.record("32").configured)
            self.assertTrue(store.record("64").configured)

    def test_detector_selects_the_matching_user_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            small = self._png(32, 45, 70)
            large = self._png(68, 77, 190)
            store.save("32", small)
            store.save("64", large)

            template = cv2.imdecode(np.frombuffer(large, dtype=np.uint8), cv2.IMREAD_COLOR)
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            frame[80 : 80 + template.shape[0], 120 : 120 + template.shape[1]] = template

            detector = UserDojoLeaderDetector(
                threshold=0.90,
                template_root=directory,
                scales=(1.0,),
            )
            match = detector.find(frame, now=1.0)
            self.assertIsNotNone(match)
            self.assertEqual(detector.last_accepted_template_mode, "64")
            self.assertEqual(detector.last_accepted_template_source, "user-64x64")
            self.assertGreaterEqual(match.score, 0.99)

    def test_start_guard_fails_closed_without_a_user_template(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DojoTemplateStore(directory)
            service = _FakeService()
            install_template_start_guard(service, store)

            self.assertFalse(service.start(object()))
            self.assertEqual(service.last_phase, DojoTrainingPhase.ERROR)
            self.assertEqual(service.last_error, "DOJO_TRAINER_TEMPLATE_REQUIRED")
            self.assertEqual(service.calls, [])

            store.save("64", self._png(68, 77, 150))
            self.assertTrue(service.start("config"))
            self.assertEqual(service.calls, ["config"])

    def test_small_templates_are_enlarged_crisply_without_distortion(self):
        self.assertEqual(preview_scale_steps(53, 69), (1, 2))
        self.assertEqual(preview_scale_steps(42, 39), (1, 3))

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
