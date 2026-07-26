from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pc_agent.history import HistoryStore
from pc_agent.leafos import LeafOSRawExporter
from pc_agent.leafos_lifecycle import LifecycleLeafOSProcessor


class LeafOSCurrentSessionVisibilityTests(unittest.TestCase):
    def test_fresh_history_database_advances_beyond_existing_vault_cursor(self) -> None:
        """Regression for Desktop permanently showing 'No open IC session'.

        A fresh installed Agent can have SQLite IDs starting at 1 while the user's
        existing Vault already has last_processed_id in the thousands. Without
        aligning the AUTOINCREMENT sequence, every new RAW record remains behind
        the Processor cursor and no open session can ever be created.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault = root / "LeafOS-Vault"
            raw = root / "RAW"
            state_path = vault / "80 - Processor" / "processor_state.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(
                json.dumps(
                    {
                        "last_processed_id": 9133,
                        "last_run": "",
                        "raw_source": str(raw),
                        "open_session": None,
                        "session_counters": {},
                    }
                ),
                encoding="utf-8",
            )

            history = HistoryStore(root / "fresh-install" / "chat_history.db")
            processor = LifecycleLeafOSProcessor(
                vault,
                raw,
                primary_character_provider=lambda: "Uchiha, Leafos",
            )

            floor = processor.evidence_id_floor()
            self.assertEqual(floor, 9133)
            self.assertEqual(history.max_message_id(), 0)
            history.ensure_next_message_id_after(floor)

            record = history.add(
                "incoming",
                "Uchiha, Leafos Says: Current session test",
                channel="ic",
            )
            self.assertGreater(record["id"], 9133)

            LeafOSRawExporter(raw).sync(history)
            result = processor.run_once()
            status = processor.lifecycle_status()

            self.assertEqual(result["processed_ic"], 1)
            self.assertTrue(status["open"])
            self.assertEqual(status["primary_character"], "Uchiha, Leafos")
            self.assertEqual(status["message_count"], 1)
            self.assertEqual(status["session_id"], "2026-07-26_001")

    def test_sequence_alignment_never_rewrites_existing_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            history = HistoryStore(root / "chat_history.db")
            first = history.add("incoming", "old", channel="ooc")
            before = history.recent()

            history.ensure_next_message_id_after(5000)

            self.assertEqual(history.recent(), before)
            second = history.add("incoming", "new", channel="ic")
            self.assertEqual(first["id"], 1)
            self.assertGreater(second["id"], 5000)


if __name__ == "__main__":
    unittest.main()
