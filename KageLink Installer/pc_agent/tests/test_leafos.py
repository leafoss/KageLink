from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pc_agent.history import HistoryStore
from pc_agent.leafos import (
    RAW_STATE_KEY,
    LeafOSProcessor,
    LeafOSRawExporter,
    RawRecordReader,
)


class LeafOSRawExporterTests(unittest.TestCase):
    def _paths(self, root: Path) -> tuple[Path, Path, HistoryStore]:
        vault = root / "LeafOS-Vault"
        raw = root / "RAW Output"
        vault.mkdir(parents=True)
        history = HistoryStore(root / "history.db")
        return vault, raw, history

    def test_first_ic_creates_file_second_appends_and_preserves_old_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, raw, history = self._paths(root)
            first = history.add("incoming", "Leafos says: First", channel="ic")
            exporter = LeafOSRawExporter(raw)
            self.assertEqual(exporter.sync(history)["ic"], 1)
            raw_file = next((raw / "IC").glob("*.md"))
            first_content = raw_file.read_text(encoding="utf-8")
            self.assertIn("Leafos says: First", first_content)
            self.assertIn(f'"id":{first["id"]}', first_content)

            second = history.add("incoming", "Leafos says: Second", channel="ic")
            self.assertEqual(exporter.sync(history)["ic"], 1)
            content = raw_file.read_text(encoding="utf-8")
            self.assertIn("Leafos says: First", content)
            self.assertIn("Leafos says: Second", content)
            self.assertIn(f'"id":{second["id"]}', content)

    def test_restart_does_not_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, raw, history = self._paths(root)
            history.add("incoming", "Leafos says: Once", channel="ic")
            LeafOSRawExporter(raw).sync(history)
            LeafOSRawExporter(raw).sync(HistoryStore(root / "history.db"))
            raw_file = next((raw / "IC").glob("*.md"))
            self.assertEqual(raw_file.read_text(encoding="utf-8").count("Leafos says: Once"), 1)

    def test_identical_text_with_different_ids_is_preserved_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, raw, history = self._paths(root)
            history.add("incoming", "Leafos says: Wait.", channel="ic")
            history.add("incoming", "Leafos says: Wait.", channel="ic")
            LeafOSRawExporter(raw).sync(history)
            raw_file = next((raw / "IC").glob("*.md"))
            self.assertEqual(raw_file.read_text(encoding="utf-8").count("Leafos says: Wait."), 2)

    def test_ic_enabled_ooc_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, raw, history = self._paths(root)
            history.add("incoming", "OOC line", channel="ooc")
            history.add("incoming", "Leafos says: IC", channel="ic")
            counts = LeafOSRawExporter(raw).sync(history)
            self.assertEqual(counts, {"ic": 1, "ooc": 0})
            self.assertEqual(list((raw / "OOC").glob("*.md")), [])

    def test_ooc_can_be_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, raw, history = self._paths(root)
            history.add("incoming", "OOC Rafael: hello", channel="ooc")
            counts = LeafOSRawExporter(raw, export_ooc=True).sync(history)
            self.assertEqual(counts["ooc"], 1)
            self.assertTrue(list((raw / "OOC").glob("*.md")))

    def test_custom_path_spaces_and_missing_directories_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            history = HistoryStore(root / "history.db")
            history.add("incoming", "Leafos says: Path", channel="ic")
            raw = root / "folder with spaces" / "nested RAW"
            LeafOSRawExporter(raw).sync(history)
            self.assertTrue(raw.is_dir())
            self.assertTrue(list((raw / "IC").glob("*.md")))

    def test_path_change_keeps_old_raw_and_does_not_reexport_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            history = HistoryStore(root / "history.db")
            raw_a = root / "RAW-A"
            raw_b = root / "RAW-B"
            history.add("incoming", "Leafos says: Old", channel="ic")
            LeafOSRawExporter(raw_a).sync(history)
            old_file = next((raw_a / "IC").glob("*.md"))
            old_content = old_file.read_text(encoding="utf-8")

            history.add("incoming", "Leafos says: New", channel="ic")
            LeafOSRawExporter(raw_b).sync(history)
            new_file = next((raw_b / "IC").glob("*.md"))
            new_content = new_file.read_text(encoding="utf-8")
            self.assertEqual(old_file.read_text(encoding="utf-8"), old_content)
            self.assertNotIn("Leafos says: Old", new_content)
            self.assertIn("Leafos says: New", new_content)

    def test_write_error_does_not_advance_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, raw, history = self._paths(root)
            row = history.add("incoming", "Leafos says: Fail", channel="ic")
            exporter = LeafOSRawExporter(raw)
            with patch.object(exporter, "append_record", side_effect=OSError("disk full")):
                self.assertEqual(exporter.sync(history), {"ic": 0, "ooc": 0})
            self.assertLess(int(history.get_runtime_state(RAW_STATE_KEY, "0")), row["id"])

    def test_raw_reader_recovers_original_text_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, raw, history = self._paths(root)
            text = "(*Uchiha, Leafos turns toward the gate.*)"
            row = history.add("incoming", text, channel="ic")
            LeafOSRawExporter(raw).sync(history)
            records = RawRecordReader(raw).after_id(0)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["id"], row["id"])
            self.assertEqual(records[0]["text"], text)
            self.assertEqual(records[0]["channel"], "ic")


