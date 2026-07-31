from __future__ import annotations

import inspect
import unittest

from pc_agent.kage_pilot.dojo_raw_trainer_v351 import RawDojoLeaderDetector
from pc_agent.kage_pilot.post_combat_v03 import DojoLeaderDetector
from pc_agent.kage_pilot.post_combat_v03b import CalibratedDojoLeaderDetector
import kage_pilot_leader_calibrate


class DojoRawPipelineAuditV351Tests(unittest.TestCase):
    def test_every_trainer_detector_name_resolves_to_raw_matcher(self):
        for factory in (DojoLeaderDetector, CalibratedDojoLeaderDetector):
            detector = factory(
                threshold=0.99,
                template_path="must-not-be-read.png",
                scales=(0.5, 1.0, 2.0),
            )
            self.assertIsInstance(detector, RawDojoLeaderDetector)
            self.assertEqual(detector.scales, (1.0,))

    def test_detector_classes_contain_no_template_treatment(self):
        forbidden = (
            "cv2.resize(",
            "cv2.cvtColor(",
            "cv2.equalizeHist(",
            "cv2.createCLAHE(",
            "cv2.threshold(",
            "cv2.adaptiveThreshold(",
            "cv2.GaussianBlur(",
            "cv2.medianBlur(",
            "cv2.normalize(",
            "cv2.erode(",
            "cv2.dilate(",
            "cv2.morphologyEx(",
            "cv2.Canny(",
            "embedded-fallback",
            "template_gray",
            "INTER_AREA",
            "INTER_CUBIC",
        )
        sources = "\n".join(
            inspect.getsource(value)
            for value in (
                RawDojoLeaderDetector,
                DojoLeaderDetector,
                CalibratedDojoLeaderDetector,
            )
        )
        for token in forbidden:
            self.assertNotIn(token, sources)

    def test_obsolete_calibration_utility_is_hard_disabled(self):
        source = inspect.getsource(kage_pilot_leader_calibrate)
        self.assertNotIn("cv2", source)
        self.assertNotIn("selectROI", source)
        self.assertNotIn("imwrite", source)
        self.assertEqual(kage_pilot_leader_calibrate.main(), 2)


if __name__ == "__main__":
    unittest.main()
