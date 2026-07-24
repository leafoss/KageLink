from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pc_agent import config as config_module
from pc_agent.chat_channels import (
    IC_CHANNEL,
    OOC_CHANNEL,
    ChatChannelParser,
    ParsedChatMessage,
    drop_replayed_prefix,
    find_new_text,
    unfinished_ic_suffix,
)
from pc_agent.history import HistoryStore


class ChatChannelParserTests(unittest.TestCase):
    def test_ooc_simple(self) -> None:
        parser = ChatChannelParser()
        result = parser.feed("OOC Rafael: hello")
        self.assertEqual(
            [(item.channel, item.text) for item in result],
            [("ooc", "OOC Rafael: hello")],
        )

    def test_exact_says_marker_is_ic(self) -> None:
        parser = ChatChannelParser()
        result = parser.feed("Uchiha, Leafos Says: Hello")
        self.assertEqual(
            [(item.channel, item.text) for item in result],
            [("ic", "Uchiha, Leafos Says: Hello")],
        )

    def test_exact_says_marker_with_markdown_speaker_is_ic(self) -> None:
        parser = ChatChannelParser()
        result = parser.feed("**Anbu** Says: test")
        self.assertEqual(
            [(item.channel, item.text) for item in result],
            [("ic", "**Anbu** Says: test")],
        )

    def test_lowercase_says_marker_remains_ooc(self) -> None:
        parser = ChatChannelParser()
        result = parser.feed("**Anbu** says: test")
        self.assertEqual(
            [(item.channel, item.text) for item in result],
            [("ooc", "**Anbu** says: test")],
        )

    def test_ic_simple(self) -> None:
        parser = ChatChannelParser()
        result = parser.feed("(*Uchiha, Leafos nods.*)")
        self.assertEqual(
            [(item.channel, item.text) for item in result],
            [("ic", "(*Uchiha, Leafos nods.*)")],
        )

    def test_ic_multiline_is_one_message(self) -> None:
        parser = ChatChannelParser()
        text = '(*Uchiha, Leafos lowers his head.\n\n"I understand."\n\nHe takes one step back.*)'
        result = parser.feed(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].channel, "ic")
        self.assertEqual(result[0].text, text)

    def test_fragmented_ic_waits_for_closing_delimiter(self) -> None:
        parser = ChatChannelParser()
        self.assertEqual(parser.feed("(*Uchiha, Leafos looks"), [])
        result = parser.feed(" toward the Hokage.*)")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "(*Uchiha, Leafos looks toward the Hokage.*)")

    def test_mixed_content(self) -> None:
        parser = ChatChannelParser()
        result = parser.feed(
            "Server Information: Test\n"
            "(*Leafos looks around.*)\n"
            "OOC Rafael: test"
        )
        self.assertEqual(
            [(item.channel, item.text) for item in result],
            [
                ("ooc", "Server Information: Test"),
                ("ic", "(*Leafos looks around.*)"),
                ("ooc", "OOC Rafael: test"),
            ],
        )

    def test_mixed_plain_says_and_ooc_content(self) -> None:
        parser = ChatChannelParser()
        result = parser.feed(
            "Server Information: Test\n"
            "**Anbu** Says: ???\n"
            "**Anbu** says: lowercase"
        )
        self.assertEqual(
            [(item.channel, item.text) for item in result],
            [
                ("ooc", "Server Information: Test"),
                ("ic", "**Anbu** Says: ???"),
                ("ooc", "**Anbu** says: lowercase"),
            ],
        )

    def test_two_ic_blocks(self) -> None:
        parser = ChatChannelParser()
        result = parser.feed("(*Leafos looks around.*)(*Leafos walks away.*)")
        self.assertEqual(
            [item.text for item in result],
            ["(*Leafos looks around.*)", "(*Leafos walks away.*)"],
        )

    def test_split_opening_delimiter(self) -> None:
        parser = ChatChannelParser()
        self.assertEqual(parser.feed("("), [])
        result = parser.feed("*Leafos nods.*)")
        self.assertEqual(
            [(item.channel, item.text) for item in result],
            [("ic", "(*Leafos nods.*)")],
        )

    def test_find_new_text_preserves_multiline(self) -> None:
        previous = "Server line"
        current = "Server line\n(*Leafos\n\nwaits.*)"
        addition, resync = find_new_text(previous, current)
        self.assertFalse(resync)
        self.assertEqual(addition, "\n(*Leafos\n\nwaits.*)")

    def test_resynchronization_drops_only_replayed_message_prefix(self) -> None:
        parsed = [
            ParsedChatMessage(OOC_CHANNEL, "Server Information: Test"),
            ParsedChatMessage(IC_CHANNEL, "(*Leafos looks around.*)"),
            ParsedChatMessage(OOC_CHANNEL, "OOC Rafael: new"),
        ]
        recent = [
            (OOC_CHANNEL, "older"),
            (OOC_CHANNEL, "Server Information: Test"),
            (IC_CHANNEL, "(*Leafos looks around.*)"),
        ]

        remaining = drop_replayed_prefix(parsed, recent)

        self.assertEqual(
            remaining,
            [ParsedChatMessage(OOC_CHANNEL, "OOC Rafael: new")],
        )

    def test_resynchronization_keeps_unrelated_messages(self) -> None:
        parsed = [ParsedChatMessage(OOC_CHANNEL, "brand new history")]
        recent = [(OOC_CHANNEL, "old history")]
        self.assertEqual(drop_replayed_prefix(parsed, recent), parsed)

    def test_truncated_history_overlap_preserves_separator(self) -> None:
        previous = "old line\nshared line"
        current = "shared line\n(*Leafos nods.*)"
        addition, resync = find_new_text(previous, current)
        self.assertFalse(resync)
        self.assertEqual(addition, "\n(*Leafos nods.*)")

    def test_fragmented_ic_preserves_new_paragraphs(self) -> None:
        previous = "(*Leafos lowers his head."
        current = f'{previous}\n\n"I understand."\n\nHe steps back.*)'
        parser = ChatChannelParser(previous)
        addition, resync = find_new_text(previous, current)
        self.assertFalse(resync)
        result = parser.feed(addition)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, current)

    def test_unfinished_suffix_can_be_recovered_during_upgrade(self) -> None:
        text = "OOC line\n(*Leafos begins\n\na long action"
        self.assertEqual(
            unfinished_ic_suffix(text),
            "(*Leafos begins\n\na long action",
        )
        self.assertEqual(unfinished_ic_suffix("(*Leafos nods.*)"), "")

    def test_pending_ic_can_resume_after_restart(self) -> None:
        snapshot = "Server line\n(*Leafos begins"
        parser = ChatChannelParser("(*Leafos begins")
        addition, resync = find_new_text(snapshot, f"{snapshot} speaking.*)")
        self.assertFalse(resync)
        result = parser.feed(addition)
        self.assertEqual(
            [(item.channel, item.text) for item in result],
            [("ic", "(*Leafos begins speaking.*)")],
        )


