from pathlib import Path

root = Path.cwd()
launcher = root / "KageLink Installer" / "pc_agent" / "unified_launcher.py"
entry = root / "KageLink Installer" / "pc_agent" / "unified_entry.py"
test_file = root / "KageLink Installer" / "pc_agent" / "tests" / "test_unified_localization_contract.py"

text = launcher.read_text(encoding="utf-8")

pt_anchor = '        "back": "Voltar",\n'
pt_extra = '''        "connection_help": "O KageLink cria a chave de acesso automaticamente e inicia por padrão uma rota segura via Cloudflare.",
        "access_key_help": "Uma chave de acesso aleatória e segura será criada automaticamente.",
        "finish_help": "O KageLink.exe gerenciará o Agent, o ciclo de vida da sessão, o Interpreter e o Memory Reviewer. O uso normal não exige PowerShell.",
        "state_on": "ATIVO",
        "state_off": "DESATIVADO",
        "ollama_model": "Modelo Ollama",
        "invalid_port": "Porta inválida.",
        "select_vault": "Selecione a Vault LeafOS.",
        "settings_help": "O KageLink mantém chat, GAME e STATS isolados do LeafOS. Alterações de rede ou caminhos do LeafOS reiniciam o Agent com segurança.",
        "operation_failed": "A operação falhou:\\n\\n{error}",
        "interpreter_failed": "O Interpreter não conseguiu concluir uma ou mais sessões:",
        "interpreter_preserved": "A sessão, os dados do Processor e o RAW foram preservados. Use 'Interpretar pendentes' para tentar novamente.",
'''
if '"connection_help"' not in text:
    if pt_anchor not in text:
        raise RuntimeError("PT-BR TEXT anchor not found")
    text = text.replace(pt_anchor, pt_anchor + pt_extra, 1)

en_anchor = '        "back": "Back",\n'
en_extra = '''        "connection_help": "KageLink creates the access key automatically and starts a secure Cloudflare route by default.",
        "access_key_help": "A secure random access key will be created automatically.",
        "finish_help": "KageLink.exe will manage the Agent, session lifecycle, Interpreter and Memory Reviewer. Normal use does not require PowerShell.",
        "state_on": "ON",
        "state_off": "OFF",
        "ollama_model": "Ollama model",
        "invalid_port": "Invalid port.",
        "select_vault": "Select the LeafOS Vault.",
        "settings_help": "KageLink keeps chat, GAME and STATS isolated from LeafOS. Network or LeafOS path changes restart the Agent safely.",
        "operation_failed": "The operation failed:\\n\\n{error}",
        "interpreter_failed": "The Interpreter could not complete one or more sessions:",
        "interpreter_preserved": "The session, Processor data and RAW were preserved. Use 'Interpret pending' to retry.",
'''
if '"connection_help": "KageLink creates' not in text:
    if en_anchor not in text:
        raise RuntimeError("EN-US TEXT anchor not found")
    text = text.replace(en_anchor, en_anchor + en_extra, 1)

