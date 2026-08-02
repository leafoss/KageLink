from __future__ import annotations

import unittest

from navigation_lab.observer.window_capture import WindowNotFoundError, _select_window_match


class WindowSelectionTests(unittest.TestCase):
    def test_exact_game_title_wins_over_longer_matching_console(self) -> None:
        matches = [
            (101, "PowerShell — Shinobi Story Online capture"),
            (202, "Shinobi Story Online"),
            (303, "Debug — Shinobi Story Online — overlay"),
        ]
        self.assertEqual(
            _select_window_match(matches, "Shinobi Story Online"),
            (202, "Shinobi Story Online"),
        )

    def test_previous_exact_hwnd_remains_stable(self) -> None:
        matches = [
            (201, "Shinobi Story Online"),
            (202, "Shinobi Story Online"),
        ]
        self.assertEqual(
            _select_window_match(matches, "Shinobi Story Online", previous_hwnd=202),
            (202, "Shinobi Story Online"),
        )

    def test_shortest_partial_title_is_safe_fallback(self) -> None:
        matches = [
            (101, "Console helper for Shinobi Story Online diagnostics"),
            (202, "Shinobi Story Online - Dream Seeker"),
        ]
        self.assertEqual(
            _select_window_match(matches, "Shinobi Story Online"),
            (202, "Shinobi Story Online - Dream Seeker"),
        )

    def test_missing_window_is_explicit(self) -> None:
        with self.assertRaises(WindowNotFoundError):
            _select_window_match([], "Shinobi Story Online")


if __name__ == "__main__":
    unittest.main()
