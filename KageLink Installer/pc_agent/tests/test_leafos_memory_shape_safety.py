from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pc_agent.leafos_memory import LeafOSMemoryReviewer
from pc_agent.leafos_memory_support import ReviewerError


class LeafOSMemoryShapeSafetyTests(unittest.TestCase):
    def test_wrong_entries_container_blocks_without_modifying_canonical_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            path = vault / "60 - Canonical Memory" / "memory.json"
            path.parent.mkdir(parents=True)
            original = '{"type":"leafos_canonical_memory","entries":"oops"}\n'
            path.write_text(original, encoding="utf-8")

            reviewer = LeafOSMemoryReviewer(vault)
            with self.assertRaisesRegex(ReviewerError, "INVALID_JSON_FIELD_TYPE"):
                reviewer._load_memory()

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_wrong_reviews_container_blocks_without_modifying_review_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            path = vault / "80 - Memory Reviewer" / "Reviews" / "s1.json"
            path.parent.mkdir(parents=True)
            original = '{"type":"leafos_memory_reviews","session_id":"s1","reviews":[]}\n'
            path.write_text(original, encoding="utf-8")

            reviewer = LeafOSMemoryReviewer(vault)
            with self.assertRaisesRegex(ReviewerError, "INVALID_JSON_FIELD_TYPE"):
                reviewer._load_reviews("s1")

            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
