from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from leafos_memory_fixtures import sha256, write_session_and_bundle
from pc_agent.leafos_memory import EvidenceError, LeafOSMemoryReviewer


class LeafOSMemoryEvidenceTests(unittest.TestCase):
    def test_invalid_evidence_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            _, _, bundle_path = write_session_and_bundle(vault)
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            bundle["events"][0]["source_message_ids"] = [999]
            bundle["message_ids"].append(999)
            bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            with self.assertRaises(EvidenceError):
                reviewer.approve(candidate["candidate_id"])
            self.assertFalse(reviewer.canonical_memory_path.exists())

    def test_missing_raw_marker_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            raw_path, _, _ = write_session_and_bundle(vault)
            raw_path.write_text("<!-- empty raw -->\n", encoding="utf-8")
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            with self.assertRaises(EvidenceError):
                reviewer.approve(candidate["candidate_id"])

    def test_raw_content_mismatch_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            raw_path, _, _ = write_session_and_bundle(vault)
            text = raw_path.read_text(encoding="utf-8")
            raw_path.write_text(text.replace("The Mizukage is heading east.", "Different RAW text."), encoding="utf-8")
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            with self.assertRaises(EvidenceError):
                reviewer.approve(candidate["candidate_id"])

    def test_invalid_evidence_candidate_can_still_be_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            _, _, bundle_path = write_session_and_bundle(vault)
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            bundle["events"][0]["source_message_ids"] = [999]
            bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            reviewer = LeafOSMemoryReviewer(vault)
            candidate = reviewer.list_candidates("2026-07-24_001")[0]
            review = reviewer.reject(candidate["candidate_id"], reason="Broken evidence")
            self.assertEqual(review["status"], "rejected")
            self.assertFalse(review["evidence_valid"])
            self.assertTrue(review["evidence_error"])
            self.assertNotIn(candidate["candidate_id"], {item["candidate_id"] for item in reviewer.list_candidates("2026-07-24_001")})

    def test_raw_processor_and_bundle_are_never_modified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            raw_path, session_path, bundle_path = write_session_and_bundle(vault)
            before = {path: sha256(path) for path in (raw_path, session_path, bundle_path)}
            reviewer = LeafOSMemoryReviewer(vault)
            candidates = reviewer.list_candidates("2026-07-24_001")
            reviewer.approve(candidates[0]["candidate_id"])
            reviewer.reject(candidates[1]["candidate_id"])
            after = {path: sha256(path) for path in (raw_path, session_path, bundle_path)}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
