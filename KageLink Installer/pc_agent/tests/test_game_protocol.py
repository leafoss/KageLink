from __future__ import annotations

import unittest

from pc_agent.game_protocol import (
    ACTION_KEYS,
    ALLOWED_KEYS,
    MOVEMENT_KEYS,
    normalize_pressed,
    normalize_view_mode,
    parse_control_message,
)


class GameProtocolTests(unittest.TestCase):
    def test_whitelist_contains_movement_and_configurable_action_keys(self) -> None:
        self.assertTrue(MOVEMENT_KEYS.issubset(ALLOWED_KEYS))
        self.assertTrue({"e", "space", "g", "v", "z", "x", "u"}.issubset(ACTION_KEYS))
        self.assertTrue({"enter", "escape", "f1", "f12", "0", "9"}.issubset(ACTION_KEYS))

    def test_normalizes_key_state_and_removes_duplicates(self) -> None:
        self.assertEqual(
            normalize_pressed(["UP", "right", "up", " E "]),
            frozenset({"up", "right", "e"}),
        )

    def test_accepts_safe_configurable_keys(self) -> None:
        self.assertEqual(
            normalize_pressed(["z", "x", "u", "f4", "alt"]),
            frozenset({"z", "x", "u", "f4", "alt"}),
        )

    def test_rejects_arbitrary_commands(self) -> None:
        with self.assertRaisesRegex(ValueError, "INVALID_GAME_KEYS"):
            normalize_pressed(["powershell.exe"])

    def test_parses_active_message(self) -> None:
        result = parse_control_message({"type": "active", "value": True})
        self.assertEqual(result.kind, "active")
        self.assertTrue(result.active)

    def test_parses_focus_click_message(self) -> None:
        result = parse_control_message({"type": "focus_click"})
        self.assertEqual(result.kind, "focus_click")

    def test_parses_multitouch_key_state(self) -> None:
        result = parse_control_message(
            {"type": "keys", "pressed": ["up", "right", "e", "z"]}
        )
        self.assertEqual(result.pressed, frozenset({"up", "right", "e", "z"}))

    def test_heartbeat_preserves_timestamp(self) -> None:
        result = parse_control_message(
            {"type": "heartbeat", "pressed": [], "timestamp": 1234.5}
        )
        self.assertEqual(result.timestamp, 1234.5)

    def test_view_mode_is_limited_to_two_modes(self) -> None:
        self.assertEqual(normalize_view_mode("zoom"), "zoom")
        self.assertEqual(normalize_view_mode("full"), "full")
        self.assertEqual(normalize_view_mode("anything"), "full")


if __name__ == "__main__":
    unittest.main()
