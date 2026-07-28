from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pc_agent.kage_pilot.dojo_fight_v03e import TrainerClickTarget
from pc_agent.kage_pilot.dojo_fight_v03f import DojoDialogMatchV2
from pc_agent.kage_pilot.dojo_fight_v03i import request_taijutsu_dojo_spar_single_click
from pc_agent.kage_pilot.post_combat_v03 import PostCombatDecision


class FakeController:
    def __init__(self) -> None:
        self.repeat_keys = {"r"}
        self.activations = 0
        self.releases = 0
        self.clicks: list[tuple[float, float]] = []

    def activate(self) -> None:
        self.activations += 1

    def release_all(self) -> None:
        self.releases += 1

    def click_normalized(self, x: float, y: float) -> None:
        self.clicks.append((x, y))


class FakeDetector:
    last_raw_score = -1.0
    last_raw_location = None
    _last_visual = None

    def find(self, *args, **kwargs):
        del args, kwargs
        return None


class KagePilotV03IRuntimeTests(unittest.TestCase):
    def test_dojo_request_clicks_trainer_exactly_once_even_with_legacy_attempts_six(self):
        controller = FakeController()
        target = TrainerClickTarget(0.55, 0.20, 0.96, 7, (500, 50, 32, 45))
        dialog = DojoDialogMatchV2(101, 102, 103, 0, 3)
        focus = SimpleNamespace(ok=True, error=None)

        with (
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.search_trainer_until_visible",
                return_value=target,
            ),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.wait_for_dojo_dialog_with_ok",
                return_value=dialog,
            ) as wait_dialog,
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.find_dojo_dialog_with_ok",
                return_value=dialog,
            ),
            patch("pc_agent.kage_pilot.dojo_fight_v03i.click_first_option_ok") as click_ok,
            patch("pc_agent.kage_pilot.dojo_fight_v03i._interruptible_wait"),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.time.monotonic",
                side_effect=[100.0, 101.0],
            ),
            patch("pc_agent.windows.ensure_game_window_foreground", return_value=focus),
        ):
            result = request_taijutsu_dojo_spar_single_click(
                "Shinobi Story Online",
                interaction_attempts=6,
                controller=controller,
            )

        self.assertEqual(result, target)
        self.assertEqual(controller.clicks, [(0.55, 0.20)])
        wait_dialog.assert_called_once()
        click_ok.assert_called_once_with(dialog)

    def test_fast_chakra_y_turns_on_once_above_90_hp_and_off_once_at_50_chakra(self):
        import kage_pilot_live_v03i_round as runtime

        engine = runtime.FastChakraVisualRecoveryEngine(
            leader_detector=FakeDetector(),
            search_timeout_seconds=45.0,
        )
        decisions = [
            PostCombatDecision(state="MEDITATING", health=0.91, chakra=0.40),
            PostCombatDecision(state="MEDITATING", health=0.92, chakra=0.42),
            PostCombatDecision(state="MEDITATING", health=0.93, chakra=0.50),
            PostCombatDecision(state="MEDITATING", health=0.94, chakra=0.52),
        ]

        with patch(
            "pc_agent.kage_pilot.post_combat_v03h.VisualProgressPostCombatRecoveryEngine.step",
            side_effect=decisions,
        ):
            engine.step(None, None, None, now=1.0)
            self.assertIsNone(engine.pending_y_action)
            engine.step(None, None, None, now=1.1)
            self.assertEqual(engine.consume_y_action(), "on")
            self.assertTrue(engine.y_fast_active)

            engine.step(None, None, None, now=1.2)
            self.assertIsNone(engine.pending_y_action)
            engine.step(None, None, None, now=1.3)
            self.assertEqual(engine.consume_y_action(), "off")
            self.assertFalse(engine.y_fast_active)

    def test_fast_chakra_y_does_not_start_at_exactly_90_percent_hp(self):
        import kage_pilot_live_v03i_round as runtime

        engine = runtime.FastChakraVisualRecoveryEngine(
            leader_detector=FakeDetector(),
            search_timeout_seconds=45.0,
        )
        decision = PostCombatDecision(state="MEDITATING", health=0.90, chakra=0.25)
        with patch(
            "pc_agent.kage_pilot.post_combat_v03h.VisualProgressPostCombatRecoveryEngine.step",
            return_value=decision,
        ):
            engine.step(None, None, None, now=1.0)
            engine.step(None, None, None, now=1.1)
        self.assertIsNone(engine.pending_y_action)
        self.assertFalse(engine.y_fast_active)

    def test_map_save_resync_planner_releases_r_and_all_other_keys(self):
        import kage_pilot_live_v03i_round as runtime

        runtime._RESYNC.generation = 0
        runtime._RESYNC.active_until = -1e9
        runtime._RESYNC.trigger("unit_test", now=10.0, hold_seconds=2.0)
        planner = runtime.MapSaveResyncPlanner(h_enabled=True)
        decision = SimpleNamespace(base_r=True)
        command = planner.plan(decision, now=10.5)

        self.assertEqual(command.held_keys, ())
        self.assertIsNone(command.face_pulse)
        self.assertIsNone(command.move_pulse)
        self.assertFalse(command.h_fire)
        self.assertEqual(command.safety_state, "MAP_SAVE_RESYNC")

        runtime._RESYNC.active_until = -1e9


if __name__ == "__main__":
    unittest.main()
