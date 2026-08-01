from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pc_agent.kage_pilot.dojo_journal_v351 import (
    DojoSessionJournal,
    latest_dojo_error,
)


class DojoSessionJournalV351Tests(unittest.TestCase):
    def test_success_removes_active_file_and_leaves_no_error(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = DojoSessionJournal(root=directory, session_id="success")
            active = journal.active_path
            journal.write("PHASE", "combat")
            result = journal.finalize(success=True, return_code=0)

            self.assertIsNone(result)
            self.assertFalse(active.exists())
            self.assertEqual(list(Path(directory).glob("*.txt")), [])

    def test_error_preserves_utf8_log_with_timestamp_category_and_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = DojoSessionJournal(
                root=directory,
                session_id="failure",
                metadata={"rounds": 65, "mode": "64×64"},
            )
            journal.write("PHASE", "post_combat", round=23)
            journal.write("POSITION", "updated", x=20, y=10, confidence=0.93)
            journal.write("RELOCALIZATION", "matched", x=20, y=10, score=0.93)
            journal.write("RETURN", "failed", reason="blocked")
            result = journal.finalize(
                success=False,
                error="TRAINER_RETURN_FAILED",
                return_code=1,
                summary={"completed_rounds": 22},
            )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertTrue(result.name.startswith("dojo_error_"))
            text = result.read_text(encoding="utf-8")
            self.assertIn("[SESSION] started", text)
            self.assertIn("[CONFIG]", text)
            self.assertIn("64×64", text)
            self.assertIn("[PHASE]", text)
            self.assertIn("[POSITION]", text)
            self.assertIn("[RELOCALIZATION]", text)
            self.assertIn("[RETURN]", text)
            self.assertIn("[ERROR] TRAINER_RETURN_FAILED", text)
            self.assertRegex(text.splitlines()[0], r"^\d{4}-\d{2}-\d{2}T.* \[SESSION\]")

            status = latest_dojo_error(directory)
            self.assertTrue(status.exists)
            self.assertEqual(status.kind, "error")
            self.assertEqual(Path(status.path), result.resolve())

    def test_exception_writes_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = DojoSessionJournal(root=directory, session_id="trace")
            try:
                raise RuntimeError("falha física")
            except RuntimeError as error:
                journal.write_exception(error)
            result = journal.finalize(success=False, error="RUNTIME_FAILURE")

            assert result is not None
            text = result.read_text(encoding="utf-8")
            self.assertIn("[TRACEBACK]", text)
            self.assertIn("RuntimeError: falha física", text)

    def test_abandoned_active_file_is_recovered_once(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = DojoSessionJournal(root=directory, session_id="abandoned")
            active = journal.active_path
            journal.write("PHASE", "combat")
            journal._handle.close()  # simulate process death without finalize
            journal._closed = True

            recovered = DojoSessionJournal.recover_abandoned(directory)
            self.assertEqual(len(recovered), 1)
            self.assertFalse(active.exists())
            self.assertTrue(recovered[0].name.startswith("dojo_incomplete_"))
            text = recovered[0].read_text(encoding="utf-8")
            self.assertIn("UNCLEAN_PREVIOUS_SHUTDOWN", text)
            self.assertEqual(DojoSessionJournal.recover_abandoned(directory), [])

    def test_multiple_sessions_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            first = DojoSessionJournal(root=directory, session_id="one")
            second = DojoSessionJournal(root=directory, session_id="two")
            first_path = first.finalize(success=False, error="FIRST")
            second_path = second.finalize(success=False, error="SECOND")
            self.assertIsNotNone(first_path)
            self.assertIsNotNone(second_path)
            self.assertNotEqual(first_path, second_path)
            self.assertEqual(len(list(Path(directory).glob("dojo_error_*.txt"))), 2)

    def test_logging_failure_is_non_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = DojoSessionJournal(root=directory, session_id="safe")
            journal._handle.close()
            journal.write("F12", "emergency_stop")
            self.assertFalse(journal.healthy)
            self.assertTrue(journal.last_error)


if __name__ == "__main__":
    unittest.main()
