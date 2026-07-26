from __future__ import annotations

import unittest

import unified_entry
from pc_agent import leafos_interpreter_v31 as v31
from pc_agent import leafos_interpreter_v32 as v32


class UnifiedEntryV32RouteTests(unittest.TestCase):
    def test_packaged_entry_uses_v32_and_preserves_v31_module(self) -> None:
        self.assertIs(unified_entry.LeafOSInterpreter, v32.LeafOSInterpreter)
        self.assertIs(unified_entry.OllamaInterpreterProvider, v32.OllamaInterpreterProvider)
        self.assertIs(unified_entry.launcher.LeafOSInterpreter, v32.LeafOSInterpreter)
        self.assertIs(unified_entry.launcher.OllamaInterpreterProvider, v32.OllamaInterpreterProvider)
        self.assertEqual(v31.PROMPT_VERSION, "leafos-interpreter-v3.1")
        self.assertEqual(v32.PROMPT_VERSION, "leafos-interpreter-v3.2")


if __name__ == "__main__":
    unittest.main()
