from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import kage_pilot_loop_v03g as loop_v03g
from pc_agent.kage_pilot.dojo_fight_v03e import DojoFightRequestError, TrainerClickTarget
from pc_agent.kage_pilot.dojo_fight_v03f import DojoDialogMatchV2
from pc_agent.kage_pilot.dojo_fight_v03i import (
    DojoRoundWithoutCombatError,
    request_taijutsu_dojo_spar_single_click,
)


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


TARGET = TrainerClickTarget(0.55, 0.20, 0.96, 1, (500, 50, 32, 45))
DIALOG = DojoDialogMatchV2(101, 102, 103, 0, 3)
FOCUS_OK = SimpleNamespace(ok=True, error=None)


class KagePilotDojoDialogRetryTests(unittest.TestCase):
    def _run_success(self, success_attempt: int):
        controller = FakeController()
        misses = [DojoFightRequestError("DOJO_DIALOG_NOT_FOUND")] * (success_attempt - 1)
        wait_side_effect = [*misses, DIALOG]
        with (
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.search_trainer_until_visible",
                return_value=TARGET,
            ),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.wait_for_dojo_dialog_with_ok",
                side_effect=wait_side_effect,
            ) as wait_dialog,
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.find_dojo_dialog_with_ok",
                return_value=DIALOG,
            ),
            patch("pc_agent.kage_pilot.dojo_fight_v03i.click_first_option_ok") as click_ok,
            patch("pc_agent.kage_pilot.dojo_fight_v03i._interruptible_wait") as wait,
            patch("pc_agent.windows.ensure_game_window_foreground", return_value=FOCUS_OK),
        ):
            result = request_taijutsu_dojo_spar_single_click(
                "Shinobi Story Online",
                dialog_delay_seconds=5.0,
                dialog_find_timeout_seconds=0.5,
                dialog_retries=3,
                spawn_delay_seconds=5.0,
                round_number=3,
                controller=controller,
            )
        return controller, result, wait_dialog, click_ok, wait

    def test_dialog_found_after_initial_wait(self):
        controller, result, wait_dialog, click_ok, wait = self._run_success(1)
        self.assertEqual(result, TARGET)
        self.assertEqual(controller.clicks, [(0.55, 0.20)])
        self.assertEqual(wait_dialog.call_count, 1)
        self.assertEqual(click_ok.call_count, 1)
        self.assertEqual(wait.call_count, 2)  # initial dialog wait + spawn wait

    def test_dialog_found_after_one_additional_wait(self):
        controller, _, wait_dialog, click_ok, wait = self._run_success(2)
        self.assertEqual(controller.clicks, [(0.55, 0.20)])
        self.assertEqual(wait_dialog.call_count, 2)
        self.assertEqual(click_ok.call_count, 1)
        self.assertEqual(wait.call_count, 3)  # two dialog waits + spawn wait

    def test_dialog_found_after_two_additional_waits(self):
        controller, _, wait_dialog, click_ok, wait = self._run_success(3)
        self.assertEqual(controller.clicks, [(0.55, 0.20)])
        self.assertEqual(wait_dialog.call_count, 3)
        self.assertEqual(click_ok.call_count, 1)
        self.assertEqual(wait.call_count, 4)

    def test_dialog_found_after_three_additional_waits(self):
        controller, _, wait_dialog, click_ok, wait = self._run_success(4)
        self.assertEqual(controller.clicks, [(0.55, 0.20)])
        self.assertEqual(wait_dialog.call_count, 4)
        self.assertEqual(click_ok.call_count, 1)
        self.assertEqual(wait.call_count, 5)

    def test_dialog_never_appears_finishes_round_without_combat(self):
        controller = FakeController()
        with (
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.search_trainer_until_visible",
                return_value=TARGET,
            ),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.wait_for_dojo_dialog_with_ok",
                side_effect=DojoFightRequestError("DOJO_DIALOG_NOT_FOUND"),
            ) as wait_dialog,
            patch("pc_agent.kage_pilot.dojo_fight_v03i.click_first_option_ok") as click_ok,
            patch("pc_agent.kage_pilot.dojo_fight_v03i._interruptible_wait") as wait,
        ):
            with self.assertRaises(DojoRoundWithoutCombatError) as raised:
                request_taijutsu_dojo_spar_single_click(
                    "Shinobi Story Online",
                    dialog_retries=3,
                    round_number=3,
                    controller=controller,
                )

        error = raised.exception
        self.assertEqual(error.reason, "DOJO_DIALOG_NOT_FOUND")
        self.assertEqual(error.trainer_clicks, 1)
        self.assertEqual(error.dialog_attempts, 4)
        self.assertEqual(controller.clicks, [(0.55, 0.20)])
        self.assertEqual(wait_dialog.call_count, 4)
        self.assertEqual(wait.call_count, 4)
        click_ok.assert_not_called()

    def test_trainer_click_function_is_never_called_twice(self):
        controller = FakeController()
        with (
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.search_trainer_until_visible",
                return_value=TARGET,
            ),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.wait_for_dojo_dialog_with_ok",
                side_effect=DojoFightRequestError("DOJO_DIALOG_NOT_FOUND"),
            ),
            patch("pc_agent.kage_pilot.dojo_fight_v03i._interruptible_wait"),
        ):
            with self.assertRaises(DojoRoundWithoutCombatError):
                request_taijutsu_dojo_spar_single_click(
                    "Shinobi Story Online",
                    dialog_retries=3,
                    controller=controller,
                )
        self.assertEqual(len(controller.clicks), 1)

    def test_f12_during_wait_releases_inputs_and_stops_checks(self):
        controller = FakeController()
        with (
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.search_trainer_until_visible",
                return_value=TARGET,
            ),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i._interruptible_wait",
                side_effect=DojoFightRequestError("F12_STOP"),
            ),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.wait_for_dojo_dialog_with_ok"
            ) as wait_dialog,
        ):
            with self.assertRaisesRegex(DojoFightRequestError, "F12_STOP"):
                request_taijutsu_dojo_spar_single_click(
                    "Shinobi Story Online",
                    dialog_retries=3,
                    controller=controller,
                )
        self.assertEqual(controller.clicks, [(0.55, 0.20)])
        self.assertGreaterEqual(controller.releases, 1)
        wait_dialog.assert_not_called()

    def test_disappearing_hwnd_is_not_clicked_and_retry_can_succeed(self):
        controller = FakeController()
        with (
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.search_trainer_until_visible",
                return_value=TARGET,
            ),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.wait_for_dojo_dialog_with_ok",
                side_effect=[DIALOG, DIALOG],
            ) as wait_dialog,
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03i.find_dojo_dialog_with_ok",
                side_effect=[None, DIALOG],
            ),
            patch("pc_agent.game_window.find_exact_game_window", return_value=999),
            patch("pc_agent.kage_pilot.dojo_fight_v03i.click_first_option_ok") as click_ok,
            patch("pc_agent.kage_pilot.dojo_fight_v03i._interruptible_wait"),
            patch("pc_agent.windows.ensure_game_window_foreground", return_value=FOCUS_OK),
        ):
            result = request_taijutsu_dojo_spar_single_click(
                "Shinobi Story Online",
                dialog_retries=3,
                controller=controller,
            )
        self.assertEqual(result, TARGET)
        self.assertEqual(controller.clicks, [(0.55, 0.20)])
        self.assertEqual(wait_dialog.call_count, 2)
        self.assertEqual(click_ok.call_count, 1)
        click_ok.assert_called_once_with(DIALOG)

    def test_round_three_dialog_failure_does_not_stop_ten_round_loop(self):
        requested_rounds: list[int] = []
        combat_rounds: list[int] = []

        def fake_request(_game_title, **kwargs):
            round_number = int(kwargs["round_number"])
            requested_rounds.append(round_number)
            if round_number == 3:
                raise DojoRoundWithoutCombatError(
                    "DOJO_DIALOG_NOT_FOUND",
                    trainer_clicks=1,
                    dialog_attempts=4,
                )
            return TARGET

        def fake_run_round(_args, *, round_number):
            combat_rounds.append(int(round_number))
            return True

        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                rounds=10,
                combat_seconds=120.0,
                post_combat_timeout=240.0,
                dialog_delay=5.0,
                dialog_timeout=0.5,
                dialog_retries=3,
                spawn_delay=5.0,
                trainer_search_timeout=90.0,
                interaction_attempts=1,
                round_startup_delay=1.0,
                chat_poll_seconds=0.15,
                recovery_hp_percent=90.0,
                recovery_chakra_percent=50.0,
                leader_threshold=0.88,
                log_dir=Path(directory),
                disable_h=False,
            )
            parser = SimpleNamespace(parse_args=lambda: args)
            output = StringIO()
            with (
                patch.object(loop_v03g, "build_parser", return_value=parser),
                patch.object(loop_v03g, "load_config", return_value=SimpleNamespace(game_title="Shinobi Story Online")),
                patch.object(loop_v03g, "REQUEST_DOJO_FIGHT", side_effect=fake_request),
                patch.object(loop_v03g, "DIALOG_RETRY_POLICY_ENABLED", True),
                patch.object(loop_v03g, "_run_round", side_effect=fake_run_round),
                patch.object(loop_v03g, "f12_pressed", return_value=False),
                patch.object(loop_v03g.time, "sleep"),
                redirect_stdout(output),
            ):
                return_code = loop_v03g.main()

        self.assertEqual(return_code, 0)
        self.assertEqual(requested_rounds, list(range(1, 11)))
        self.assertEqual(combat_rounds, [1, 2, 4, 5, 6, 7, 8, 9, 10])
        self.assertNotIn(11, requested_rounds)
        text = output.getvalue()
        self.assertIn("ROUND 3: FINISHED_WITHOUT_COMBAT", text)
        self.assertIn("ROUND 4: SEARCH AND REQUEST", text)
        self.assertIn(
            "DOJO_LOOP_FINISHED requested=10 processed=10 completed=9 "
            "finished_without_combat=1 failed=0 emergency_stopped=0",
            text,
        )


if __name__ == "__main__":
    unittest.main()
