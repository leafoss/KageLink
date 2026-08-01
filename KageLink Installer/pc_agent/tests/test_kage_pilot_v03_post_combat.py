from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np

from pc_agent.kage_pilot.post_combat_v03 import (
    ChatVictoryWatcher,
    DojoLeaderDetector,
    HudResourceReader,
    LeaderMatch,
    PostCombatRecoveryEngine,
)


class FakeChatReader:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def read_current(self):
        if not self.values:
            return ""
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        return value


class FakeLeaderDetector:
    def __init__(self, matches):
        self.matches = list(matches)
        self.index = 0

    def find(self, frame_bgr, *, arena_rect=None):
        del frame_bgr, arena_rect
        if not self.matches:
            return None
        value = self.matches[min(self.index, len(self.matches) - 1)]
        self.index += 1
        return value


class FakeResourceReader:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def read(self, frame_bgr):
        del frame_bgr
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        return value


class FakeObserver:
    tile_size = 32.0
    grid_origin = (0.0, 0.0)


class KagePilotV03PostCombatTests(unittest.TestCase):
    def test_authoritative_knocked_out_phrase(self):
        self.assertTrue(ChatVictoryWatcher.is_victory_text("Jounin: Tamura, Seijun has been Knocked-Out"))
        self.assertTrue(ChatVictoryWatcher.is_victory_text("X has been knocked out"))
        self.assertFalse(ChatVictoryWatcher.is_victory_text("X was knocked down"))

    def test_watcher_ignores_old_chat_and_fires_only_on_new_line(self):
        reader = FakeChatReader([
            "Old line\nSomeone has been Knocked-Out",
            "Old line\nSomeone has been Knocked-Out\nCombat continues",
            "Old line\nSomeone has been Knocked-Out\nCombat continues\nJounin: A has been Knocked-Out",
        ])
        watcher = ChatVictoryWatcher("x", "y", reader=reader)
        watcher.prime()
        self.assertIsNone(watcher.poll())
        signal = watcher.poll()
        self.assertIsNotNone(signal)
        self.assertIn("Jounin: A", signal.text)

    def test_supplied_raw_trainer_reference_matches_without_processing(self):
        detector = DojoLeaderDetector(threshold=0.99)
        template = next(item for item in detector._raw_templates if item.mode == "64")
        frame = np.zeros((300, 400, 3), dtype=np.uint8)
        x, y = 120, 80
        frame[y:y + template.height, x:x + template.width] = template.pixels[:, :, :3]
        match = detector.find(frame)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(match.score, 0.999)
        self.assertEqual(match.bbox, (x, y, 61, 64))
        self.assertEqual(match.scale, 1.0)
        self.assertEqual(detector.last_accepted_template_mode, "64")

    def test_hud_reader_estimates_requested_thresholds_from_synthetic_bars(self):
        reader = HudResourceReader()
        frame = np.zeros((540, 960, 3), dtype=np.uint8)

        def paint(region, width, bgr):
            x, y, rw, rh = region
            del rw, rh
            x0 = round(x * 960)
            y0 = round(y * 540)
            frame[y0 + 8:y0 + 14, x0 + 4:x0 + 4 + width] = bgr

        paint(reader.HEALTH_ROI, 42, (0, 0, 220))
        paint(reader.CHAKRA_ROI, 24, (220, 80, 20))
        levels = reader.read(frame)
        self.assertGreaterEqual(levels.health, 0.90)
        self.assertGreaterEqual(levels.chakra, 0.50)

    def test_postcombat_moves_to_adjacent_then_toggles_v_once(self):
        detector = FakeLeaderDetector([
            LeaderMatch(0.95, (210, 120, 68, 73), (240.0, 160.0)),
            LeaderMatch(0.95, (210, 120, 68, 73), (240.0, 160.0)),
            LeaderMatch(0.95, (178, 120, 68, 73), (192.0, 160.0)),
            LeaderMatch(0.95, (178, 120, 68, 73), (192.0, 160.0)),
        ])
        engine = PostCombatRecoveryEngine(leader_detector=detector, leader_confirm_frames=2)
        state = SimpleNamespace(arena_rect=(0, 0, 320, 320), player_center=(160.0, 160.0))
        frame = np.zeros((320, 320, 3), dtype=np.uint8)
        observer = FakeObserver()

        first = engine.step(frame, state, observer, now=1.0)
        second = engine.step(frame, state, observer, now=1.1)
        third = engine.step(frame, state, observer, now=1.2)
        fourth = engine.step(frame, state, observer, now=1.3)

        self.assertIsNone(first.move_pulse)
        self.assertEqual(second.move_pulse, "right")
        self.assertIsNone(third.move_pulse)
        self.assertTrue(fourth.tap_v)
        self.assertEqual(fourth.state, "START_MEDITATION")

    def test_meditation_exits_only_after_hp_and_chakra_are_both_ready(self):
        from pc_agent.kage_pilot.post_combat_v03 import ResourceLevels

        detector = FakeLeaderDetector([
            LeaderMatch(0.99, (120, 120, 68, 73), (160.0, 160.0)),
            LeaderMatch(0.99, (120, 120, 68, 73), (160.0, 160.0)),
        ])
        resources = FakeResourceReader([
            ResourceLevels(0.95, 0.40, 44, 18),
            ResourceLevels(0.95, 0.55, 44, 24),
            ResourceLevels(0.96, 0.56, 44, 25),
            ResourceLevels(0.97, 0.57, 45, 25),
        ])
        engine = PostCombatRecoveryEngine(
            leader_detector=detector,
            resource_reader=resources,
            leader_confirm_frames=2,
            recovery_confirm_frames=3,
            min_meditation_seconds=0.25,
        )
        state = SimpleNamespace(arena_rect=(0, 0, 320, 320), player_center=(160.0, 160.0))
        frame = np.zeros((320, 320, 3), dtype=np.uint8)
        observer = FakeObserver()

        engine.step(frame, state, observer, now=1.0)
        start = engine.step(frame, state, observer, now=1.1)
        self.assertTrue(start.tap_v)

        low_chakra = engine.step(frame, state, observer, now=1.4)
        ready1 = engine.step(frame, state, observer, now=1.5)
        ready2 = engine.step(frame, state, observer, now=1.6)
        done = engine.step(frame, state, observer, now=1.7)
        self.assertFalse(low_chakra.tap_v)
        self.assertFalse(ready1.tap_v)
        self.assertFalse(ready2.tap_v)
        self.assertTrue(done.tap_v)
        self.assertEqual(done.state, "READY")


if __name__ == "__main__":
    unittest.main()
