from __future__ import annotations

import unittest
from pathlib import Path

import unified_launcher


class UnifiedLocalizationContractTests(unittest.TestCase):
    def test_catalogs_have_identical_keys(self) -> None:
        self.assertEqual(
            set(unified_launcher.TEXT["pt-BR"]),
            set(unified_launcher.TEXT["en-US"]),
        )

    def test_new_unified_ui_has_no_known_mixed_or_single_language_literals(self) -> None:
        root = Path(__file__).resolve().parents[1]
        launcher_source = (root / "unified_launcher.py").read_text(encoding="utf-8")
        entry_source = (root / "unified_entry.py").read_text(encoding="utf-8")
        source = launcher_source + "\n" + entry_source
        forbidden = (
            "Porta inválida / Invalid port",
            "Vault required / Vault obrigatória",
            "Selecione a Vault LeafOS / Select the LeafOS Vault",
            "KageLink creates the access key automatically and starts the secure Cloudflare route by default.",
            "A secure random access key will be created automatically. / Uma chave segura será criada automaticamente.",
            "KageLink.exe will own Agent, session lifecycle, Interpreter and Memory Reviewer. No PowerShell is required for normal use.",
            "KageLink keeps chat/GAME/STATS isolated from LeafOS. Changes to network or LeafOS paths restart the Agent safely.",
            'for title, var in (("AGENT", self.agent_var)',
            'if self.lang == "pt-BR":',
        )
        for literal in forbidden:
            with self.subTest(literal=literal):
                self.assertNotIn(literal, source)

    def test_audited_strings_resolve_in_both_languages(self) -> None:
        keys = (
            "connection_help",
            "access_key_help",
            "finish_help",
            "state_on",
            "state_off",
            "ollama_model",
            "invalid_port",
            "select_vault",
            "settings_help",
            "operation_failed",
            "interpreter_failed",
            "interpreter_preserved",
        )
        for key in keys:
            with self.subTest(key=key):
                pt = unified_launcher._t("pt-BR", key, error="X") if key == "operation_failed" else unified_launcher._t("pt-BR", key)
                en = unified_launcher._t("en-US", key, error="X") if key == "operation_failed" else unified_launcher._t("en-US", key)
                self.assertTrue(pt.strip())
                self.assertTrue(en.strip())
                self.assertNotEqual(pt, key)
                self.assertNotEqual(en, key)


if __name__ == "__main__":
    unittest.main()
