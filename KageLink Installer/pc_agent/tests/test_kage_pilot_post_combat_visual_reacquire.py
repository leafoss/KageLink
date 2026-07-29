from __future__ import annotations

from types import SimpleNamespace
import unittest

import numpy as np

from pc_agent.kage_pilot.post_combat_v03b import LeaderMatchV2
from pc_agent.kage_pilot.post_combat_v03c import PostCombatRecoveryEngineV3


class FakeObserver:
    tile_size = 32.0
    grid_origin = (0.0, 0.0)


class FakeLeaderDetector:
    last_raw_score = -1.0
    last_raw_location = None
    _last_visual = None

    def __init__(self, matches):
        self.matches = list(matches)
        self.index = 0

    def find(self, frame_bgr, *, arena_rect=None, flow=None, now=None):
        del frame_bgr, arena_rect, flow, now
        if not self.matches:
            return None
        value = self.matches[min(self.index, len(self.matches) - 1)]
        self.index += 1
        if value is not None and value.source == "visual":
            self._last_visual = value
        return value


MEMORY_ADJACENT = LeaderMatchV2(
    score=0.991,
    bbox=(160, 120, 32, 45),
    foot=(176.0, 160.0),
    source="memory",
)
VISUAL_CELL_A = LeaderMatchV2(
    score=0.998,
    bbox=(160, 120, 32, 45),
    foot=(176.0, 160.0),
    source="visual",
)
VISUAL_CELL_B = LeaderMatchV2(
    score=0.998,
    bbox=(191, 120, 32, 45),
    foot=(207.0, 160.0),
    source="visual",
)


class KagePilotPostCombatVisualReacquireTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((320, 320, 3), dtype=np.uint8)
        self.state = SimpleNamespace(
            arena_rect=(0, 0, 320, 320),
            player_center=(160.0, 160.0),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0),
        )
        self.observer = FakeObserver()

    def test_two_current_adjacent_visuals_survive_one_cell_grid_jitter(self):
        engine = PostCombatRecoveryEngineV3(
            leader_detector=FakeLeaderDetector([VISUAL_CELL_A, VISUAL_CELL_B]),
            leader_confirm_frames=2,
        )

        first = engine.step(self.frame, self.state, self.observer, now=1.0)
        second = engine.step(self.frame, self.state, self.observer, now=1.1)

        self.assertFalse(first.tap_v)
        self.assertEqual(first.state, "SEEK_LEADER")
        self.assertTrue(second.tap_v)
        self.assertEqual(second.state, "START_MEDITATION")
        self.assertIn("duas confirmacoes visuais", second.reason)

    def test_visual_memory_visual_flicker_can_confirm_but_memory_never_taps_v(self):
        engine = PostCombatRecoveryEngineV3(
            leader_detector=FakeLeaderDetector(
                [VISUAL_CELL_A, MEMORY_ADJACENT, VISUAL_CELL_B]
            ),
            leader_confirm_frames=2,
        )

        first_visual = engine.step(self.frame, self.state, self.observer, now=1.0)
        memory = engine.step(self.frame, self.state, self.observer, now=1.1)
        second_visual = engine.step(self.frame, self.state, self.observer, now=1.2)

        self.assertFalse(first_visual.tap_v)
        self.assertFalse(memory.tap_v)
        self.assertIn("memory says adjacent", memory.reason)
        self.assertTrue(second_visual.tap_v)
        self.assertEqual(second_visual.state, "START_MEDITATION")

    def test_adjacent_memory_stall_enters_visual_reacquisition_search(self):
        engine = PostCombatRecoveryEngineV3(
            leader_detector=FakeLeaderDetector([MEMORY_ADJACENT] * 4),
            adjacent_memory_reacquire_seconds=1.0,
            search_delay_seconds=0.25,
            search_timeout_seconds=10.0,
            search_pulses_per_tile=2,
            search_max_radius_tiles=2,
        )

        initial = engine.step(self.frame, self.state, self.observer, now=1.0)
        reacquire_wait = engine.step(self.frame, self.state, self.observer, now=2.1)
        reacquire_move = engine.step(self.frame, self.state, self.observer, now=2.4)

        self.assertFalse(initial.tap_v)
        self.assertEqual(initial.state, "SEEK_LEADER")
        self.assertFalse(reacquire_wait.tap_v)
        self.assertEqual(reacquire_wait.state, "REACQUIRE_VISUAL_WAIT")
        self.assertFalse(reacquire_move.tap_v)
        self.assertEqual(reacquire_move.state, "REACQUIRE_LEADER_VISUAL")
        self.assertEqual(reacquire_move.move_pulse, "up")
        self.assertIn("forcar nova confirmacao visual", reacquire_move.reason)

    def test_visual_reacquisition_exits_memory_search_and_starts_meditation(self):
        engine = PostCombatRecoveryEngineV3(
            leader_detector=FakeLeaderDetector(
                [
                    MEMORY_ADJACENT,
                    MEMORY_ADJACENT,
                    MEMORY_ADJACENT,
                    VISUAL_CELL_A,
                    VISUAL_CELL_B,
                ]
            ),
            leader_confirm_frames=2,
            adjacent_memory_reacquire_seconds=1.0,
            search_delay_seconds=0.25,
            search_timeout_seconds=10.0,
            search_pulses_per_tile=2,
            search_max_radius_tiles=2,
        )

        engine.step(self.frame, self.state, self.observer, now=1.0)
        wait = engine.step(self.frame, self.state, self.observer, now=2.1)
        move = engine.step(self.frame, self.state, self.observer, now=2.4)
        first_visual = engine.step(self.frame, self.state, self.observer, now=2.5)
        second_visual = engine.step(self.frame, self.state, self.observer, now=2.6)

        self.assertEqual(wait.state, "REACQUIRE_VISUAL_WAIT")
        self.assertEqual(move.state, "REACQUIRE_LEADER_VISUAL")
        self.assertFalse(first_visual.tap_v)
        self.assertTrue(second_visual.tap_v)
        self.assertEqual(second_visual.state, "START_MEDITATION")


if __name__ == "__main__":
    unittest.main()
