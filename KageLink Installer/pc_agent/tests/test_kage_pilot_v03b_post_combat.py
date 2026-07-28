from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import cv2
import numpy as np

from pc_agent.kage_pilot.post_combat_v03b import (
    CalibratedDojoLeaderDetector,
    CalibratedHudResourceReader,
    LeaderMatchV2,
    PostCombatRecoveryEngineV2,
)


class FakeObserver:
    tile_size = 32.0
    grid_origin = (0.0, 0.0)


class FakeLeaderDetector:
    def __init__(self, matches):
        self.matches = list(matches)
        self.index = 0

    def find(self, frame_bgr, *, arena_rect=None, flow=None, now=None):
        del frame_bgr, arena_rect, flow, now
        value = self.matches[min(self.index, len(self.matches) - 1)]
        self.index += 1
        return value


class KagePilotV03BPostCombatTests(unittest.TestCase):
    def _template(self):
        rng = np.random.default_rng(12345)
        template = rng.integers(0, 256, size=(34, 28, 3), dtype=np.uint8)
        cv2.rectangle(template, (4, 5), (22, 29), (10, 240, 80), 2)
        return template

    def test_local_live_template_is_preferred_and_matches(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "leader.png"
            template = self._template()
            self.assertTrue(cv2.imwrite(str(path), template))
            detector = CalibratedDojoLeaderDetector(
                threshold=0.95,
                template_path=path,
                scales=(1.0,),
            )
            frame = np.zeros((180, 240, 3), dtype=np.uint8)
            frame[70:104, 120:148] = template
            match = detector.find(frame, now=1.0)
            self.assertIsNotNone(match)
            self.assertEqual(detector.template_source, "local")
            self.assertEqual(match.source, "visual")
            self.assertEqual(match.bbox[:2], (120, 70))
            self.assertGreaterEqual(match.score, 0.99)

    def test_camera_flow_shifts_leader_memory_when_visual_is_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "leader.png"
            template = self._template()
            cv2.imwrite(str(path), template)
            detector = CalibratedDojoLeaderDetector(
                threshold=0.95,
                template_path=path,
                scales=(1.0,),
                memory_seconds=10.0,
            )
            frame = np.zeros((180, 240, 3), dtype=np.uint8)
            frame[70:104, 120:148] = template
            visual = detector.find(frame, now=1.0)
            self.assertIsNotNone(visual)

            blank = np.zeros_like(frame)
            memory = detector.find(
                blank,
                flow=SimpleNamespace(dx=-32.0, dy=5.0),
                now=1.1,
            )
            self.assertIsNotNone(memory)
            self.assertEqual(memory.source, "memory")
            self.assertEqual(memory.bbox[0], visual.bbox[0] - 32)
            self.assertEqual(memory.bbox[1], visual.bbox[1] + 5)

    def test_micro_full_resource_widths_report_one_hundred_percent(self):
        reader = CalibratedHudResourceReader()
        frame = np.zeros((540, 960, 3), dtype=np.uint8)

        def paint(region, width, bgr):
            x, y, _, _ = region
            x0 = round(x * 960)
            y0 = round(y * 540)
            frame[y0 + 8:y0 + 14, x0 + 4:x0 + 4 + width] = bgr

        paint(reader.HEALTH_ROI, 47, (0, 0, 220))
        paint(reader.CHAKRA_ROI, 40, (220, 80, 20))
        levels = reader.read(frame)
        self.assertEqual(levels.health, 1.0)
        self.assertEqual(levels.chakra, 1.0)

    def test_memory_can_navigate_but_cannot_start_meditation(self):
        adjacent_memory = LeaderMatchV2(0.95, (150, 120, 30, 40), (176.0, 160.0), "memory")
        adjacent_visual = LeaderMatchV2(0.96, (150, 120, 30, 40), (176.0, 160.0), "visual")
        detector = FakeLeaderDetector([
            adjacent_memory,
            adjacent_memory,
            adjacent_visual,
            adjacent_visual,
        ])
        engine = PostCombatRecoveryEngineV2(
            leader_detector=detector,
            leader_confirm_frames=2,
        )
        state = SimpleNamespace(
            arena_rect=(0, 0, 320, 320),
            player_center=(160.0, 160.0),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0),
        )
        frame = np.zeros((320, 320, 3), dtype=np.uint8)
        observer = FakeObserver()

        memory1 = engine.step(frame, state, observer, now=1.0)
        memory2 = engine.step(frame, state, observer, now=1.1)
        visual1 = engine.step(frame, state, observer, now=1.2)
        visual2 = engine.step(frame, state, observer, now=1.3)

        self.assertFalse(memory1.tap_v)
        self.assertFalse(memory2.tap_v)
        self.assertFalse(visual1.tap_v)
        self.assertTrue(visual2.tap_v)
        self.assertEqual(visual2.state, "START_MEDITATION")


if __name__ == "__main__":
    unittest.main()
