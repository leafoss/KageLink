from __future__ import annotations

import unittest

from pc_agent.kage_pilot.chat_victory_v03g import RobustChatVictoryWatcher


class FakeSnapshotReader:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.index = 0

    def read_all_current(self):
        if not self.snapshots:
            return {}
        value = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        self.index += 1
        return value


class KagePilotV03GVictoryTests(unittest.TestCase):
    def test_phrase_variants(self):
        self.assertTrue(
            RobustChatVictoryWatcher.is_victory_text(
                "Jounin: Fujita, Isaiah has been Knocked-Out"
            )
        )
        self.assertTrue(RobustChatVictoryWatcher.is_victory_text("X has been knocked out"))
        self.assertFalse(RobustChatVictoryWatcher.is_victory_text("X was knocked down"))

    def test_old_knockout_is_baselined_but_new_second_control_knockout_fires(self):
        reader = FakeSnapshotReader(
            [
                {
                    101: "Old line\nSomeone has been Knocked-Out",
                    202: "Combat starting",
                },
                {
                    101: "Old line\nSomeone has been Knocked-Out",
                    202: "Combat starting\nJounin: Fujita, Isaiah has been Knocked-Out",
                },
            ]
        )
        watcher = RobustChatVictoryWatcher("x", "y", reader=reader)
        watcher.prime()
        signal = watcher.poll()
        self.assertIsNotNone(signal)
        self.assertIn("Fujita, Isaiah", signal.text)
        self.assertEqual(signal.source, "202")

    def test_rewritten_history_with_new_knockout_is_not_discarded(self):
        reader = FakeSnapshotReader(
            [
                {101: "Alpha\nBeta\nCombat continues"},
                {101: "Completely rewritten\nJounin: A has been Knocked-Out"},
            ]
        )
        watcher = RobustChatVictoryWatcher("x", "y", reader=reader)
        watcher.prime()
        signal = watcher.poll()
        self.assertIsNotNone(signal)
        self.assertTrue(signal.resynchronized)

    def test_temporary_empty_read_does_not_erase_baseline(self):
        reader = FakeSnapshotReader(
            [
                {101: "Combat starting"},
                {},
                {101: "Combat starting\nJounin: B has been Knocked-Out"},
            ]
        )
        watcher = RobustChatVictoryWatcher("x", "y", reader=reader)
        watcher.prime()
        self.assertIsNone(watcher.poll())
        signal = watcher.poll()
        self.assertIsNotNone(signal)
        self.assertIn("Jounin: B", signal.text)

    def test_new_control_is_baselined_before_it_can_fire(self):
        reader = FakeSnapshotReader(
            [
                {101: "Combat starting"},
                {
                    101: "Combat starting",
                    303: "Historical line\nOld opponent has been Knocked-Out",
                },
                {
                    101: "Combat starting",
                    303: (
                        "Historical line\nOld opponent has been Knocked-Out\n"
                        "Jounin: New has been Knocked-Out"
                    ),
                },
            ]
        )
        watcher = RobustChatVictoryWatcher("x", "y", reader=reader)
        watcher.prime()
        self.assertIsNone(watcher.poll())
        signal = watcher.poll()
        self.assertIsNotNone(signal)
        self.assertIn("Jounin: New", signal.text)

    def test_repeated_identical_line_with_larger_occurrence_count_fires(self):
        line = "Jounin: Same has been Knocked-Out"
        reader = FakeSnapshotReader(
            [
                {101: f"Old\n{line}"},
                {101: f"Rewritten\n{line}\n{line}"},
            ]
        )
        watcher = RobustChatVictoryWatcher("x", "y", reader=reader)
        watcher.prime()
        signal = watcher.poll()
        self.assertIsNotNone(signal)
        self.assertTrue(signal.resynchronized)
        self.assertEqual(signal.text, line)

    def test_full_loop_defaults_to_five_second_dialog_delay(self):
        import kage_pilot_loop_v03g

        args = kage_pilot_loop_v03g.build_parser().parse_args([])
        self.assertEqual(args.dialog_delay, 5.0)
        self.assertEqual(args.spawn_delay, 5.0)
        self.assertEqual(args.chat_poll_seconds, 0.15)


if __name__ == "__main__":
    unittest.main()
