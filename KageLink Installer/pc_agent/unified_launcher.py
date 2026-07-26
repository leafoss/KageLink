from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    X,
    BooleanVar,
    Button,
    Entry,
    Frame,
    Label,
    StringVar,
    Tk,
    Toplevel,
    filedialog,
    messagebox,
    ttk,
)

import kagelink_launcher as legacy
from pc_agent.config import (
    CONFIG_PATH,
    PROJECT_DIR,
    RESOURCE_DIR,
    ensure_config,
    load_config,
    update_user_settings,
)
from pc_agent.history import HistoryStore
from pc_agent.leafos_interpreter import LeafOSInterpreter, OllamaInterpreterProvider
from pc_agent.leafos_memory import LeafOSMemoryReviewer
from pc_agent.leafos_memory_reviewer import COLORS, MemoryReviewerApp
from pc_agent.leafos_ollama import OllamaManager
from pc_agent.primary_character import (
    get_primary_character,
    resolve_primary_character,
    saved_characters,
    set_primary_character,
)


MODEL = "qwen3:14b"
OLLAMA_URL = "http://127.0.0.1:11434"


TEXT = {
    "pt-BR": {
        "app_title": "KageLink · LeafOS",
        "overview": "Visão geral",
        "memory": "Memória",
        "connection": "Conexão",
        "settings": "Configurações",
        "character": "Personagem atual",
        "change": "Trocar",
        "no_character": "Nenhum personagem configurado",
        "session": "Sessão atual",
        "no_session": "Nenhuma sessão IC aberta",
        "session_open": "{id} · {count} mensagens IC",
        "memory_status": "Memória LeafOS",
        "pending_review": "{count} sessão(ões) aguardando revisão",
        "finalize_review": "Finalizar sessão e revisar",
        "interpret": "Interpretar pendentes",
        "open_reviewer": "Abrir Memory Reviewer",
        "services": "Serviços",
        "agent": "AGENTE",
        "game": "JOGO",
        "chat": "CHAT",
        "input": "ENTRADA",
        "tunnel": "CONEXÃO EXTERNA",
        "ollama": "Ollama",
        "model": "Modelo",
        "online": "Online",
        "offline": "Offline",
        "installed": "Instalado",
        "not_installed": "Não instalado",
        "available": "Disponível",
        "missing": "Não baixado",
        "install_ollama": "Instalar Ollama",
        "start_ollama": "Iniciar Ollama",
        "download_model": "Baixar qwen3:14b",
        "closed_sessions": "Sessões fechadas",
        "interpretations": "Interpretadas",
        "recommended_address": "Endereço externo recomendado",
        "local_address": "Endereço local",
        "access_key": "Chave de acesso",
        "copy_address": "Copiar endereço",
        "copy_key": "Copiar chave",
        "copy_both": "Copiar ambos",
        "restart_connection": "Reiniciar conexão",
        "open_logs": "Abrir logs",
        "save_restart": "Salvar e reiniciar",
        "leafos_enabled": "Ativar integração LeafOS",
        "vault": "Vault LeafOS",
        "raw": "Pasta RAW",
        "export_ic": "Exportar IC",
        "export_ooc": "Exportar OOC",
        "language": "Idioma",
        "port": "Porta",
        "primary_required": "O LeafOS está ativo. Escolha o personagem que você vai interpretar antes de jogar.",
        "character_title": "Personagem principal",
        "character_help": "Este personagem será gravado dentro das novas sessões do LeafOS.",
        "save": "Salvar",
        "cancel": "Cancelar",
        "working": "Processando...",
        "finalizing": "Finalizando sessão e preservando RAW...",
        "finalized": "Sessão finalizada com segurança.",
        "interpret_done": "Interpreter concluído: {interpreted} nova(s), {failed} falha(s).",
        "ollama_required": "Ollama/qwen3:14b ainda não está pronto. Use os controles da tela Memória.",
        "close_confirm": "Finalizar a sessão atual e encerrar o KageLink?",
        "close_failed": "Não foi possível confirmar o fechamento seguro da sessão. Forçar a saída mesmo assim?",
        "leafos_disabled": "Integração LeafOS desativada",
        "blocked_character": "LeafOS aguardando personagem principal",
        "first_leafos": "LeafOS / Memória",
        "first_leafos_help": "Opcional. Ative para registrar RAW, organizar sessões e usar Interpreter/Reviewer.",
        "browse": "Procurar",
        "finish": "Concluir",
        "continue": "Continuar",
        "back": "Voltar",
    },
    "en-US": {
        "app_title": "KageLink · LeafOS",
        "overview": "Overview",
        "memory": "Memory",
        "connection": "Connection",
        "settings": "Settings",
        "character": "Current character",
        "change": "Change",
        "no_character": "No character configured",
        "session": "Current session",
        "no_session": "No open IC session",
        "session_open": "{id} · {count} IC messages",
        "memory_status": "LeafOS Memory",
        "pending_review": "{count} session(s) waiting for review",
        "finalize_review": "Finalize session and review",
        "interpret": "Interpret pending",
        "open_reviewer": "Open Memory Reviewer",
        "services": "Services",
        "agent": "AGENT",
        "game": "GAME",
        "chat": "CHAT",
        "input": "INPUT",
        "tunnel": "EXTERNAL CONNECTION",
        "ollama": "Ollama",
        "model": "Model",
        "online": "Online",
        "offline": "Offline",
        "installed": "Installed",
        "not_installed": "Not installed",
        "available": "Available",
        "missing": "Not downloaded",
        "install_ollama": "Install Ollama",
        "start_ollama": "Start Ollama",
        "download_model": "Download qwen3:14b",
        "closed_sessions": "Closed sessions",
        "interpretations": "Interpreted",
        "recommended_address": "Recommended external address",
        "local_address": "Local address",
        "access_key": "Access key",
        "copy_address": "Copy address",
        "copy_key": "Copy key",
        "copy_both": "Copy both",
        "restart_connection": "Restart connection",
        "open_logs": "Open logs",
        "save_restart": "Save and restart",
        "leafos_enabled": "Enable LeafOS integration",
        "vault": "LeafOS Vault",
        "raw": "RAW folder",
        "export_ic": "Export IC",
        "export_ooc": "Export OOC",
        "language": "Language",
        "port": "Port",
        "primary_required": "LeafOS is enabled. Choose the character you will play before starting the game.",
        "character_title": "Primary character",
        "character_help": "This character will be written into new LeafOS sessions.",
        "save": "Save",
        "cancel": "Cancel",
        "working": "Working...",
        "finalizing": "Finalizing session and preserving RAW...",
        "finalized": "Session finalized safely.",
        "interpret_done": "Interpreter finished: {interpreted} new, {failed} failed.",
        "ollama_required": "Ollama/qwen3:14b is not ready yet. Use the controls on the Memory page.",
        "close_confirm": "Finalize the current session and exit KageLink?",
        "close_failed": "The session could not be confirmed as safely closed. Force exit anyway?",
        "leafos_disabled": "LeafOS integration disabled",
        "blocked_character": "LeafOS waiting for a primary character",
        "first_leafos": "LeafOS / Memory",
        "first_leafos_help": "Optional. Enable it to record RAW, organize sessions and use Interpreter/Reviewer.",
        "browse": "Browse",
        "finish": "Finish",
        "continue": "Continue",
        "back": "Back",
    },
}