replacements = {
    'self._title(self.tr("connection"), "KageLink creates the access key automatically and starts the secure Cloudflare route by default.")':
        'self._title(self.tr("connection"), self.tr("connection_help"))',
    'Label(self.content, text="A secure random access key will be created automatically. / Uma chave segura será criada automaticamente.", bg=COLORS["bg"], fg=COLORS["text"], wraplength=620, justify="left").pack(anchor="w")':
        'Label(self.content, text=self.tr("access_key_help"), bg=COLORS["bg"], fg=COLORS["text"], wraplength=620, justify="left").pack(anchor="w")',
    'self._title(self.tr("finish"), "KageLink.exe will own Agent, session lifecycle, Interpreter and Memory Reviewer. No PowerShell is required for normal use.")':
        'self._title(self.tr("finish"), self.tr("finish_help"))',
    'f"LeafOS: {\'ON\' if self.leafos_enabled.get() else \'OFF\'}",':
        'f"LeafOS: {self.tr(\'state_on\') if self.leafos_enabled.get() else self.tr(\'state_off\')}",',
    'f"Ollama model: {MODEL}",':
        'f"{self.tr(\'ollama_model\')}: {MODEL}",',
    'messagebox.showerror("KageLink", "Porta inválida / Invalid port", parent=self.window); return':
        'messagebox.showerror("KageLink", self.tr("invalid_port"), parent=self.window); return',
    'messagebox.showerror("KageLink", "Selecione a Vault LeafOS / Select the LeafOS Vault", parent=self.window); return':
        'messagebox.showerror("KageLink", self.tr("select_vault"), parent=self.window); return',
    'for title, var in (("AGENT", self.agent_var), ("GAME", self.game_var), ("CHAT", self.chat_var), ("INPUT", self.input_var), ("EXTERNAL", self.tunnel_var)):\n':
        'for title, var in ((_t(self.lang, "agent"), self.agent_var), (_t(self.lang, "game"), self.game_var), (_t(self.lang, "chat"), self.chat_var), (_t(self.lang, "input"), self.input_var), (_t(self.lang, "tunnel"), self.tunnel_var)):\n',
    'Label(card, text="KageLink keeps chat/GAME/STATS isolated from LeafOS. Changes to network or LeafOS paths restart the Agent safely.", bg=COLORS["card"], fg=COLORS["muted"], wraplength=760, justify="left").pack(anchor="w", pady=(0, 14))':
        'Label(card, text=_t(self.lang, "settings_help"), bg=COLORS["card"], fg=COLORS["muted"], wraplength=760, justify="left").pack(anchor="w", pady=(0, 14))',
    'messagebox.showerror("KageLink", "Porta inválida / Invalid port", parent=window); return':
        'messagebox.showerror("KageLink", _t(self.lang, "invalid_port"), parent=window); return',
    'messagebox.showerror("LeafOS", "Vault required / Vault obrigatória", parent=window); return':
        'messagebox.showerror("LeafOS", _t(self.lang, "select_vault"), parent=window); return',
    'messagebox.showerror("LeafOS", str(error), parent=window)':
        'messagebox.showerror("LeafOS", _t(self.lang, "operation_failed", error=error), parent=window)',
    'self.ui(lambda: messagebox.showerror("LeafOS", str(error), parent=self.root))':
        'self.ui(lambda: messagebox.showerror("LeafOS", _t(self.lang, "operation_failed", error=error), parent=self.root))',
    'self.ui(lambda: messagebox.showerror("Ollama", str(error), parent=self.root))':
        'self.ui(lambda: messagebox.showerror("Ollama", _t(self.lang, "operation_failed", error=error), parent=self.root))',
}

for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new)
    elif new not in text:
        raise RuntimeError(f"launcher replacement anchor not found: {old[:90]}")

launcher.write_text(text, encoding="utf-8", newline="\n")

text = entry.read_text(encoding="utf-8")
old = '''        if self.lang == "pt-BR":
            return (
                "O Interpreter não conseguiu concluir uma ou mais sessões:\\n\\n"
                f"{details}\\n\\n"
                "A sessão, o Processor e o RAW foram preservados. "
                "Use 'Interpretar pendentes' para tentar novamente."
            )
        return (
            "The Interpreter could not complete one or more sessions:\\n\\n"
            f"{details}\\n\\n"
            "The session, Processor data and RAW were preserved. "
            "Use 'Interpret pending' to retry."
        )
'''
new = '''        return (
            f"{launcher._t(self.lang, 'interpreter_failed')}\\n\\n"
            f"{details}\\n\\n"
            f"{launcher._t(self.lang, 'interpreter_preserved')}"
        )
'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise RuntimeError("unified_entry interpreter localization block not found")

old_error = '''                lambda value=str(error): messagebox.showerror(
                    "LeafOS",
                    value,
                    parent=self.root,
                )
'''
new_error = '''                lambda value=error: messagebox.showerror(
                    "LeafOS",
                    launcher._t(self.lang, "operation_failed", error=value),
                    parent=self.root,
                )
'''
if old_error in text:
    text = text.replace(old_error, new_error, 1)
elif new_error not in text:
    raise RuntimeError("unified_entry error wrapper not found")
entry.write_text(text, encoding="utf-8", newline="\n")

test_content = '''from __future__ import annotations

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
        source = launcher_source + "\\n" + entry_source
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
'''
test_file.write_text(test_content, encoding="utf-8", newline="\n")
print("unified localization audit fix applied")
