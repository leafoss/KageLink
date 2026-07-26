from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pc_agent.history import HistoryStore
from pc_agent.leafos import LeafOSRawExporter
from pc_agent.leafos_lifecycle import LifecycleLeafOSProcessor


class LeafOSLifecycleTests(unittest.TestCase):
    def _setup(self, root: Path):
        vault = root / "LeafOS-Vault"
        raw = root / "RAW"
        vault.mkdir(parents=True)
        history = HistoryStore(root / "history.db")
        exporter = LeafOSRawExporter(raw)
        return vault, raw, history, exporter

    def test_new_session_is_blocked_until_primary_character_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault, raw, history, exporter = self._setup(root)
            row = history.add("incoming", "Uchiha, Leafos Says: Test", channel="ic")
            exporter.sync(history)
            character = {"value": ""}
            processor = LifecycleLeafOSProcessor(
                vault,
                raw,
                primary_character_provider=lambda: character["value"],
            )

            blocked = processor.run_once()
            self.assertEqual(blocked["processed_ic"], 0)
            self.assertEqual(blocked["blocked_no_primary_character"], 1)
            state = json.loads(
                (vault / "80 - Processor" / "processor_state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["last_processed_id"], 0)
            self.assertIsNone(state["open_session"])

            character["value"] = "Uchiha, Leafos"
            processed = processor.run_once()
            self.assertEqual(processed["processed_ic"], 1)
            self.assertTrue(processor.has_open_session())
            self.assertGreaterEqual(row["id"], 1)

    def test_manual_finalize_stamps_character_reason_and_clean_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault, raw, history, exporter = self._setup(root)
            history.add("incoming", "Uchiha, Leafos Says: Hold.", channel="ic")
            exporter.sync(history)
            processor = LifecycleLeafOSProcessor(
                vault,
                raw,
                primary_character_provider=lambda: "Uchiha, Leafos",
            )
            processor.run_once()

            result = processor.finalize_open_session("manual")

            self.assertTrue(result["closed"])
            self.assertEqual(result["close_reason"], "manual")
            self.assertFalse(processor.has_open_session())
            session_path = next((vault / "80 - Processor" / "Sessions").glob("*.json"))
            session = json.loads(session_path.read_text(encoding="utf-8"))
            self.assertEqual(session["primary_character"], "Uchiha, Leafos")
            self.assertEqual(session["close_reason"], "manual")
            self.assertTrue(session["closed_cleanly"])
            self.assertTrue(session["closed_at"])
            inbox_path = next((vault / "70 - LeafOS Inbox" / "Sessions").glob("*.json"))
            inbox = json.loads(inbox_path.read_text(encoding="utf-8"))
            self.assertEqual(inbox["primary_character"], "Uchiha, Leafos")
            self.assertEqual(inbox["close_reason"], "manual")

    def test_recovery_closes_leftover_session_as_unclean(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault, raw, history, exporter = self._setup(root)
            history.add("incoming", "Leafos Says: Before crash", channel="ic")
            exporter.sync(history)
            first = LifecycleLeafOSProcessor(
                vault,
                raw,
                primary_character_provider=lambda: "Uchiha, Leafos",
            )
            first.run_once()
            self.assertTrue(first.has_open_session())

            restarted = LifecycleLeafOSProcessor(
                vault,
                raw,
                primary_character_provider=lambda: "Uchiha, Leafos",
            )
            result = restarted.recover_unclean_session()

            self.assertTrue(result["closed"])
            session_path = next((vault / "80 - Processor" / "Sessions").glob("*.json"))
            session = json.loads(session_path.read_text(encoding="utf-8"))
            self.assertEqual(session["close_reason"], "unclean_shutdown_recovery")
            self.assertFalse(session["closed_cleanly"])

    def test_idle_timeout_remains_automatic_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault, raw, history, exporter = self._setup(root)
            history.add("incoming", "Leafos Says: Idle", channel="ic")
            exporter.sync(history)
            now = datetime.now(timezone.utc)
            processor = LifecycleLeafOSProcessor(
                vault,
                raw,
                session_idle_seconds=60,
                primary_character_provider=lambda: "Uchiha, Leafos",
            )
            processor.run_once(now=now)
            result = processor.run_once(now=now + timedelta(minutes=2))
            self.assertEqual(result["closed_sessions"], 1)
            session_path = next((vault / "80 - Processor" / "Sessions").glob("*.json"))
            session = json.loads(session_path.read_text(encoding="utf-8"))
            self.assertEqual(session["close_reason"], "idle_timeout")


if __name__ == "__main__":
    unittest.main()
