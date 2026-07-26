from __future__ import annotations

import unittest

import unified_entry
from pc_agent import leafos_interpreter_v31 as v31
from pc_agent import leafos_interpreter_v32 as v32
from pc_agent import leafos_interpreter_v321 as v321


class UnifiedEntryV321RouteTests(unittest.TestCase):
    def test_packaged_entry_uses_v321_and_preserves_v31_v32_modules(self) -> None:
        self.assertIs(unified_entry.LeafOSInterpreter, v321.LeafOSInterpreter)
        self.assertIs(unified_entry.OllamaInterpreterProvider, v321.OllamaInterpreterProvider)
        self.assertIs(unified_entry.launcher.LeafOSInterpreter, v321.LeafOSInterpreter)
        self.assertIs(unified_entry.launcher.OllamaInterpreterProvider, v321.OllamaInterpreterProvider)
        self.assertEqual(v31.PROMPT_VERSION, "leafos-interpreter-v3.1")
        self.assertEqual(v32.PROMPT_VERSION, "leafos-interpreter-v3.2")
        self.assertEqual(v321.PROMPT_VERSION, "leafos-interpreter-v3.2.1")
        self.assertTrue(issubclass(v321.LeafOSInterpreter, v32.LeafOSInterpreter))


if __name__ == "__main__":
    unittest.main()
