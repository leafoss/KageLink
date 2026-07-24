from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pc_agent.history import HistoryStore
from pc_agent.primary_character import (
    get_primary_character,
    resolve_primary_character,
    saved_characters,
    set_primary_character,
)


class PrimaryCharacterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history = HistoryStore(Path(self.temp_dir.name) / "history.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_primary_character_is_persisted(self) -> None:
        result = set_primary_character(
            self.history,
            "Matsunaya Hika",
            changed_at=datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(result["primary_character"], "Matsunaya Hika")
        self.assertEqual(get_primary_character(self.history), "Matsunaya Hika")
        self.assertEqual(saved_characters(self.history), ["Matsunaya Hika"])

    def test_previous_characters_remain_available(self) -> None:
        set_primary_character(
            self.history,
            "Uchiha, Leafos",
            changed_at=datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc),
        )
        result = set_primary_character(
            self.history,
            "Matsunaya Hika",
            changed_at=datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            result["saved_characters"],
            ["Matsunaya Hika", "Uchiha, Leafos"],
        )

    def test_character_can_be_resolved_for_an_older_session(self) -> None:
        set_primary_character(
            self.history,
            "Uchiha, Leafos",
            changed_at=datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc),
        )
        set_primary_character(
            self.history,
            "Matsunaya Hika",
            changed_at=datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            resolve_primary_character(self.history, "2026-07-24T11:30:00+00:00"),
            "Uchiha, Leafos",
        )
        self.assertEqual(
            resolve_primary_character(self.history, "2026-07-24T12:30:00+00:00"),
            "Matsunaya Hika",
        )

    def test_blank_name_clears_current_character_without_losing_history(self) -> None:
        set_primary_character(
            self.history,
            "Matsunaya Hika",
            changed_at=datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
        )
        result = set_primary_character(
            self.history,
            "",
            changed_at=datetime(2026, 7, 24, 13, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(result["primary_character"], "")
        self.assertEqual(saved_characters(self.history), ["Matsunaya Hika"])
        self.assertEqual(
            resolve_primary_character(self.history, "2026-07-24T12:30:00+00:00"),
            "Matsunaya Hika",
        )
        self.assertEqual(
            resolve_primary_character(self.history, "2026-07-24T13:30:00+00:00"),
            "",
        )

    def test_multiline_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            set_primary_character(self.history, "Matsunaya\nHika")


if __name__ == "__main__":
    unittest.main()
