from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pc_agent.kage_pilot import dojo_precombat_guard_v351 as guard
from pc_agent.kage_pilot.dojo_fight_v03e import (
    DojoFightRequestError,
    TrainerClickTarget,
)
from pc_agent.kage_pilot.dojo_fight_v03f import DojoDialogMatchV2
from pc_agent.kage_pilot.dojo_request import (
    request_taijutsu_dojo_spar_single_click as canonical_request,
)


TARGET = TrainerClickTarget(0.55, 0.20, 0.96, 1, (500, 50, 32, 45))
DIALOG = DojoDialogMatchV2(101, 102, 103, 0, 3)
FOCUS_OK = SimpleNamespace(ok=True, error=None)


class FakeRequestController:
    def __init__(self, events: list[tuple]) -> None:
        self.events = events
        self.repeat_keys: set[str] = set()

    def activate(self) -> None:
        self.events.append(("activate",))

    def release_all(self) -> None:
        self.events.append(("release",))

    def apply_keys(self, keys) -> None:
        self.events.append(("keys", tuple(keys)))

    def click_normalized(self, x: float, y: float) -> None:
        self.events.append(("trainer_click", round(x, 3), round(y, 3)))


class FakeRoundController:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.repeat_keys: set[str] = set()

    def activate(self) -> None:
        self.events.append(("activate",))

    def release_all(self) -> None:
        self.events.append(("release",))

    def apply_keys(self, keys) -> None:
        self.events.append(("keys", tuple(keys)))


class DojoPrecombatGuardV351Tests(unittest.TestCase):
    def test_canonical_request_uses_the_guarded_provider(self):
        self.assertIs(canonical_request, guard.request_taijutsu_dojo_spar_single_click)

    def test_after_ok_ctrl_right_pulses_once_then_r_is_held_through_spawn_wait(self):
        events: list[tuple] = []
        controller = FakeRequestController(events)

        def wait(seconds: float) -> None:
            events.append(("wait", round(float(seconds), 3)))

        def click_ok(_dialog) -> None:
            events.append(("ok",))

        with (
            patch.object(guard.legacy_request, "search_trainer_until_visible", return_value=TARGET),
            patch.object(guard.legacy_request, "wait_for_dojo_dialog_with_ok", return_value=DIALOG),
            patch.object(guard.legacy_request, "find_dojo_dialog_with_ok", return_value=DIALOG),
            patch.object(guard.legacy_request, "click_first_option_ok", side_effect=click_ok),
            patch.object(guard.legacy_request, "_interruptible_wait", side_effect=wait),
            patch("pc_agent.windows.ensure_game_window_foreground", return_value=FOCUS_OK),
        ):
            result = canonical_request(
                "Shinobi Story Online",
                dialog_delay_seconds=5.0,
                dialog_find_timeout_seconds=0.5,
                dialog_retries=0,
                spawn_delay_seconds=5.0,
                round_number=1,
                controller=controller,
            )

        self.assertEqual(result, TARGET)
        self.assertEqual(controller.repeat_keys, {"r"})
        self.assertEqual(
            [event for event in events if event == ("keys", ("ctrl", "right"))],
            [("keys", ("ctrl", "right"))],
        )

        ok_index = events.index(("ok",))
        combo_index = events.index(("keys", ("ctrl", "right")))
        guard_wait_index = events.index(("wait", 0.08))
        first_r_index = events.index(("keys", ("r",)), combo_index)
        spawn_wait_index = max(
            index for index, event in enumerate(events) if event == ("wait", 5.0)
        )
        final_release_index = len(events) - 1

        self.assertLess(ok_index, combo_index)
        self.assertLess(combo_index, guard_wait_index)
        self.assertLess(guard_wait_index, first_r_index)
        self.assertLess(first_r_index, spawn_wait_index)
        self.assertEqual(events[final_release_index], ("release",))

        # Every validated release after arming is converted back to held R until
        # the request returns; only the outer owner cleanup performs a real release.
        self.assertTrue(
            all(
                event != ("release",)
                for event in events[first_r_index:final_release_index]
            )
        )

    def test_no_guard_input_is_sent_when_the_dialog_never_appears(self):
        events: list[tuple] = []
        controller = FakeRequestController(events)

        with (
            patch.object(guard.legacy_request, "search_trainer_until_visible", return_value=TARGET),
            patch.object(
                guard.legacy_request,
                "wait_for_dojo_dialog_with_ok",
                side_effect=DojoFightRequestError("DOJO_DIALOG_NOT_FOUND"),
            ),
            patch.object(guard.legacy_request, "_interruptible_wait"),
        ):
            with self.assertRaises(guard.DojoRoundWithoutCombatError):
                canonical_request(
                    "Shinobi Story Online",
                    dialog_retries=0,
                    controller=controller,
                )

        self.assertNotIn(("keys", ("ctrl", "right")), events)
        self.assertNotIn(("keys", ("r",)), events)

    def test_round_startup_first_release_arms_r_and_later_releases_are_normal(self):
        guard.install_round_precombat_r_hold(FakeRoundController)
        controller = FakeRoundController()

        controller.activate()
        controller.release_all()

        self.assertEqual(
            controller.events,
            [
                ("activate",),
                ("release",),
                ("keys", ("r",)),
            ],
        )
        self.assertEqual(controller.repeat_keys, {"r"})

        controller.release_all()
        self.assertEqual(controller.events[-1], ("release",))
        self.assertEqual(
            controller.events.count(("keys", ("r",))),
            1,
        )


if __name__ == "__main__":
    unittest.main()
