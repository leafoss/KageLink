from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

from pc_agent.leafos_memory_support import MEMORY_MARKDOWN_TEXT, render_memory_markdown

PC_AGENT_ROOT = Path(__file__).resolve().parents[1]
REVIEWER_UI = PC_AGENT_ROOT / "pc_agent" / "leafos_memory_reviewer.py"
LAUNCHER = PC_AGENT_ROOT / "kagelink_launcher.py"


def literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"Assignment {name} not found in {path}")


def method_source(path: Path, class_name: str, method_name: str) -> str:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    segment = ast.get_source_segment(source, item)
                    if segment is not None:
                        return segment
    raise AssertionError(f"Method {class_name}.{method_name} not found")


class LocalizationContractTests(unittest.TestCase):
    def assert_language_parity(self, catalog: dict, label: str) -> None:
        self.assertEqual(set(catalog), {"pt-BR", "en-US"}, label)
        self.assertEqual(set(catalog["pt-BR"]), set(catalog["en-US"]), label)

    def test_reviewer_visible_text_has_parity(self) -> None:
        self.assert_language_parity(literal_assignment(REVIEWER_UI, "TEXT"), "Reviewer TEXT")

    def test_reviewer_error_catalog_has_parity(self) -> None:
        self.assert_language_parity(literal_assignment(REVIEWER_UI, "REVIEWER_ERROR_TEXT"), "Reviewer errors")

    def test_reviewer_cli_catalog_has_parity(self) -> None:
        self.assert_language_parity(literal_assignment(REVIEWER_UI, "CLI_TEXT"), "Reviewer CLI")

    def test_pc_agent_visible_text_has_parity(self) -> None:
        self.assert_language_parity(literal_assignment(LAUNCHER, "TEXT"), "PC Agent TEXT")

    def test_memory_markdown_catalog_has_parity(self) -> None:
        self.assert_language_parity(MEMORY_MARKDOWN_TEXT, "Canonical-memory Markdown")

    def test_reviewer_does_not_show_raw_controlled_errors_directly(self) -> None:
        source = REVIEWER_UI.read_text(encoding="utf-8-sig")
        self.assertNotIn('messagebox.showerror("LeafOS Reviewer",str(error),parent=self)', source)
        self.assertNotIn("\\n\\n{error}\\n\\n", source)
        self.assertIn("_reviewer_error_message", source)

    def test_leafos_settings_do_not_use_old_bilingual_hardcoded_labels(self) -> None:
        source = method_source(LAUNCHER, "KageLinkAgentUI", "open_settings")
        for old_text in (
            "Idioma / Language", "Porta / Port", "Gerar nova chave / Generate new key",
            "Ativar integração LeafOS / Enable LeafOS integration", "Procurar / Browse",
            "Pasta RAW / RAW folder", "Exportar IC / Export IC", "Exportar OOC / Export OOC",
            "Porta inválida / Invalid port", "Salvar / Save",
        ):
            self.assertNotIn(old_text, source)

    def test_generated_memory_markdown_is_explicitly_bilingual(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "MEMORY.md"
            render_memory_markdown(path, {"updated_at": "2026-07-25T00:00:00+00:00", "entries": []})
            text = path.read_text(encoding="utf-8")
        self.assertIn("DERIVED VIEW / VISUALIZAÇÃO DERIVADA", text)
        self.assertIn("The canonical source is `memory.json`", text)
        self.assertIn("A fonte canônica é `memory.json`", text)
        self.assertIn("## Events / Eventos", text)