class LeafOSProcessorTests(unittest.TestCase):
    def _setup(self, root: Path) -> tuple[Path, Path, HistoryStore, LeafOSRawExporter]:
        vault = root / "LeafOS-Vault"
        raw = root / "External RAW"
        vault.mkdir()
        history = HistoryStore(root / "history.db")
        return vault, raw, history, LeafOSRawExporter(raw)

    def test_processes_only_new_records_persists_state_and_participants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault, raw, history, exporter = self._setup(root)
            row = history.add("incoming", "Uchiha, Leafos says: Move.", channel="ic")
            exporter.sync(history)
            processor = LeafOSProcessor(vault, raw)
            first = processor.run_once()
            second = processor.run_once()
            self.assertEqual(first["processed_ic"], 1)
            self.assertEqual(second["processed_ic"], 0)
            state = json.loads((vault / "80 - Processor" / "processor_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["last_processed_id"], row["id"])
            self.assertEqual(Path(state["raw_source"]), raw)
            discovered = json.loads((vault / "80 - Processor" / "Participants" / "discovered.json").read_text(encoding="utf-8"))
            self.assertIn("Uchiha, Leafos", discovered["participants"])
            self.assertTrue((vault / "70 - LeafOS Inbox" / "New Characters" / "Uchiha, Leafos.json").exists())

    def test_session_closes_after_15_minutes_and_restart_does_not_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault, raw, history, exporter = self._setup(root)
            row = history.add("incoming", "Leafos says: Hold.", channel="ic")
            start = datetime(2026, 7, 24, 20, 0, tzinfo=timezone.utc)
            with sqlite3.connect(root / "history.db") as connection:
                connection.execute("UPDATE messages SET timestamp = ? WHERE id = ?", (start.isoformat(), row["id"]))
                connection.commit()
            exporter.sync(history)
            processor = LeafOSProcessor(vault, raw, session_idle_seconds=900)
            processor.run_once(now=start + timedelta(minutes=1))
            closed = processor.run_once(now=start + timedelta(minutes=16))
            self.assertEqual(closed["closed_sessions"], 1)
            sessions = list((vault / "80 - Processor" / "Sessions").glob("*.json"))
            inbox = list((vault / "70 - LeafOS Inbox" / "Sessions").glob("*.json"))
            self.assertEqual(len(sessions), 1)
            self.assertEqual(len(inbox), 1)
            self.assertEqual(LeafOSProcessor(vault, raw).run_once()["processed_ic"], 0)
            self.assertEqual(len(list((vault / "80 - Processor" / "Sessions").glob("*.json"))), 1)

    def test_gap_splits_sessions_and_session_has_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault, raw, history, exporter = self._setup(root)
            first = history.add("incoming", "Leafos says: One", channel="ic")
            second = history.add("incoming", "Urahara says: Two", channel="ic")
            start = datetime(2026, 7, 24, 20, 0, tzinfo=timezone.utc)
            with sqlite3.connect(root / "history.db") as connection:
                connection.execute("UPDATE messages SET timestamp = ? WHERE id = ?", (start.isoformat(), first["id"]))
                connection.execute("UPDATE messages SET timestamp = ? WHERE id = ?", ((start + timedelta(minutes=16)).isoformat(), second["id"]))
                connection.commit()
            exporter.sync(history)
            result = LeafOSProcessor(vault, raw).run_once(now=start + timedelta(minutes=17))
            self.assertEqual(result["processed_ic"], 2)
            self.assertEqual(result["closed_sessions"], 1)
            session_path = next((vault / "80 - Processor" / "Sessions").glob("*.json"))
            payload = json.loads(session_path.read_text(encoding="utf-8"))
            for key in ("session_id", "started_at", "ended_at", "participants", "message_count", "message_ids", "raw_sources", "messages"):
                self.assertIn(key, payload)

    def test_processor_follows_configured_raw_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault = root / "LeafOS-Vault"
            vault.mkdir()
            history = HistoryStore(root / "history.db")
            raw_a = root / "A"
            raw_b = root / "B"
            history.add("incoming", "Leafos says: A", channel="ic")
            LeafOSRawExporter(raw_a).sync(history)
            processor = LeafOSProcessor(vault, raw_a)
            self.assertEqual(processor.run_once()["processed_ic"], 1)

            history.add("incoming", "Urahara says: B", channel="ic")
            LeafOSRawExporter(raw_b).sync(history)
            switched = LeafOSProcessor(vault, raw_b)
            self.assertEqual(switched.run_once()["processed_ic"], 1)
            state = json.loads((vault / "80 - Processor" / "processor_state.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(state["raw_source"]), raw_b)

    def test_processor_failure_is_local_to_processor_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault = root / "LeafOS-Vault"
            vault.mkdir()
            history = HistoryStore(root / "history.db")
            row = history.add("incoming", "Leafos says: Chat survives", channel="ic")
            with self.assertRaises(FileNotFoundError):
                LeafOSProcessor(vault, root / "missing-raw").run_once()
            self.assertEqual(history.recent()[-1]["id"], row["id"])


if __name__ == "__main__":
    unittest.main()
