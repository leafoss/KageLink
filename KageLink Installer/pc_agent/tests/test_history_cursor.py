from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pc_agent.history import HistoryStore


class HistoryCursorTests(unittest.TestCase):
    def test_messages_after_id_returns_both_channels_and_directions_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history = HistoryStore(Path(temp_dir) / "chat_history.db")
            first = history.add("incoming", "OOC hello", channel="ooc")
            second = history.add("outgoing", "IC reply", channel="ic")
            third = history.add("incoming", "IC response", channel="ic")

            rows = history.messages_after_id(first["id"])

            self.assertEqual([row["id"] for row in rows], [second["id"], third["id"]])
            self.assertEqual([row["direction"] for row in rows], ["outgoing", "incoming"])
            self.assertEqual([row["channel"] for row in rows], ["ic", "ic"])

    def test_messages_after_id_does_not_replay_old_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history = HistoryStore(Path(temp_dir) / "chat_history.db")
            first = history.add("incoming", "one", channel="ooc")
            second = history.add("incoming", "two", channel="ic")

            rows = history.messages_after_id(second["id"])

            self.assertEqual(first["id"] + 1, second["id"])
            self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
