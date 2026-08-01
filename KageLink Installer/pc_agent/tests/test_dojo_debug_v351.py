from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest

from pc_agent.kage_pilot.dojo_debug_v351 import (
    DojoDebugOverlay,
    DojoDebugSettings,
    read_debug_settings,
    write_debug_settings,
)


class DojoDebugV351Tests(unittest.TestCase):
    def test_settings_round_trip_and_normalize_safety_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "debug.json"
            written = write_debug_settings(
                DojoDebugSettings(
                    enabled=True,
                    opacity=4.0,
                    fps=100.0,
                    level="unknown",
                    meditation_enter_delay_seconds=1.0,
                    meditation_exit_delay_seconds=2.0,
                    meditation_timeout_seconds=3.0,
                ),
                path,
            )
            self.assertEqual(written, path)
            loaded = read_debug_settings(path)

        self.assertTrue(loaded.enabled)
        self.assertEqual(loaded.opacity, 1.0)
        self.assertEqual(loaded.fps, 30.0)
        self.assertEqual(loaded.level, "detections")
        self.assertEqual(loaded.meditation_enter_delay_seconds, 5.0)
        self.assertEqual(loaded.meditation_exit_delay_seconds, 5.0)
        self.assertEqual(loaded.meditation_timeout_seconds, 15.0)

    def test_opacity_accepts_ten_percent_and_clamps_lower_values(self):
        self.assertEqual(DojoDebugSettings(opacity=0.10).normalized().opacity, 0.10)
        self.assertEqual(DojoDebugSettings(opacity=0.01).normalized().opacity, 0.10)

    def test_malformed_settings_fail_closed_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "debug.json"
            path.write_text(
                '{"enabled":"yes","opacity":"bad","fps":null}',
                encoding="utf-8",
            )
            loaded = read_debug_settings(path)
        self.assertFalse(loaded.enabled)
        self.assertEqual(loaded.opacity, 0.85)
        self.assertEqual(loaded.fps, 15.0)

    def test_overlay_is_noop_off_windows(self):
        overlay = DojoDebugOverlay()
        if os.name != "nt":
            self.assertFalse(overlay.start())

    def test_windows_overlay_uses_64_bit_safe_win32_calls(self):
        source = Path(__file__).resolve().parents[1] / "pc_agent" / "kage_pilot" / "dojo_debug_v351.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("win32gui.GetWindowLong", text)
        self.assertIn("win32gui.SetWindowLong", text)
        self.assertIn("SetWindowDisplayAffinity", text)
        self.assertIn("set_affinity.argtypes", text)
        self.assertNotIn("GetWindowLongPtrW", text)

    def test_overlay_never_activates_or_lifts_its_tk_window(self):
        source = Path(__file__).resolve().parents[1] / "pc_agent" / "kage_pilot" / "dojo_debug_v351.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("SW_SHOWNOACTIVATE", text)
        self.assertIn("SWP_NOACTIVATE", text)
        self.assertIn("is_game_window_foreground", text)
        self.assertNotIn("root.deiconify()", text)
        self.assertNotIn("root.lift()", text)
        self.assertNotIn('root.attributes("-topmost"', text)

    def test_overlay_thread_failure_is_reported_without_touching_combat(self):
        source = Path(__file__).resolve().parents[1] / "pc_agent" / "kage_pilot" / "dojo_debug_v351.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("DOJO_DEBUG_OVERLAY_ERROR", text)
        self.assertIn("self.last_error", text)
        self.assertNotIn("ensure_game_window_foreground", text)


if __name__ == "__main__":
    unittest.main()
