from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from pc_agent.kage_pilot.dojo_fight_v03e import (
    DojoDialogMatch,
    TrainerClickTarget,
    request_taijutsu_dojo_spar,
)
from pc_agent.kage_pilot.post_combat_v03e import ObstacleAwarePostCombatRecoveryEngine


class FakeDetector:
    last_raw_score = -1.0
    last_raw_location = None

    def find(self, *args, **kwargs):
        del args, kwargs
        return None


class FakeController:
    instances = []

    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.repeat_keys = set()
        self.clicks = []
        self.activations = 0
        self.releases = 0
        self.__class__.instances.append(self)

    def activate(self):
        self.activations += 1

    def release_all(self):
        self.releases += 1

    def click_normalized(self, x, y):
        self.clicks.append((x, y))


class KagePilotV03ELoopTests(unittest.TestCase):
    def setUp(self):
        FakeController.instances.clear()

    def _engine(self, **kwargs):
        return ObstacleAwarePostCombatRecoveryEngine(
            leader_detector=FakeDetector(),
            search_timeout_seconds=45.0,
            search_pulses_per_tile=1,
            **kwargs,
        )

    def test_two_no_motion_probes_temporarily_block_and_advance_direction(self):
        engine = self._engine(obstacle_confirmations=2, obstacle_ttl_seconds=3.0)
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        state = SimpleNamespace(
            arena_rect=(0, 0, 160, 120),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0),
        )

        engine.observe_movement_frame(frame, state, now=0.0)
        self.assertEqual(engine.search.phase, "up")

        engine.arm_movement_probe("up", now=0.10)
        engine.observe_movement_frame(frame, state, now=0.20)
        self.assertFalse(engine._is_blocked("up", now=0.20))

        engine.arm_movement_probe("up", now=0.30)
        engine.observe_movement_frame(frame, state, now=0.40)
        self.assertTrue(engine._is_blocked("up", now=0.40))
        self.assertEqual(engine.search.phase, "right")

    def test_detected_camera_translation_clears_failure(self):
        engine = self._engine(obstacle_confirmations=2)
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        still = SimpleNamespace(
            arena_rect=(0, 0, 160, 120),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0),
        )
        moved = SimpleNamespace(
            arena_rect=(0, 0, 160, 120),
            global_flow=SimpleNamespace(dx=32.0, dy=0.0),
        )

        engine.observe_movement_frame(frame, still, now=0.0)
        engine.arm_movement_probe("right", now=0.10)
        engine.observe_movement_frame(frame, still, now=0.20)
        engine.arm_movement_probe("right", now=0.30)
        engine.observe_movement_frame(frame, moved, now=0.40)

        self.assertTrue(engine.last_movement_detected)
        self.assertFalse(engine._is_blocked("right", now=0.40))

    def test_subthreshold_trainer_hint_pauses_search_without_authorizing_match(self):
        detector = FakeDetector()
        detector.last_raw_score = 0.84
        detector.last_raw_location = (320, 180)
        engine = ObstacleAwarePostCombatRecoveryEngine(
            leader_detector=detector,
            search_hint_threshold=0.80,
            search_timeout_seconds=45.0,
        )

        decision = engine._search_decision(now=1.0)
        self.assertEqual(decision.state, "SEARCH_CONFIRM_HINT")
        self.assertIsNone(decision.move_pulse)
        self.assertFalse(decision.tap_v)

    def test_dojo_request_clicks_once_confirms_first_option_and_refocuses(self):
        click_target = TrainerClickTarget(0.50, 0.40, 0.97, 1, (100, 80, 32, 45))
        dialog = DojoDialogMatch(101, 102, 0, 3)
        focus = SimpleNamespace(ok=True, error=None)

        with (
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03e.locate_adjacent_trainer",
                return_value=click_target,
            ),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03e.wait_for_dojo_dialog",
                return_value=dialog,
            ),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03e.find_dojo_dialog",
                return_value=dialog,
            ),
            patch("pc_agent.kage_pilot.dojo_fight_v03e.confirm_first_dojo_option") as confirm,
            patch("pc_agent.kage_pilot.dojo_fight_v03e._interruptible_wait"),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03e.time.monotonic",
                side_effect=[100.0, 110.0],
            ),
            patch("pc_agent.kage_pilot.pilot.WindowsGameController", FakeController),
            patch("pc_agent.windows.ensure_game_window_foreground", return_value=focus),
        ):
            result = request_taijutsu_dojo_spar(
                "Shinobi Story Online",
                dialog_delay_seconds=10.0,
                spawn_delay_seconds=5.0,
            )

        self.assertEqual(result, click_target)
        self.assertEqual(len(FakeController.instances), 1)
        self.assertEqual(FakeController.instances[0].clicks, [(0.50, 0.40)])
        confirm.assert_called_once_with(dialog)


if __name__ == "__main__":
    unittest.main()