class HistoryMigrationTests(unittest.TestCase):
    def test_legacy_database_adds_channel_without_losing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "history.db"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    """
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        text TEXT NOT NULL,
                        resynchronized INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO messages(timestamp, direction, text, resynchronized) VALUES (?, ?, ?, ?)",
                    ("2026-07-15T00:00:00+00:00", "incoming", "OOC Test", 0),
                )
                connection.commit()

            store = HistoryStore(database)
            rows = store.recent()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["channel"], "ooc")
            self.assertEqual(rows[0]["text"], "OOC Test")

            added = store.add("incoming", "(*Leafos nods.*)", channel="ic")
            self.assertEqual(added["channel"], "ic")

    def test_monitor_state_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "history.db"
            store = HistoryStore(database)
            store.save_monitor_state("line\n(*Leafos", "(*Leafos")

            reopened = HistoryStore(database)
            snapshot, pending = reopened.monitor_state()
            self.assertEqual(snapshot, "line\n(*Leafos")
            self.assertEqual(pending, "(*Leafos")


class ConfigMigrationTests(unittest.TestCase):
    def test_legacy_ooc_preference_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "access_token": "x" * 32,
                        "input_control": {
                            "preferred_width": 777,
                            "preferred_height": 44,
                        },
                        "server": {"host": "0.0.0.0", "port": 8765},
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(config_module, "PROJECT_DIR", root), patch.object(
                config_module, "CONFIG_PATH", config_path
            ):
                raw = config_module.ensure_config()

            self.assertEqual(raw["input_controls"]["ooc"]["preferred_width"], 777)
            self.assertEqual(raw["input_controls"]["ooc"]["preferred_height"], 44)
            self.assertEqual(raw["input_controls"]["ic"]["candidate_index"], 2)


if __name__ == "__main__":
    unittest.main()
