from __future__ import annotations

import re
import unittest

# Keep this test Win32-independent so it can run in every Python CI job.
AMBUSH = re.compile(
    r"^\s*(?P<clan>[A-Za-z][A-Za-z-]*),\s*(?P<name>.+?)\s+"
    r"dashes\s+from\s+above\s+the\s+trees\s+as\s+they\s+prepare\s+their\s+ambush\.\s*$",
    re.IGNORECASE,
)


class HuntingRuleTests(unittest.TestCase):
    def test_exact_ambush_format_matches_and_extracts_identity(self):
        match = AMBUSH.match(
            "Inuzuka, Sadao dashes from above the trees as they prepare their ambush."
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group("clan"), "Inuzuka")
        self.assertEqual(match.group("name"), "Sadao")

    def test_old_generic_spawn_phrase_does_not_match(self):
        self.assertIsNone(AMBUSH.match("Inuzuka, Sadao has appeared"))


if __name__ == "__main__":
    unittest.main()
