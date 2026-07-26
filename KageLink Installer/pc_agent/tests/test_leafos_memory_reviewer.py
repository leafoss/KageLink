from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from leafos_memory_fixtures import write_session_and_bundle
from pc_agent.leafos_memory import LeafOSMemoryReviewer, ReviewerError


class LeafOSMemoryReviewerTests(unittest.TestCase):
    def test_pending_bundle_and_candidates_are_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            sessions = reviewer.list_sessions()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["session_id"], "2026-07-24_001")
            self.assertEqual(sessions[0]["primary_character"], "Matsunaya, Raika")
            self.assertEqual(sessions[0]["pending_count"], 6)

    def test_candidate_can_be_approved_with_evidence_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            entry = reviewer.approve(candidate["candidate_id"])
            self.assertEqual(entry["review_status"], "approved")
            self.assertEqual(entry["source"]["source_message_ids"], [101])
            self.assertEqual(entry["source"]["evidence"][0]["speaker"], "Uzumaki, Urahara")
            self.assertNotIn("review_status", entry["content"])
            self.assertNotIn("review_status", entry["review"]["approved_candidate"])
            memory = json.loads(reviewer.canonical_memory_path.read_text(encoding="utf-8"))
            self.assertEqual(len(memory["entries"]), 1)

    def test_candidate_can_be_edited_and_approved_with_original_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            edited = deepcopy(candidate["candidate"])
            edited["description"] = "Human-corrected description."
            entry = reviewer.approve(candidate["candidate_id"], edited_candidate=edited)
            self.assertEqual(entry["review_status"], "edited_and_approved")
            self.assertNotEqual(entry["review"]["original_candidate"]["description"], entry["review"]["approved_candidate"]["description"])
            self.assertEqual(entry["content"]["description"], "Human-corrected description.")

    def test_candidate_can_be_rejected_and_stays_reviewed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            review = reviewer.reject(candidate["candidate_id"], reason="Not reliable")
            self.assertEqual(review["status"], "rejected")
            self.assertNotIn(candidate["candidate_id"], {item["candidate_id"] for item in reviewer.list_candidates("2026-07-24_001")})
            restarted = LeafOSMemoryReviewer(vault)
            self.assertNotIn(candidate["candidate_id"], {item["candidate_id"] for item in restarted.list_candidates("2026-07-24_001")})

    def test_approved_candidate_does_not_reappear_as_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            reviewer.approve(candidate["candidate_id"])
            self.assertNotIn(candidate["candidate_id"], {item["candidate_id"] for item in reviewer.list_candidates("2026-07-24_001")})

    def test_approve_is_idempotent_and_does_not_duplicate_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            first = reviewer.approve(candidate["candidate_id"])
            second = reviewer.approve(candidate["candidate_id"])
            self.assertEqual(first["memory_id"], second["memory_id"])
            memory = json.loads(reviewer.canonical_memory_path.read_text(encoding="utf-8"))
            ids = [entry["memory_id"] for entry in memory["entries"]]
            self.assertEqual(ids.count(first["memory_id"]), 1)

    def test_primary_character_is_preserved_for_subjective_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            memory_candidate = next(item for item in reviewer.list_candidates("2026-07-24_001") if item["category"] == "leafos_memories")
            entry = reviewer.approve(memory_candidate["candidate_id"])
            self.assertEqual(entry["primary_character"], "Matsunaya, Raika")
            self.assertEqual(entry["epistemic"]["known_by"], "Matsunaya, Raika")
            self.assertEqual(entry["epistemic"]["perspective"], "said")

    def test_memories_from_different_primary_characters_do_not_mix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault, session_id="2026-07-24_001", primary_character="Matsunaya, Raika")
            write_session_and_bundle(vault, session_id="2026-07-24_002", primary_character="Uchiha, Leafos")
            reviewer = LeafOSMemoryReviewer(vault)
            first = next(item for item in reviewer.list_candidates("2026-07-24_001") if item["category"] == "leafos_memories")
            second = next(item for item in reviewer.list_candidates("2026-07-24_002") if item["category"] == "leafos_memories")
            reviewer.approve(first["candidate_id"])
            reviewer.approve(second["candidate_id"])
            memory = json.loads(reviewer.canonical_memory_path.read_text(encoding="utf-8"))
            known_by = {entry["epistemic"]["known_by"] for entry in memory["entries"] if entry["category"] == "memories"}
            self.assertEqual(known_by, {"Matsunaya, Raika", "Uchiha, Leafos"})

    def test_observed_said_and_inferred_remain_distinguishable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            memories = [item for item in reviewer.list_candidates("2026-07-24_001") if item["category"] == "leafos_memories"]
            for item in memories:
                reviewer.approve(item["candidate_id"])
            memory = json.loads(reviewer.canonical_memory_path.read_text(encoding="utf-8"))
            perspectives = {entry["epistemic"]["perspective"] for entry in memory["entries"] if entry["category"] == "memories"}
            self.assertEqual(perspectives, {"observed", "said", "inferred"})

    def test_statement_fact_is_stored_as_claim_with_speaker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            fact = next(item for item in reviewer.list_candidates("2026-07-24_001") if item["category"] == "facts")
            entry = reviewer.approve(fact["candidate_id"])
            self.assertEqual(entry["category"], "lore")
            self.assertEqual(entry["epistemic"]["type"], "claim")
            self.assertEqual(entry["epistemic"]["perspective"], "said")
            self.assertEqual(entry["epistemic"]["speaker"], "Uzumaki, Urahara")

    def test_edit_cannot_change_evidence_or_interpreter_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            edited = deepcopy(candidate["candidate"])
            edited["source_message_ids"] = [102]
            with self.assertRaises(ReviewerError):
                reviewer.approve(candidate["candidate_id"], edited_candidate=edited)
            edited = deepcopy(candidate["candidate"])
            edited["confidence"] = 0.1
            with self.assertRaises(ReviewerError):
                reviewer.approve(candidate["candidate_id"], edited_candidate=edited)

    def test_subjective_memory_requires_primary_character(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault, primary_character="")
            reviewer = LeafOSMemoryReviewer(vault)
            memory_candidate = next(item for item in reviewer.list_candidates("2026-07-24_001") if item["category"] == "leafos_memories")
            with self.assertRaises(ReviewerError):
                reviewer.approve(memory_candidate["candidate_id"])

    def test_corrupted_canonical_memory_blocks_approval_without_modifying_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            reviewer.canonical_memory_path.parent.mkdir(parents=True, exist_ok=True)
            corrupted = '{"type":"leafos_canonical_memory","entries":['
            reviewer.canonical_memory_path.write_text(corrupted, encoding="utf-8")

            with self.assertRaises(ReviewerError):
                reviewer.approve(candidate["candidate_id"])

            self.assertEqual(reviewer.canonical_memory_path.read_text(encoding="utf-8"), corrupted)
            self.assertFalse(reviewer._review_path("2026-07-24_001").exists())

    def test_corrupted_review_state_blocks_processing_without_modifying_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            review_path = reviewer._review_path("2026-07-24_001")
            review_path.parent.mkdir(parents=True, exist_ok=True)
            corrupted = '{"type":"leafos_memory_reviews","reviews":'
            review_path.write_text(corrupted, encoding="utf-8")

            with self.assertRaises(ReviewerError):
                reviewer.list_candidates("2026-07-24_001")

            self.assertEqual(review_path.read_text(encoding="utf-8"), corrupted)
            self.assertFalse(reviewer.canonical_memory_path.exists())

    def test_markdown_is_explicitly_derived_from_memory_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            write_session_and_bundle(vault)
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            reviewer.approve(candidate["candidate_id"])
            text = reviewer.canonical_markdown_path.read_text(encoding="utf-8")
            self.assertIn("DERIVED VIEW / VISUALIZAÇÃO DERIVADA", text)
            self.assertIn("The canonical source is `memory.json`", text)
            self.assertIn("A fonte canônica é `memory.json`", text)
            self.assertIn("## Events / Eventos", text)
            self.assertIn("No approved entries. / Nenhuma entrada aprovada.", text)


if __name__ == "__main__":
    unittest.main()
