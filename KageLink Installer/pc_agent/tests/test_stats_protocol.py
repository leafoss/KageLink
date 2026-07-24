from __future__ import annotations

import unittest

from pc_agent.stats_protocol import (
    STATS_OPEN_X,
    STATS_OPEN_Y,
    normalized_client_point,
    parse_stats_control_message,
)


class StatsProtocolTests(unittest.TestCase):
    def test_open_point_is_normalized(self) -> None:
        self.assertGreater(STATS_OPEN_X, 0.0)
        self.assertLess(STATS_OPEN_X, 1.0)
        self.assertGreater(STATS_OPEN_Y, 0.0)
        self.assertLess(STATS_OPEN_Y, 1.0)
        self.assertAlmostEqual(STATS_OPEN_X * 961.0, 145.0)
        self.assertAlmostEqual(STATS_OPEN_Y * 833.0, 623.0)


    def test_maps_normalized_coordinates_into_current_client_rect(self) -> None:
        self.assertEqual(
            normalized_client_point(100, 200, 401, 801, 0.0, 0.0),
            (100, 200),
        )
        self.assertEqual(
            normalized_client_point(100, 200, 401, 801, 0.5, 0.5),
            (300, 600),
        )
        self.assertEqual(
            normalized_client_point(100, 200, 401, 801, 1.0, 1.0),
            (500, 1000),
        )

    def test_rejects_invalid_client_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "INVALID_STATS_CLIENT_SIZE"):
            normalized_client_point(0, 0, 0, 100, 0.5, 0.5)

    def test_parses_open_command(self) -> None:
        command = parse_stats_control_message({"type": "open_stats"})
        self.assertEqual(command.kind, "open_stats")

    def test_parses_left_and_right_clicks(self) -> None:
        left = parse_stats_control_message(
            {"type": "click", "x": 0.25, "y": 0.75, "button": "left", "window_id": 123}
        )
        right = parse_stats_control_message(
            {"type": "click", "x": 1, "y": 0, "button": "right", "window_id": 123}
        )
        self.assertEqual((left.x, left.y, left.button, left.window_id), (0.25, 0.75, "left", 123))
        self.assertEqual((right.x, right.y, right.button), (1.0, 0.0, "right"))

    def test_rejects_coordinates_outside_client(self) -> None:
        with self.assertRaisesRegex(ValueError, "INVALID_STATS_X"):
            parse_stats_control_message(
                {"type": "click", "x": 1.1, "y": 0.5, "button": "left", "window_id": 123}
            )

    def test_rejects_unknown_mouse_button(self) -> None:
        with self.assertRaisesRegex(ValueError, "INVALID_STATS_MOUSE_BUTTON"):
            parse_stats_control_message(
                {"type": "click", "x": 0.5, "y": 0.5, "button": "middle", "window_id": 123}
            )

    def test_rejects_missing_window_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "INVALID_STATS_WINDOW_ID"):
            parse_stats_control_message(
                {"type": "click", "x": 0.5, "y": 0.5, "button": "left"}
            )

    def test_heartbeat_preserves_timestamp(self) -> None:
        command = parse_stats_control_message(
            {"type": "heartbeat", "timestamp": 44.5}
        )
        self.assertEqual(command.timestamp, 44.5)


if __name__ == "__main__":
    unittest.main()
