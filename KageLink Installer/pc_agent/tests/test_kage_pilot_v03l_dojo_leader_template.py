from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from pc_agent.kage_pilot import post_combat_v03c
from pc_agent.kage_pilot.dojo_leader_v03l import (
    ClearDojoLeaderDetector,
    compact_bundled_clear_template,
    decode_bundled_clear_template,
    install_clear_dojo_leader_detector,
)


class KagePilotV03LDojoLeaderTemplateTests(unittest.TestCase):
    def test_bundled_clear_source_decodes_and_builds_runtime_size(self):
        clear = decode_bundled_clear_template()
        compact = compact_bundled_clear_template(clear)

        self.assertEqual(clear.shape[:2], (77, 68))
        self.assertEqual(compact.shape[:2], (45, 32))
        self.assertGreater(int(np.ptp(compact)), 0)

    def test_detector_matches_bundled_clear_runtime_template(self):
        compact = compact_bundled_clear_template()
        frame = np.zeros((180, 260, 3), dtype=np.uint8)
        frame[70:115, 120:152] = compact

        detector = ClearDojoLeaderDetector(
            threshold=0.88,
            scales=(1.0,),
        )
        match = detector.find(frame, now=1.0)

        self.assertIsNotNone(match)
        self.assertEqual(match.bbox, (120, 70, 32, 45))
        self.assertEqual(detector.last_raw_template_source, "bundled-clear-32x45")
        self.assertGreaterEqual(match.score, 0.99)

    def test_explicit_local_calibration_remains_authoritative_when_it_scores_best(self):
        rng = np.random.default_rng(20260729)
        local = rng.integers(0, 256, size=(38, 26, 3), dtype=np.uint8)
        cv2.rectangle(local, (3, 4), (22, 34), (20, 240, 80), 2)

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dojo_leader_template.png"
            self.assertTrue(cv2.imwrite(str(path), local))
            frame = np.zeros((180, 260, 3), dtype=np.uint8)
            frame[60:98, 90:116] = local

            detector = ClearDojoLeaderDetector(
                threshold=0.88,
                template_path=path,
                scales=(1.0,),
            )
            match = detector.find(frame, now=1.0)

        self.assertIsNotNone(match)
        self.assertEqual(match.bbox, (90, 60, 26, 38))
        self.assertEqual(detector.last_raw_template_source, "local")
        self.assertGreaterEqual(match.score, 0.99)

    def test_install_replaces_only_the_persistent_detector_factory(self):
        original = post_combat_v03c.PersistentDojoLeaderDetector
        try:
            install_clear_dojo_leader_detector()
            self.assertIs(
                post_combat_v03c.PersistentDojoLeaderDetector,
                ClearDojoLeaderDetector,
            )
        finally:
            post_combat_v03c.PersistentDojoLeaderDetector = original


if __name__ == "__main__":
    unittest.main()
