from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from pc_agent.kage_pilot.dojo_fight_v03e import TrainerClickTarget
from pc_agent.kage_pilot.dojo_fight_v03f import (
    BM_CLICK,
    LB_GETCURSEL,
    LB_SETCURSEL,
    DojoDialogMatchV2,
    _click_target_from_match,
    click_first_option_ok,
    request_taijutsu_dojo_spar,
)


class FakeController:
    instances = []

    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.repeat_keys = set()
        self.clicks = []
        self.key_states = []
        self.activations = 0
        self.releases = 0
        self.__class__.instances.append(self)

    def activate(self):
        self.activations += 1

    def release_all(self):
        self.releases += 1

    def apply_keys(self, keys):
        self.key_states.append(tuple(keys))

    def click_normalized(self, x, y):
        self.clicks.append((x, y))


class KagePilotV03FDojoLoopTests(unittest.TestCase):
    def setUp(self):
        FakeController.instances.clear()

    def test_visual_click_target_does_not_reject_distance_greater_than_one(self):
        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        match = SimpleNamespace(
            score=0.97,
            bbox=(700, 200, 32, 45),
            foot=(716.0, 239.6),
        )
        state = SimpleNamespace(
            arena_rect=(0, 0, 960, 540),
            player_center=(497.0, 254.0),
        )
        observer = SimpleNamespace(tile_size=32.0, grid_origin=(1.0, 14.0))

        target = _click_target_from_match(match, frame, state, observer)

        self.assertGreater(target.grid_distance, 1)
        self.assertAlmostEqual(target.score, 0.97)
        self.assertTrue(0.0 <= target.normalized_x <= 1.0)
        self.assertTrue(0.0 <= target.normalized_y <= 1.0)

    def test_dialog_confirmation_selects_first_item_and_clicks_own_ok_button(self):
        match = DojoDialogMatchV2(
            dialog_hwnd=100,
            listbox_hwnd=101,
            ok_button_hwnd=102,
            selected_index=1,
            item_count=3,
        )
        calls = []

        def send_message(hwnd, message, wparam, lparam):
            calls.append((hwnd, message, wparam, lparam))
            if message == LB_GETCURSEL:
                return 0
            return 0

        with (
            patch("win32gui.IsWindow", return_value=True),
            patch("win32gui.IsWindowVisible", return_value=False),
            patch("win32gui.SendMessage", side_effect=send_message),
        ):
            click_first_option_ok(match)

        self.assertIn((101, LB_SETCURSEL, 0, 0), calls)
        self.assertIn((102, BM_CLICK, 0, 0), calls)

    def test_request_searches_then_clicks_trainer_without_adjacency_gate(self):
        target = TrainerClickTarget(0.70, 0.35, 0.96, 3, (680, 170, 32, 45))
        dialog = DojoDialogMatchV2(100, 101, 102, 0, 3)
        focus = SimpleNamespace(ok=True, error=None)

        with (
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03f.search_trainer_until_visible",
                return_value=target,
            ) as search,
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03f.wait_for_dojo_dialog_with_ok",
                return_value=dialog,
            ),
            patch(
                "pc_agent.kage_pilot.dojo_fight_v03f.find_dojo_dialog_with_ok",
                return_value=dialog,
            ),
            patch("pc_agent.kage_pilot.dojo_fight_v03f.click_first_option_ok") as click_ok,
            patch("pc_agent.kage_pilot.dojo_fight_v03f._interruptible_wait"),
            patch("pc_agent.kage_pilot.pilot.WindowsGameController", FakeController),
            patch("pc_agent.windows.ensure_game_window_foreground", return_value=focus),
        ):
            result = request_taijutsu_dojo_spar(
                "Shinobi Story Online",
                dialog_delay_seconds=10.0,
                spawn_delay_seconds=5.0,
            )

        self.assertEqual(result, target)
        search.assert_called_once()
        self.assertEqual(len(FakeController.instances), 1)
        self.assertEqual(FakeController.instances[0].clicks, [(0.70, 0.35)])
        click_ok.assert_called_once_with(dialog)


if __name__ == "__main__":
    unittest.main()
