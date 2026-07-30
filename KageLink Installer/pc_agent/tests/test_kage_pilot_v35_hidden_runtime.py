from __future__ import annotations

import sys
import unittest
from unittest import mock

import kage_pilot_loop_v03j as loop_v03j


class KagePilotV35HiddenRuntimeTests(unittest.TestCase):
    def test_packaged_round_uses_no_window_flag_on_windows(self):
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch(
            "kage_pilot_loop_v03j.os.name", "nt"
        ), mock.patch.object(
            loop_v03j.subprocess,
            "CREATE_NO_WINDOW",
            0x08000000,
            create=True,
        ):
            self.assertEqual(loop_v03j._round_creationflags(), 0x08000000)

    def test_source_round_keeps_normal_console_semantics(self):
        with mock.patch.object(sys, "frozen", False, create=True), mock.patch(
            "kage_pilot_loop_v03j.os.name", "nt"
        ):
            self.assertEqual(loop_v03j._round_creationflags(), 0)


if __name__ == "__main__":
    unittest.main()