def _t(language: str, key: str, **kwargs) -> str:
    value = TEXT.get(language, TEXT["en-US"]).get(key, key)
    return value.format(**kwargs) if kwargs else value


def _self_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve())]


class UnifiedFirstRunWizard:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.result: dict | None = None
        self.window = Toplevel(root)
        self.window.title("KageLink · LeafOS")
        self.window.geometry("700x560")
        self.window.resizable(False, False)
        self.window.configure(bg=COLORS["bg"])
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.language = StringVar(value="pt-BR")
        self.port = StringVar(value="8765")
        self.leafos_enabled = BooleanVar(value=False)
        self.vault = StringVar(value="")
        self.primary_character = StringVar(value="")
        self.page = 0
        self.content = Frame(self.window, bg=COLORS["bg"])
        self.content.pack(fill=BOTH, expand=True, padx=26, pady=22)
        nav = Frame(self.window, bg=COLORS["header"])
        nav.pack(fill=X, side="bottom")
        self.back = Button(nav, command=self.previous, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=18, pady=9)
        self.back.pack(side=LEFT, padx=16, pady=12)
        self.next = Button(nav, command=self.advance, bg=COLORS["approve"], fg=COLORS["text"], relief="flat", padx=18, pady=9)
        self.next.pack(side=RIGHT, padx=16, pady=12)
        self.render()
        self.window.grab_set()

    def tr(self, key: str, **kwargs) -> str:
        return _t(self.language.get(), key, **kwargs)

    def _clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def _title(self, title: str, subtitle: str = "") -> None:
        Label(self.content, text=title, bg=COLORS["bg"], fg=COLORS["text"], font=("Segoe UI Semibold", 23)).pack(anchor="w", pady=(18, 6))
        if subtitle:
            Label(self.content, text=subtitle, bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 10), wraplength=620, justify="left").pack(anchor="w", pady=(0, 20))

    def render(self) -> None:
        self._clear()
        self.back.configure(text=self.tr("back"), state="normal" if self.page > 0 else "disabled")
        self.next.configure(text=self.tr("finish") if self.page == 3 else self.tr("continue"))
        [self._page_language, self._page_connection, self._page_leafos, self._page_finish][self.page]()

    def _page_language(self) -> None:
        self._title("KageLink · LeafOS", "PT-BR / EN-US")
        for text, value in (("Português do Brasil", "pt-BR"), ("English (US)", "en-US")):
            ttk.Radiobutton(self.content, text=text, variable=self.language, value=value, command=self.render).pack(anchor="w", pady=8)

    def _page_connection(self) -> None:
        self._title(self.tr("connection"), "KageLink creates the access key automatically and starts the secure Cloudflare route by default.")
        Label(self.content, text=self.tr("port"), bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w")
        Entry(self.content, textvariable=self.port, bg=COLORS["surface_alt"], fg=COLORS["text"], insertbackground=COLORS["accent"], relief="flat", font=("Consolas", 14)).pack(fill=X, ipady=9, pady=(5, 18))
        Label(self.content, text="A secure random access key will be created automatically. / Uma chave segura será criada automaticamente.", bg=COLORS["bg"], fg=COLORS["text"], wraplength=620, justify="left").pack(anchor="w")

    def _page_leafos(self) -> None:
        self._title(self.tr("first_leafos"), self.tr("first_leafos_help"))
        ttk.Checkbutton(self.content, text=self.tr("leafos_enabled"), variable=self.leafos_enabled).pack(anchor="w", pady=(0, 18))
        Label(self.content, text=self.tr("vault"), bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w")
        row = Frame(self.content, bg=COLORS["bg"]); row.pack(fill=X, pady=(5, 14))
        Entry(row, textvariable=self.vault, bg=COLORS["surface_alt"], fg=COLORS["text"], insertbackground=COLORS["accent"], relief="flat").pack(side=LEFT, fill=X, expand=True, ipady=8)
        Button(row, text=self.tr("browse"), command=self._browse_vault, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=12, pady=7).pack(side=LEFT, padx=(8, 0))
        Label(self.content, text=self.tr("character_title"), bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w")
        Entry(self.content, textvariable=self.primary_character, bg=COLORS["surface_alt"], fg=COLORS["text"], insertbackground=COLORS["accent"], relief="flat").pack(fill=X, ipady=8, pady=(5, 6))
        Label(self.content, text=self.tr("character_help"), bg=COLORS["bg"], fg=COLORS["muted"], wraplength=620, justify="left").pack(anchor="w")

    def _page_finish(self) -> None:
        self._title(self.tr("finish"), "KageLink.exe will own Agent, session lifecycle, Interpreter and Memory Reviewer. No PowerShell is required for normal use.")
        lines = [
            f"{self.tr('port')}: {self.port.get()}",
            f"LeafOS: {'ON' if self.leafos_enabled.get() else 'OFF'}",
            f"{self.tr('vault')}: {self.vault.get().strip() or '—'}",
            f"{self.tr('character_title')}: {self.primary_character.get().strip() or '—'}",
            f"Ollama model: {MODEL}",
        ]
        Label(self.content, text="\n".join(lines), bg=COLORS["surface"], fg=COLORS["text"], justify="left", anchor="w", padx=18, pady=18, highlightthickness=1, highlightbackground=COLORS["border"]).pack(fill=X, pady=16)

    def _browse_vault(self) -> None:
        selected = filedialog.askdirectory(parent=self.window, title=self.tr("vault"), initialdir=str(Path.home()))
        if selected:
            self.vault.set(selected)

    def previous(self) -> None:
        self.page = max(0, self.page - 1); self.render()

    def advance(self) -> None:
        if self.page == 1:
            try:
                port = int(self.port.get().strip())
                if not 1024 <= port <= 65535:
                    raise ValueError
            except ValueError:
                messagebox.showerror("KageLink", "Porta inválida / Invalid port", parent=self.window); return
        if self.page == 2 and self.leafos_enabled.get():
            if not self.vault.get().strip():
                messagebox.showerror("KageLink", "Selecione a Vault LeafOS / Select the LeafOS Vault", parent=self.window); return
            if not self.primary_character.get().strip():
                messagebox.showerror("KageLink", self.tr("primary_required"), parent=self.window); return
        if self.page < 3:
            self.page += 1; self.render(); return
        self.result = {
            "language": self.language.get(),
            "port": int(self.port.get().strip()),
            "leafos_enabled": self.leafos_enabled.get(),
            "vault": self.vault.get().strip(),
            "primary_character": self.primary_character.get().strip(),
        }
        self.window.destroy()

    def cancel(self) -> None:
        self.result = None; self.window.destroy()

    def show(self) -> dict | None:
        self.root.wait_window(self.window); return self.result


class UnifiedKageLinkAgentUI(legacy.KageLinkAgentUI):
    def __init__(self, root: Tk) -> None:
        self._finalization_done = False
        self._leafos_busy = False
        self._page_buttons: dict[str, Button] = {}
        self._pages: dict[str, Frame] = {}
        self.character_var = StringVar(value="—")
        self.session_var = StringVar(value="—")
        self.pending_var = StringVar(value="—")
        self.closed_sessions_var = StringVar(value="0")
        self.interpretations_var = StringVar(value="0")
        self.ollama_var = StringVar(value="—")
        self.model_var = StringVar(value="—")
        super().__init__(root)
        self.root.after(900, self._refresh_leafos_status)
        self.root.after(1300, self._refresh_ollama_status)
        self.root.after(600, self._prompt_character_if_required)

    def _load_logo(self) -> None:
        self._logo_image = None
        path = RESOURCE_DIR / "pc_agent" / "assets" / "leafos_emblem.png"
        if not path.exists():
            path = Path(__file__).resolve().parent / "pc_agent" / "assets" / "leafos_emblem.png"
        try:
            import tkinter as tk
            self._logo_image = tk.PhotoImage(file=str(path))
            self.root.iconphoto(True, self._logo_image)
        except Exception:
            self._logo_image = None

    def _build_ui(self) -> None:
        self.root.title(_t(self.lang, "app_title"))
        self.root.geometry("1260x820")
        self.root.minsize(1050, 690)
        self.root.configure(bg=COLORS["bg"])
        self._load_logo()

        header = Frame(self.root, bg=COLORS["header"], padx=20, pady=13); header.pack(fill=X)
        if self._logo_image is not None:
            Label(header, image=self._logo_image, bg=COLORS["header"]).pack(side=LEFT, padx=(0, 12))
        title_box = Frame(header, bg=COLORS["header"]); title_box.pack(side=LEFT)
        Label(title_box, text="KageLink", bg=COLORS["header"], fg=COLORS["text"], font=("Segoe UI Semibold", 22)).pack(anchor="w")
        Label(title_box, text="LeafOS Desktop", bg=COLORS["header"], fg=COLORS["accent"], font=("Segoe UI", 10)).pack(anchor="w")
        self.header_character = Label(header, textvariable=self.character_var, bg=COLORS["header"], fg=COLORS["accent_soft"], font=("Segoe UI Semibold", 10)); self.header_character.pack(side=RIGHT, padx=10)

        shell = Frame(self.root, bg=COLORS["bg"]); shell.pack(fill=BOTH, expand=True, padx=14, pady=(10, 14))
        sidebar = Frame(shell, bg=COLORS["card"], highlightthickness=1, highlightbackground=COLORS["border"], width=190); sidebar.pack(side=LEFT, fill="y", padx=(0, 10)); sidebar.pack_propagate(False)
        content = Frame(shell, bg=COLORS["bg"]); content.pack(side=LEFT, fill=BOTH, expand=True)

        for key in ("overview", "memory", "connection", "settings"):
            button = Button(sidebar, text=_t(self.lang, key), command=lambda k=key: self._show_page(k), anchor="w", bg=COLORS["card"], fg=COLORS["text"], activebackground=COLORS["selected"], activeforeground=COLORS["accent_soft"], relief="flat", bd=0, padx=18, pady=13, font=("Segoe UI Semibold", 10))
            button.pack(fill=X, padx=8, pady=(8 if key == "overview" else 2, 0)); self._page_buttons[key] = button
            page = Frame(content, bg=COLORS["bg"]); self._pages[key] = page

        self._build_overview(self._pages["overview"])
        self._build_memory(self._pages["memory"])
        self._build_connection(self._pages["connection"])
        self._build_settings_page(self._pages["settings"])
        self._show_page("overview")

        self.status_line = Label(self.root, textvariable=self.message_var, bg=COLORS["bg"], fg=COLORS["muted"], anchor="w", font=("Segoe UI", 9)); self.status_line.pack(fill=X, padx=18, pady=(0, 8))

    def _card(self, parent: Frame, *, padx=16, pady=14) -> Frame:
        card = Frame(parent, bg=COLORS["card"], highlightthickness=1, highlightbackground=COLORS["border"], padx=padx, pady=pady)
        return card

    def _section_title(self, parent: Frame, text: str) -> None:
        Label(parent, text=text, bg=COLORS["bg"], fg=COLORS["text"], font=("Segoe UI Semibold", 14)).pack(anchor="w", pady=(2, 10))

    def _status_card(self, parent: Frame, title: str, variable: StringVar) -> Frame:
        card = self._card(parent, padx=10, pady=10)
        Label(card, text=title, bg=COLORS["card"], fg=COLORS["muted"], font=("Segoe UI Semibold", 8)).pack()
        Label(card, textvariable=variable, bg=COLORS["card"], fg=COLORS["accent"], font=("Segoe UI Semibold", 9), wraplength=125).pack(pady=(5, 0))
        return card

    def _build_overview(self, page: Frame) -> None:
        page.pack_propagate(False)
        self._section_title(page, _t(self.lang, "services"))
        statuses = Frame(page, bg=COLORS["bg"]); statuses.pack(fill=X)
        for title, var in (("AGENT", self.agent_var), ("GAME", self.game_var), ("CHAT", self.chat_var), ("INPUT", self.input_var), ("EXTERNAL", self.tunnel_var)):
            self._status_card(statuses, title, var).pack(side=LEFT, fill=X, expand=True, padx=4)

        top = Frame(page, bg=COLORS["bg"]); top.pack(fill=X, pady=(14, 0))
        character = self._card(top); character.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 6))
        Label(character, text=_t(self.lang, "character"), bg=COLORS["card"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w")
        Label(character, textvariable=self.character_var, bg=COLORS["card"], fg=COLORS["accent"], font=("Segoe UI Semibold", 16)).pack(anchor="w", pady=(5, 9))
        Button(character, text=_t(self.lang, "change"), command=self.change_character, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=12, pady=7).pack(anchor="w")

        session = self._card(top); session.pack(side=LEFT, fill=BOTH, expand=True, padx=(6, 0))
        Label(session, text=_t(self.lang, "session"), bg=COLORS["card"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w")
        Label(session, textvariable=self.session_var, bg=COLORS["card"], fg=COLORS["text"], font=("Segoe UI Semibold", 14), wraplength=430, justify="left").pack(anchor="w", pady=(5, 9))
        Label(session, textvariable=self.pending_var, bg=COLORS["card"], fg=COLORS["accent_soft"], font=("Segoe UI", 9)).pack(anchor="w")

        actions = self._card(page); actions.pack(fill=X, pady=(14, 0))
        Button(actions, text=_t(self.lang, "finalize_review"), command=self.finalize_and_review, bg=COLORS["approve"], fg=COLORS["text"], activebackground=COLORS["approve_hover"], relief="flat", padx=18, pady=11, font=("Segoe UI Semibold", 10)).pack(side=LEFT, padx=(0, 8))
        Button(actions, text=_t(self.lang, "interpret"), command=lambda: self.interpret_pending(False), bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=18, pady=11).pack(side=LEFT, padx=8)
        Button(actions, text=_t(self.lang, "open_reviewer"), command=self.open_reviewer, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=18, pady=11).pack(side=LEFT, padx=8)

    def _build_memory(self, page: Frame) -> None:
        self._section_title(page, _t(self.lang, "memory"))
        ollama = self._card(page); ollama.pack(fill=X)
        row = Frame(ollama, bg=COLORS["card"]); row.pack(fill=X)
        for title, variable in ((_t(self.lang, "ollama"), self.ollama_var), (_t(self.lang, "model"), self.model_var)):
            box = Frame(row, bg=COLORS["surface_alt"], padx=14, pady=12, highlightthickness=1, highlightbackground=COLORS["border_soft"]); box.pack(side=LEFT, fill=X, expand=True, padx=4)
            Label(box, text=title, bg=COLORS["surface_alt"], fg=COLORS["muted"]).pack(anchor="w")
            Label(box, textvariable=variable, bg=COLORS["surface_alt"], fg=COLORS["accent"], font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(5, 0))
        controls = Frame(ollama, bg=COLORS["card"]); controls.pack(fill=X, pady=(12, 0))
        Button(controls, text=_t(self.lang, "install_ollama"), command=self.install_ollama, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=12, pady=8).pack(side=LEFT, padx=(0, 6))
        Button(controls, text=_t(self.lang, "start_ollama"), command=self.start_ollama, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=12, pady=8).pack(side=LEFT, padx=6)
        Button(controls, text=_t(self.lang, "download_model"), command=self.download_model, bg=COLORS["edit"], fg="#fff2d0", relief="flat", padx=12, pady=8).pack(side=LEFT, padx=6)

        counts = self._card(page); counts.pack(fill=X, pady=(14, 0))
        for title, variable in ((_t(self.lang, "closed_sessions"), self.closed_sessions_var), (_t(self.lang, "interpretations"), self.interpretations_var), (_t(self.lang, "memory_status"), self.pending_var)):
            box = Frame(counts, bg=COLORS["card"]); box.pack(side=LEFT, fill=X, expand=True, padx=8)
            Label(box, text=title, bg=COLORS["card"], fg=COLORS["muted"]).pack(anchor="w")
            Label(box, textvariable=variable, bg=COLORS["card"], fg=COLORS["text"], font=("Segoe UI Semibold", 12), wraplength=250).pack(anchor="w", pady=(5, 0))
        actions = self._card(page); actions.pack(fill=X, pady=(14, 0))
        Button(actions, text=_t(self.lang, "interpret"), command=lambda: self.interpret_pending(False), bg=COLORS["approve"], fg=COLORS["text"], relief="flat", padx=18, pady=10).pack(side=LEFT, padx=(0, 8))
        Button(actions, text=_t(self.lang, "open_reviewer"), command=self.open_reviewer, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=18, pady=10).pack(side=LEFT)

    def _build_connection(self, page: Frame) -> None:
        self._section_title(page, _t(self.lang, "connection"))
        card = self._card(page); card.pack(fill=X)
        self._field(card, _t(self.lang, "recommended_address"), self.external_var, True)
        self._field(card, _t(self.lang, "local_address"), self.local_var, False)
        self._field(card, _t(self.lang, "access_key"), self.token_var, False)
        row = Frame(card, bg=COLORS["card"]); row.pack(fill=X, pady=(8, 0))
        for text, command in (
            (_t(self.lang, "copy_address"), lambda: self.copy(self.external_url)),
            (_t(self.lang, "copy_key"), lambda: self.copy(self.config.access_token)),
            (_t(self.lang, "copy_both"), self.copy_both),
            (_t(self.lang, "restart_connection"), self.restart_tunnel),
            (_t(self.lang, "open_logs"), self.open_logs),
        ):
            Button(row, text=text, command=command, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=11, pady=8).pack(side=LEFT, padx=4)

    def _field(self, parent: Frame, title: str, variable: StringVar, highlight: bool) -> None:
        Label(parent, text=title, bg=COLORS["card"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 3))
        Entry(parent, textvariable=variable, state="readonly", readonlybackground=COLORS["surface_alt"], fg=COLORS["accent"] if highlight else COLORS["text"], relief="flat", font=("Consolas", 10)).pack(fill=X, ipady=9, pady=(0, 8))

    def _build_settings_page(self, page: Frame) -> None:
        self._section_title(page, _t(self.lang, "settings"))
        card = self._card(page); card.pack(fill=X)
        Label(card, text="KageLink keeps chat/GAME/STATS isolated from LeafOS. Changes to network or LeafOS paths restart the Agent safely.", bg=COLORS["card"], fg=COLORS["muted"], wraplength=760, justify="left").pack(anchor="w", pady=(0, 14))
        Button(card, text=_t(self.lang, "settings"), command=self.open_settings, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=18, pady=10).pack(anchor="w")

    def _show_page(self, key: str) -> None:
        for name, page in self._pages.items():
            page.pack_forget()
            self._page_buttons[name].configure(bg=COLORS["selected"] if name == key else COLORS["card"], fg=COLORS["accent_soft"] if name == key else COLORS["text"])
        self._pages[key].pack(fill=BOTH, expand=True)

    def _api_json(self, method: str, path: str, payload: dict | None = None, *, timeout: float = 20.0) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.config.port}{path}",
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.config.access_token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
        return value if isinstance(value, dict) else {}

    def _history(self) -> HistoryStore:
        return HistoryStore(self.config.database_path)

    def _refresh_leafos_status(self) -> None:
        if self.stopping:
            return
        try:
            if not self.config.leafos_enabled:
                self.character_var.set(get_primary_character(self._history()) or _t(self.lang, "no_character"))
                self.session_var.set(_t(self.lang, "leafos_disabled")); self.pending_var.set(_t(self.lang, "leafos_disabled"))
            elif self._server_is_healthy():
                payload = self._api_json("GET", "/api/leafos/status", timeout=2.5)
                character = str(payload.get("primary_character", "") or "")
                self.character_var.set(character or _t(self.lang, "no_character"))
                session = payload.get("session", {}) if isinstance(payload.get("session"), dict) else {}
                if session.get("blocked_no_primary_character"):
                    self.session_var.set(_t(self.lang, "blocked_character"))
                elif session.get("open"):
                    self.session_var.set(_t(self.lang, "session_open", id=session.get("session_id", ""), count=session.get("message_count", 0)))
                else:
                    self.session_var.set(_t(self.lang, "no_session"))
                pending = int(payload.get("pending_review_sessions", 0) or 0)
                self.pending_var.set(_t(self.lang, "pending_review", count=pending if pending >= 0 else "?"))
                self.closed_sessions_var.set(str(payload.get("closed_sessions", 0)))
                self.interpretations_var.set(str(payload.get("interpretations", 0)))
        except Exception:
            pass
        finally:
            self.root.after(1800, self._refresh_leafos_status)

    def _refresh_ollama_status(self) -> None:
        if self.stopping:
            return
        try:
            status = OllamaManager(base_url=OLLAMA_URL, model=MODEL).status()
            if not status.cli_path:
                self.ollama_var.set(_t(self.lang, "not_installed"))
            else:
                self.ollama_var.set(_t(self.lang, "online") if status.server_online else _t(self.lang, "installed"))
            self.model_var.set(_t(self.lang, "available") if status.model_available else _t(self.lang, "missing"))
        except Exception:
            self.ollama_var.set(_t(self.lang, "offline")); self.model_var.set(_t(self.lang, "missing"))
        finally:
            self.root.after(5000, self._refresh_ollama_status)

    def _prompt_character_if_required(self) -> None:
        if self.config.leafos_enabled and not get_primary_character(self._history()):
            messagebox.showwarning("LeafOS", _t(self.lang, "primary_required"), parent=self.root)
            self.change_character(required=True)

    def change_character(self, required: bool = False) -> None:
        history = self._history(); current = get_primary_character(history); saved = saved_characters(history)
        window = Toplevel(self.root); window.title(_t(self.lang, "character_title")); window.geometry("520x360"); window.configure(bg=COLORS["bg"]); window.transient(self.root); window.grab_set()
        Label(window, text=_t(self.lang, "character_title"), bg=COLORS["bg"], fg=COLORS["text"], font=("Segoe UI Semibold", 18)).pack(anchor="w", padx=22, pady=(22, 6))
        Label(window, text=_t(self.lang, "character_help"), bg=COLORS["bg"], fg=COLORS["muted"], wraplength=470, justify="left").pack(anchor="w", padx=22, pady=(0, 12))
        value = StringVar(value=current); Entry(window, textvariable=value, bg=COLORS["surface_alt"], fg=COLORS["text"], insertbackground=COLORS["accent"], relief="flat").pack(fill=X, padx=22, ipady=9)
        chips = Frame(window, bg=COLORS["bg"]); chips.pack(fill=X, padx=22, pady=12)
        for name in saved[:8]:
            Button(chips, text=name, command=lambda n=name: value.set(n), bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=8, pady=5).pack(side=LEFT, padx=3, pady=3)
        buttons = Frame(window, bg=COLORS["bg"]); buttons.pack(fill=X, padx=22, pady=16)
        def save_character() -> None:
            name = value.get().strip()
            if required and not name:
                messagebox.showerror("LeafOS", _t(self.lang, "primary_required"), parent=window); return
            try:
                if self._server_is_healthy():
                    result = self._api_json("POST", "/api/primary-character", {"name": name}, timeout=20)
                    self.character_var.set(str(result.get("primary_character", "") or _t(self.lang, "no_character")))
                else:
                    set_primary_character(history, name); self.character_var.set(name or _t(self.lang, "no_character"))
                window.destroy(); self._refresh_leafos_status()
            except Exception as error:
                messagebox.showerror("LeafOS", str(error), parent=window)
        Button(buttons, text=_t(self.lang, "save"), command=save_character, bg=COLORS["approve"], fg=COLORS["text"], relief="flat", padx=16, pady=8).pack(side=RIGHT)
        if not required:
            Button(buttons, text=_t(self.lang, "cancel"), command=window.destroy, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=16, pady=8).pack(side=RIGHT, padx=(0, 8))

    def _set_busy(self, text: str) -> bool:
        if self._leafos_busy:
            return False
        self._leafos_busy = True; self.ui(lambda: self.message_var.set(text)); return True

    def _clear_busy(self) -> None:
        self._leafos_busy = False

    def finalize_and_review(self) -> None:
        if not self._set_busy(_t(self.lang, "finalizing")):
            return
        threading.Thread(target=self._finalize_review_worker, name="LeafOSFinalizeReview", daemon=True).start()

    def _finalize_review_worker(self) -> None:
        try:
            self._api_json("POST", "/api/leafos/finalize-session", {"reason": "manual", "restart_monitor": True}, timeout=30)
            self.ui(lambda: self.message_var.set(_t(self.lang, "finalized")))
            self._interpret_pending_worker(open_reviewer=True)
        except Exception as error:
            self.ui(lambda: messagebox.showerror("LeafOS", str(error), parent=self.root))
        finally:
            self._clear_busy()

    def interpret_pending(self, open_reviewer: bool) -> None:
        if not self._set_busy(_t(self.lang, "working")):
            return
        threading.Thread(target=lambda: self._interpret_wrapper(open_reviewer), name="LeafOSInterpreter", daemon=True).start()

    def _interpret_wrapper(self, open_reviewer: bool) -> None:
        try:
            self._interpret_pending_worker(open_reviewer=open_reviewer)
        finally:
            self._clear_busy()

    def _interpret_pending_worker(self, *, open_reviewer: bool) -> None:
        config = load_config()
        if not config.leafos_enabled or config.leafos_vault_path is None:
            self.ui(lambda: self.message_var.set(_t(self.lang, "leafos_disabled"))); return
        manager = OllamaManager(base_url=OLLAMA_URL, model=MODEL)
        status = manager.status()
        if not status.server_online and status.cli_path:
            status = manager.start_server()
        if not status.server_online or not status.model_available:
            self.ui(lambda: self.message_var.set(_t(self.lang, "ollama_required"))); return
        history = HistoryStore(config.database_path)
        provider = OllamaInterpreterProvider(base_url=OLLAMA_URL, model=MODEL)
        interpreter = LeafOSInterpreter(
            Path(config.leafos_vault_path),
            provider,
            primary_character_resolver=lambda session: resolve_primary_character(history, session.get("started_at")),
        )
        result = interpreter.run_once()
        self.ui(lambda: self.message_var.set(_t(self.lang, "interpret_done", interpreted=result.get("interpreted", 0), failed=result.get("failed", 0))))
        self.ui(self._refresh_leafos_status)
        if open_reviewer:
            self.ui(self.open_reviewer)

    def open_reviewer(self) -> None:
        config = load_config()
        if config.leafos_vault_path is None:
            messagebox.showinfo("LeafOS", _t(self.lang, "leafos_disabled"), parent=self.root); return
        args = _self_command() + ["--leafos-reviewer", "--vault", str(config.leafos_vault_path), "--lang", self.lang]
        subprocess.Popen(args, cwd=PROJECT_DIR, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def install_ollama(self) -> None:
        if not self._set_busy(_t(self.lang, "working")): return
        def worker() -> None:
            try:
                OllamaManager(base_url=OLLAMA_URL, model=MODEL).install_with_winget()
                self.ui(lambda: self.message_var.set("Ollama OK"))
            except Exception as error:
                self.ui(lambda: messagebox.showerror("Ollama", str(error), parent=self.root))
            finally:
                self._clear_busy(); self.ui(self._refresh_ollama_status)
        threading.Thread(target=worker, name="OllamaInstall", daemon=True).start()

    def start_ollama(self) -> None:
        if not self._set_busy(_t(self.lang, "working")): return
        def worker() -> None:
            try:
                OllamaManager(base_url=OLLAMA_URL, model=MODEL).start_server(); self.ui(lambda: self.message_var.set("Ollama OK"))
            except Exception as error:
                self.ui(lambda: messagebox.showerror("Ollama", str(error), parent=self.root))
            finally:
                self._clear_busy(); self.ui(self._refresh_ollama_status)
        threading.Thread(target=worker, name="OllamaStart", daemon=True).start()

    def download_model(self) -> None:
        if not self._set_busy(_t(self.lang, "working")): return
        def worker() -> None:
            try:
                manager = OllamaManager(base_url=OLLAMA_URL, model=MODEL)
                manager.pull_model(on_output=lambda line: self.ui(lambda value=line: self.message_var.set(value[-180:])))
                self.ui(lambda: self.message_var.set(f"{MODEL} OK"))
            except Exception as error:
                self.ui(lambda: messagebox.showerror("Ollama", str(error), parent=self.root))
            finally:
                self._clear_busy(); self.ui(self._refresh_ollama_status)
        threading.Thread(target=worker, name="OllamaPull", daemon=True).start()

    def open_settings(self) -> None:
        config = load_config(); window = Toplevel(self.root); window.title(_t(self.lang, "settings")); window.geometry("690x690"); window.configure(bg=COLORS["bg"]); window.transient(self.root); window.grab_set()
        language = StringVar(value=config.ui_language); port = StringVar(value=str(config.port)); enabled = BooleanVar(value=config.leafos_enabled); vault = StringVar(value=str(config.leafos_vault_path or "")); raw = StringVar(value=str(config.leafos_raw_output_path or "")); export_ic = BooleanVar(value=config.leafos_export_ic); export_ooc = BooleanVar(value=config.leafos_export_ooc)
        body = Frame(window, bg=COLORS["bg"]); body.pack(fill=BOTH, expand=True, padx=24, pady=20)
        Label(body, text=_t(self.lang, "settings"), bg=COLORS["bg"], fg=COLORS["text"], font=("Segoe UI Semibold", 20)).pack(anchor="w", pady=(0, 16))
        def label(text: str) -> None: Label(body, text=text, bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(10, 4))
        label(_t(self.lang, "language")); ttk.Combobox(body, textvariable=language, values=["pt-BR", "en-US"], state="readonly").pack(fill=X)
        label(_t(self.lang, "port")); Entry(body, textvariable=port, bg=COLORS["surface_alt"], fg=COLORS["text"], insertbackground=COLORS["accent"], relief="flat").pack(fill=X, ipady=7)
        ttk.Checkbutton(body, text=_t(self.lang, "leafos_enabled"), variable=enabled).pack(anchor="w", pady=(16, 4))
        label(_t(self.lang, "vault")); vr = Frame(body, bg=COLORS["bg"]); vr.pack(fill=X); Entry(vr, textvariable=vault, bg=COLORS["surface_alt"], fg=COLORS["text"], insertbackground=COLORS["accent"], relief="flat").pack(side=LEFT, fill=X, expand=True, ipady=7)
        def browse_vault() -> None:
            selected = filedialog.askdirectory(parent=window, title=_t(self.lang, "vault"), initialdir=vault.get().strip() or str(Path.home()))
            if selected:
                old_default = str(Path(vault.get().strip()) / "90 - KageAgent" / "Raw") if vault.get().strip() else ""
                vault.set(selected)
                if not raw.get().strip() or raw.get().strip() == old_default:
                    raw.set(str(Path(selected) / "90 - KageAgent" / "Raw"))
        Button(vr, text=_t(self.lang, "browse"), command=browse_vault, bg=COLORS["button"], fg=COLORS["text"], relief="flat", padx=10, pady=6).pack(side=LEFT, padx=(8, 0))
        label(_t(self.lang, "raw")); Entry(body, textvariable=raw, bg=COLORS["surface_alt"], fg=COLORS["text"], insertbackground=COLORS["accent"], relief="flat").pack(fill=X, ipady=7)
        ttk.Checkbutton(body, text=_t(self.lang, "export_ic"), variable=export_ic).pack(anchor="w", pady=(14, 3)); ttk.Checkbutton(body, text=_t(self.lang, "export_ooc"), variable=export_ooc).pack(anchor="w")
        def save() -> None:
            try:
                port_value = int(port.get().strip())
                if not 1024 <= port_value <= 65535: raise ValueError
            except ValueError:
                messagebox.showerror("KageLink", "Porta inválida / Invalid port", parent=window); return
            if enabled.get() and not vault.get().strip():
                messagebox.showerror("LeafOS", "Vault required / Vault obrigatória", parent=window); return
            update_user_settings(language=language.get(), port=port_value, leafos_enabled=enabled.get(), leafos_vault_path=vault.get().strip(), leafos_raw_output_path=raw.get().strip(), leafos_export_ic=export_ic.get(), leafos_export_ooc=export_ooc.get())
            window.destroy(); self._restart_application()
        Button(body, text=_t(self.lang, "save_restart"), command=save, bg=COLORS["approve"], fg=COLORS["text"], relief="flat", padx=18, pady=10).pack(anchor="e", pady=(20, 0))

    def _finalize_for_shutdown(self) -> bool:
        if self._finalization_done or not self.config.leafos_enabled or not self._server_is_healthy():
            self._finalization_done = True; return True
        try:
            self.message_var.set(_t(self.lang, "finalizing")); self.root.update_idletasks()
            self._api_json("POST", "/api/leafos/finalize-session", {"reason": "agent_shutdown", "restart_monitor": False}, timeout=30)
            self._finalization_done = True; return True
        except Exception as error:
            self.logger.exception("LeafOS shutdown finalization failed: %s", error); return False

    def request_close(self) -> None:
        if not messagebox.askyesno("KageLink", _t(self.lang, "close_confirm"), parent=self.root): return
        if not self._finalize_for_shutdown():
            if not messagebox.askyesno("KageLink", _t(self.lang, "close_failed"), parent=self.root): return
        legacy.KageLinkAgentUI.shutdown(self, prompt=False); self.root.destroy()

    def shutdown(self, prompt: bool = False) -> None:
        self._finalize_for_shutdown(); legacy.KageLinkAgentUI.shutdown(self, prompt=prompt)

    def _restart_application(self) -> None:
        if not self._finalize_for_shutdown():
            if not messagebox.askyesno("KageLink", _t(self.lang, "close_failed"), parent=self.root): return
        executable = _self_command(); legacy.KageLinkAgentUI.shutdown(self, prompt=False); subprocess.Popen(executable, cwd=PROJECT_DIR); self.root.destroy()


def _run_reviewer_mode(args: argparse.Namespace) -> int:
    reviewer = LeafOSMemoryReviewer(Path(args.vault)); app = MemoryReviewerApp(reviewer, language=args.lang); app.mainloop(); return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--leafos-reviewer", action="store_true")
    parser.add_argument("--vault")
    parser.add_argument("--lang", choices=("pt-BR", "en-US"), default=None)
    args, _unknown = parser.parse_known_args()
    if args.leafos_reviewer:
        if not args.vault:
            raise SystemExit("--vault is required for --leafos-reviewer")
        return _run_reviewer_mode(args)

    legacy._ensure_standard_streams()
    if os.name != "nt":
        raise SystemExit("KageLink PC Agent is available only for Windows.")
    if legacy.already_running():
        return 0

    root: Tk | None = None
    try:
        root = Tk(); root.title("KageLink · LeafOS"); root.withdraw()
        first_run = not CONFIG_PATH.exists()
        if first_run:
            wizard = UnifiedFirstRunWizard(root); result = wizard.show()
            if result is None:
                root.destroy(); legacy.release_mutex(); return 0
            ensure_config(language=result["language"], port=result["port"])
            update_user_settings(
                language=result["language"],
                port=result["port"],
                leafos_enabled=result["leafos_enabled"],
                leafos_vault_path=result["vault"],
                leafos_raw_output_path=str(Path(result["vault"]) / "90 - KageAgent" / "Raw") if result["vault"] else "",
                leafos_export_ic=True,
                leafos_export_ooc=False,
            )
            if result["primary_character"]:
                config = load_config(); set_primary_character(HistoryStore(config.database_path), result["primary_character"])
        else:
            ensure_config()

        # Import the wrapper once, then make the legacy launcher resolve "app" to
        # the unified backend without modifying the proven legacy server code.
        unified_backend = importlib.import_module("unified_app")
        sys.modules["app"] = unified_backend

        root.deiconify(); root.lift()
        try:
            root.attributes("-topmost", True); root.after(700, lambda: root.attributes("-topmost", False))
        except Exception:
            pass
        root.after(100, root.focus_force)
        UnifiedKageLinkAgentUI(root); root.mainloop(); return 0
    finally:
        legacy.release_mutex()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as error:
        path = legacy._write_startup_error(error)
        legacy._show_native_error(
            "KageLink could not start.\n\nKageLink não pôde iniciar.\n\n"
            f"Diagnostic log / Log de diagnóstico:\n{path}"
        )
