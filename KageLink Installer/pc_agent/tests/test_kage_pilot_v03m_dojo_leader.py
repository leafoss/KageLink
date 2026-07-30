from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from pc_agent.kage_pilot import dojo_fight_v03i
from pc_agent.kage_pilot import post_combat_v03c
from pc_agent.kage_pilot.dojo_leader_v03l import decode_bundled_clear_template
from pc_agent.kage_pilot.dojo_leader_v03m import (
    IsotropicDojoLeaderDetector,
    install_isotropic_dojo_leader_detector,
)
from pc_agent.kage_pilot.trainer_search_v03m import (
    search_trainer_until_visible_diagnostic,
)


class KagePilotV03MDojoLeaderTests(unittest.TestCase):
    @staticmethod
    def _runtime_view():
        clear = decode_bundled_clear_template()
        return cv2.resize(
            clear,
            (34, 38),
            interpolation=cv2.INTER_AREA,
        )

    def test_clear_template_is_searched_at_isotropic_runtime_scale(self):
        runtime = self._runtime_view()
        frame = np.zeros((220, 320, 3), dtype=np.uint8)
        frame[:] = (50, 55, 60)
        frame[70:108, 120:154] = runtime

        detector = IsotropicDojoLeaderDetector(
            threshold=0.88,
            scales=(1.0,),
        )
        match = detector.find(frame, now=1.0)

        self.assertIsNotNone(match)
        self.assertEqual(match.bbox, (120, 70, 34, 38))
        self.assertEqual(
            detector.last_accepted_template_source,
            "bundled-clear-isotropic-68x77",
        )
        self.assertAlmostEqual(match.scale, 0.50, places=3)
        self.assertGreaterEqual(match.score, 0.99)

    def test_clear_template_is_not_stretched_to_32x45(self):
        clear = decode_bundled_clear_template()
        isotropic = cv2.resize(
            clear,
            (34, 38),
            interpolation=cv2.INTER_AREA,
        )

        self.assertEqual(isotropic.shape[:2], (38, 34))
        self.assertNotEqual(isotropic.shape[:2], (45, 32))

    def test_full_frame_fallback_recovers_trainer_below_arena_crop(self):
        runtime = self._runtime_view()
        frame = np.zeros((220, 320, 3), dtype=np.uint8)
        frame[:] = (50, 55, 60)
        frame[165:203, 120:154] = runtime

        detector = IsotropicDojoLeaderDetector(
            threshold=0.88,
            scales=(1.0,),
        )
        match = detector.find(
            frame,
            arena_rect=(10, 10, 300, 145),
            now=1.0,
        )

        self.assertIsNotNone(match)
        self.assertEqual(match.bbox, (120, 165, 34, 38))
        self.assertEqual(detector.last_scope, "full")

    def test_exact_local_calibration_remains_first_authority(self):
        rng = np.random.default_rng(20260729)
        local = rng.integers(0, 256, size=(38, 26, 3), dtype=np.uint8)
        cv2.rectangle(local, (3, 4), (22, 34), (20, 240, 80), 2)
        runtime = self._runtime_view()

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dojo_leader_template.png"
            self.assertTrue(cv2.imwrite(str(path), local))
            frame = np.zeros((220, 320, 3), dtype=np.uint8)
            frame[:] = (50, 55, 60)
            frame[60:98, 90:116] = local
            frame[130:168, 180:214] = runtime

            detector = IsotropicDojoLeaderDetector(
                threshold=0.88,
                template_path=path,
                scales=(1.0,),
            )
            match = detector.find(frame, now=1.0)

        self.assertIsNotNone(match)
        self.assertEqual(match.bbox, (90, 60, 26, 38))
        self.assertEqual(detector.last_accepted_template_source, "local")
        self.assertGreaterEqual(match.score, 0.99)

    def test_local_and_clear_weak_matches_can_confirm_same_position(self):
        runtime = self._runtime_view()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dojo_leader_template.png"
            self.assertTrue(cv2.imwrite(str(path), runtime))
            frame = np.zeros((220, 320, 3), dtype=np.uint8)
            frame[:] = (50, 55, 60)
            frame[70:108, 120:154] = runtime
            frame[78:108, 124:140] = (70, 70, 70)

            detector = IsotropicDojoLeaderDetector(
                threshold=0.88,
                template_path=path,
                scales=(1.0,),
            )
            match = detector.find(frame, now=1.0)

        self.assertIsNotNone(match)
        self.assertEqual(
            detector.last_accepted_template_source,
            "local-clear-consensus",
        )

    def test_install_patches_post_combat_and_initial_search(self):
        original_detector = post_combat_v03c.PersistentDojoLeaderDetector
        original_search = dojo_fight_v03i.search_trainer_until_visible
        try:
            install_isotropic_dojo_leader_detector()
            self.assertIs(
                post_combat_v03c.PersistentDojoLeaderDetector,
                IsotropicDojoLeaderDetector,
            )
            self.assertIs(
                dojo_fight_v03i.search_trainer_until_visible,
                search_trainer_until_visible_diagnostic,
            )
        finally:
            post_combat_v03c.PersistentDojoLeaderDetector = original_detector
            dojo_fight_v03i.search_trainer_until_visible = original_search


if __name__ == "__main__":
    unittest.main()
