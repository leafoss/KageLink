from __future__ import annotations

import argparse
import json
import locale
import os
import re
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from pc_agent.leafos_memory import LeafOSMemoryReviewer
from pc_agent.leafos_memory_support import ReviewerError, _display_candidate


COLORS = {
    "bg": "#07130d",
    "header": "#0a1a12",
    "card": "#0a1911",
    "surface": "#0b1b12",
    "surface_alt": "#0d2116",
    "surface_hover": "#10261a",
    "border": "#1c3b29",
    "border_soft": "#153021",
    "text": "#e8efe9",
    "muted": "#9aa89f",
    "muted_2": "#74877b",
    "accent": "#78d36d",
    "accent_soft": "#a9eba2",
    "selected": "#173a27",
    "disabled": "#536158",
    "button": "#10251a",
    "button_hover": "#173a26",
    "approve": "#1b4627",
    "approve_hover": "#245a32",
    "approve_border": "#4b8a52",
    "edit": "#7a5514",
    "edit_hover": "#91671a",
    "edit_border": "#ae8328",
    "reject": "#7b201b",
    "reject_hover": "#922a23",
    "reject_border": "#a8443b",
}

CATEGORY_COLORS = {
    "events": ("#173821", "#75d36b"),
    "characters": ("#12303a", "#6cc5da"),
    "locations": ("#3b2b12", "#e4bd65"),
    "relationships": ("#3a1c1c", "#e68b83"),
    "lore": ("#2c2138", "#c89be8"),
    "memories": ("#123531", "#7cd8c7"),
}


TEXT = {
    "pt-BR": {
        "title": "LeafOS Memory Reviewer",
        "subtitle": "Revisão humana antes da memória canônica",
        "refresh": "↻  Atualizar",
        "sessions_title": "Sessões pendentes",
        "session": "Sessão",
        "character": "Personagem",
        "pending": "Pend.",
        "primary_label": "Personagem principal",
        "candidates_title": "Candidatos",
        "candidate": "Candidato",
        "category": "Categoria",
        "confidence": "Conf.",
        "perspective": "Perspectiva",
        "detail_title": "Candidato e evidência",
        "selected_candidate": "Candidato selecionado",
        "evidence": "Evidência",
        "raw_json": "RAW JSON",
        "approve": "✓  Aprovar",
        "edit": "✎  Editar + aprovar",
        "reject": "✕  Rejeitar",
        "menu_refresh": "Atualizar",
        "menu_folder": "Abrir pasta da Canonical Memory",
        "menu_json": "Abrir memory.json",
        "menu_md": "Abrir MEMORY.md",
        "menu_language": "Idioma",
        "menu_close": "Fechar Reviewer",
        "lang_pt": "Português (Brasil)",
        "lang_en": "English (US)",
        "instructions": "Selecione uma sessão e um candidato.\n\nA promoção só é liberada quando a evidência chega até o RAW.",
        "invalid_state": "ESTADO DO REVIEWER INVÁLIDO",
        "invalid_state_body": "O processamento foi bloqueado para proteger a memória persistida.",
        "invalid_state_status": "Reviewer bloqueado por estado persistido inválido",
        "count_one": "1 sessão com candidatos pendentes",
        "count_many": "{count} sessões com candidatos pendentes",
        "no_summary": "Sessão sem resumo.",
        "load_error": "Não foi possível carregar os candidatos da sessão",
        "invalid_evidence": "EVIDÊNCIA INVÁLIDA",
        "invalid_evidence_body": "Aprovação bloqueada. Rejeição continua disponível para registrar a decisão humana.",
        "invalid_evidence_status": "Promoção bloqueada; rejeição auditável disponível",
        "evidence_ok": "Evidência validada até o RAW",
        "approve_question": "Promover este candidato para a memória canônica?",
        "approved": "Aprovado: {memory_id}",
        "edit_title": "Editar candidato antes da aprovação",
        "edit_hint": "Edite somente o conteúdo. source_message_ids, confidence e review_status são protegidos.",
        "cancel": "Cancelar",
        "save": "Salvar e aprovar",
        "edited": "Editado e aprovado: {memory_id}",
        "json_object": "O JSON precisa ser um objeto.",
        "reject_question": "Rejeitar este candidato? Ele ficará registrado como revisado.",
        "rejected": "Candidato rejeitado e registrado",
        "path_missing": "Este caminho ainda não existe:\n\n{path}",
        "path_error": "Não foi possível abrir:\n\n{path}\n\n{error}",
        "cat_events": "Eventos",
        "cat_characters": "Personagens",
        "cat_locations": "Locais",
        "cat_relationships": "Relações",
        "cat_lore": "Lore",
        "cat_memories": "Memórias",
        "per_observed": "Observado",
        "per_said": "Dito",
        "per_inferred": "Inferido",
    },
    "en-US": {
        "title": "LeafOS Memory Reviewer",
        "subtitle": "Human review before canonical memory",
        "refresh": "↻  Refresh",
        "sessions_title": "Pending sessions",
        "session": "Session",
        "character": "Character",
        "pending": "Pending",
        "primary_label": "Primary character",
        "candidates_title": "Candidates",
        "candidate": "Candidate",
        "category": "Category",
        "confidence": "Conf.",
        "perspective": "Perspective",
        "detail_title": "Candidate and evidence",
        "selected_candidate": "Selected candidate",
        "evidence": "Evidence",
        "raw_json": "RAW JSON",
        "approve": "✓  Approve",
        "edit": "✎  Edit + approve",
        "reject": "✕  Reject",
        "menu_refresh": "Refresh",
        "menu_folder": "Open Canonical Memory folder",
        "menu_json": "Open memory.json",
        "menu_md": "Open MEMORY.md",
        "menu_language": "Language",
        "menu_close": "Close Reviewer",
        "lang_pt": "Português (Brasil)",
        "lang_en": "English (US)",
        "instructions": "Select a session and a candidate.\n\nPromotion is enabled only when the evidence can be traced back to RAW.",
        "invalid_state": "INVALID REVIEWER STATE",
        "invalid_state_body": "Processing was blocked to protect persisted memory.",
        "invalid_state_status": "Reviewer blocked by invalid persisted state",
        "count_one": "1 session with pending candidates",
        "count_many": "{count} sessions with pending candidates",
        "no_summary": "Session has no summary.",
        "load_error": "Could not load candidates for this session",
        "invalid_evidence": "INVALID EVIDENCE",
        "invalid_evidence_body": "Approval is blocked. Rejection remains available to record the human decision.",
        "invalid_evidence_status": "Promotion blocked; auditable rejection remains available",
        "evidence_ok": "Evidence validated through RAW",
        "approve_question": "Promote this candidate to canonical memory?",
        "approved": "Approved: {memory_id}",
        "edit_title": "Edit candidate before approval",
        "edit_hint": "Edit content only. source_message_ids, confidence and review_status are protected.",
        "cancel": "Cancel",
        "save": "Save and approve",
        "edited": "Edited and approved: {memory_id}",
        "json_object": "The JSON must be an object.",
        "reject_question": "Reject this candidate? It will remain recorded as reviewed.",
        "rejected": "Candidate rejected and recorded",
        "path_missing": "This path does not exist yet:\n\n{path}",
        "path_error": "Could not open:\n\n{path}\n\n{error}",
        "cat_events": "Events",
        "cat_characters": "Characters",
        "cat_locations": "Locations",
        "cat_relationships": "Relationships",
        "cat_lore": "Lore",
        "cat_memories": "Memories",
        "per_observed": "Observed",
        "per_said": "Said",
        "per_inferred": "Inferred",
    },
}

LOGO_PNG_BASE64 = "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"


def _default_language() -> str:
    try:
        current = locale.getlocale()[0] or ""
    except (AttributeError, ValueError):
        current = ""
    return "pt-BR" if current.lower().startswith("pt") else "en-US"


class _ScrollableList(tk.Frame):
    def __init__(self, parent: tk.Widget, *, bg: str, scrollbar_style: str) -> None:
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, borderwidth=0, relief="flat")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style=scrollbar_style)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(2, 0))
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.inner.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._sync_width)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)
        self._scroll_visible = True

    def _sync_scrollregion(self, _event: Any = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.after_idle(self._update_scrollbar_visibility)

    def _sync_width(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=max(int(event.width), 1))
        self.after_idle(self._update_scrollbar_visibility)

    def _on_scroll(self, first: str, last: str) -> None:
        self.scrollbar.set(first, last)
        self.after_idle(self._update_scrollbar_visibility)

    def _update_scrollbar_visibility(self) -> None:
        bbox = self.canvas.bbox("all")
        content_height = 0 if not bbox else bbox[3] - bbox[1]
        viewport = self.canvas.winfo_height()
        should_show = content_height > viewport + 2
        if should_show and not self._scroll_visible:
            self.scrollbar.grid()
            self._scroll_visible = True
        elif not should_show and self._scroll_visible:
            self.scrollbar.grid_remove()
            self._scroll_visible = False

    def _bind_wheel(self, _event: Any = None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._mousewheel)

    def _unbind_wheel(self, _event: Any = None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _mousewheel(self, event: tk.Event) -> None:
        if self._scroll_visible:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def clear(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)
        self.after_idle(self._sync_scrollregion)


class MemoryReviewerApp(tk.Tk):
    def __init__(self, reviewer: LeafOSMemoryReviewer, *, language: str | None = None) -> None:
        super().__init__()
        self.reviewer = reviewer
        self.language = language if language in TEXT else _default_language()
        self.language_var = tk.StringVar(value=self.language)
        self._session_rows: dict[str, dict[str, Any]] = {}
        self._candidate_rows: dict[str, dict[str, Any]] = {}
        self._session_order: list[str] = []
        self._candidate_order: list[str] = []
        self._selected_session_id: str | None = None
        self._selected_candidate_id_value: str | None = None
        self._session_sort = ("session", False)
        self._candidate_sort = ("candidate", False)
        self._menu: tk.Menu | None = None
        self.geometry("1586x992")
        self.minsize(1240, 760)
        self.configure(bg=COLORS["bg"])
        self._configure_styles()
        self._load_brand_image()
        self._build_ui()
        self._apply_language()
        self.refresh()

    def _t(self, key: str, **kwargs: Any) -> str:
        value = TEXT[self.language].get(key, key)
        return value.format(**kwargs) if kwargs else value

    def _count_text(self, count: int) -> str:
        return self._t("count_one") if count == 1 else self._t("count_many", count=count)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Reviewer.Vertical.TScrollbar", background="#193527", troughcolor=COLORS["surface"], bordercolor=COLORS["surface"], arrowcolor=COLORS["muted"], lightcolor="#193527", darkcolor="#193527")
        self._button_style("Refresh.TButton", COLORS["button"], COLORS["button_hover"], "#315d3d", COLORS["text"])
        self._button_style("Approve.TButton", COLORS["approve"], COLORS["approve_hover"], COLORS["approve_border"], "#eff8f0")
        self._button_style("Edit.TButton", COLORS["edit"], COLORS["edit_hover"], COLORS["edit_border"], "#fff2d0")
        self._button_style("Reject.TButton", COLORS["reject"], COLORS["reject_hover"], COLORS["reject_border"], "#ffe6e2")

    def _button_style(self, name: str, normal: str, active: str, border: str, foreground: str) -> None:
        style = ttk.Style(self)
        style.configure(name, padding=(14, 11), background=normal, foreground=foreground, bordercolor=border, lightcolor=border, darkcolor=border, relief="flat", font=("Segoe UI Semibold", 10))
        style.map(name, background=[("disabled", "#151d18"), ("pressed", active), ("active", active)], foreground=[("disabled", COLORS["disabled"])], bordercolor=[("disabled", "#26342b")])

    def _load_brand_image(self) -> None:
        self._logo_image = tk.PhotoImage(data=LOGO_PNG_BASE64)
        try:
            self.iconphoto(True, self._logo_image)
        except tk.TclError:
            pass

    def _card(self, parent: tk.Widget, *, bg: str | None = None) -> tk.Frame:
        return tk.Frame(parent, bg=bg or COLORS["card"], highlightthickness=1, highlightbackground=COLORS["border"])

    def _bind_click(self, widget: tk.Widget, callback: Callable[[], None]) -> None:
        try:
            widget.configure(cursor="hand2")
        except tk.TclError:
            pass
        widget.bind("<Button-1>", lambda _event: callback())
        for child in widget.winfo_children():
            self._bind_click(child, callback)

    def _flat_header(self, parent: tk.Widget, *, key: str, column: str, target: str, anchor: str = "w") -> tk.Label:
        label = tk.Label(parent, text="", bg=COLORS["surface_alt"], fg=COLORS["text"], font=("Segoe UI", 9), anchor=anchor, padx=6, pady=8, cursor="hand2")
        label.bind("<Button-1>", lambda _event: self._sort_rows(target, column))
        setattr(label, "_text_key", key)
        return label

    def _section_title(self, parent: tk.Widget, icon: str) -> tuple[tk.Frame, tk.Label]:
        row = tk.Frame(parent, bg=COLORS["surface"])
        tk.Label(row, text=icon, bg=COLORS["surface"], fg=COLORS["accent"], font=("Segoe UI Symbol", 15)).pack(side="left", padx=(0, 8))
        label = tk.Label(row, text="", bg=COLORS["surface"], fg=COLORS["text"], font=("Segoe UI Semibold", 11), anchor="w")
        label.pack(side="left", fill="x", expand=True)
        return row, label

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=COLORS["header"])
        header.pack(fill="x", padx=14, pady=(12, 10))
        brand = tk.Frame(header, bg=COLORS["header"])
        brand.pack(side="left", fill="x", expand=True, padx=(4, 0), pady=3)
        self.logo_label = tk.Label(brand, image=self._logo_image, bg=COLORS["header"], borderwidth=0, highlightthickness=0)
        self.logo_label.pack(side="left", padx=(0, 15))
        title_box = tk.Frame(brand, bg=COLORS["header"])
        title_box.pack(side="left", fill="x", expand=True, pady=(4, 0))
        self.title_label = tk.Label(title_box, text="", bg=COLORS["header"], fg=COLORS["text"], font=("Segoe UI Semibold", 22))
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(title_box, text="", bg=COLORS["header"], fg=COLORS["muted"], font=("Segoe UI", 10))
        self.subtitle_label.pack(anchor="w", pady=(3, 0))
        header_actions = tk.Frame(header, bg=COLORS["header"])
        header_actions.pack(side="right", padx=(0, 7), pady=19)
        self.refresh_button = ttk.Button(header_actions, text="", command=self.refresh, style="Refresh.TButton")
        self.refresh_button.pack(side="left", padx=(0, 18))
        self.menu_button = tk.Button(header_actions, text="⋮", command=self._show_menu, width=3, bg=COLORS["button"], fg=COLORS["text"], activebackground=COLORS["button_hover"], activeforeground=COLORS["accent_soft"], relief="flat", bd=0, highlightthickness=1, highlightbackground=COLORS["border_soft"], cursor="hand2", font=("Segoe UI Semibold", 14), padx=8, pady=7)
        self.menu_button.pack(side="left")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=(0, 13))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=23, minsize=330)
        body.grid_columnconfigure(1, weight=77, minsize=820)

        left = self._card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)
        left_title = tk.Frame(left, bg=COLORS["card"])
        left_title.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))
        tk.Label(left_title, text="●", bg=COLORS["card"], fg=COLORS["accent"], font=("Segoe UI", 12)).pack(side="left", padx=(0, 8))
        self.sessions_title = tk.Label(left_title, text="", bg=COLORS["card"], fg=COLORS["text"], font=("Segoe UI Semibold", 11))
        self.sessions_title.pack(side="left")
        self.sessions_header = tk.Frame(left, bg=COLORS["surface_alt"], highlightthickness=1, highlightbackground=COLORS["border_soft"])
        self.sessions_header.grid(row=1, column=0, sticky="ew", padx=12)
        self.sessions_header.grid_columnconfigure(0, weight=42, uniform="sessions")
        self.sessions_header.grid_columnconfigure(1, weight=38, uniform="sessions")
        self.sessions_header.grid_columnconfigure(2, minsize=82)
        self.session_h = self._flat_header(self.sessions_header, key="session", column="session", target="session")
        self.character_h = self._flat_header(self.sessions_header, key="character", column="character", target="session")
        self.pending_h = self._flat_header(self.sessions_header, key="pending", column="pending", target="session", anchor="center")
        self.session_h.grid(row=0, column=0, sticky="ew")
        self.character_h.grid(row=0, column=1, sticky="ew")
        self.pending_h.grid(row=0, column=2, sticky="ew")
        self.sessions_list = _ScrollableList(left, bg=COLORS["surface"], scrollbar_style="Reviewer.Vertical.TScrollbar")
        self.sessions_list.grid(row=2, column=0, sticky="nsew", padx=12)
        self.pending_status = tk.Label(left, text="", anchor="w", bg=COLORS["card"], fg=COLORS["muted"], font=("Segoe UI", 9))
        self.pending_status.grid(row=3, column=0, sticky="ew", padx=15, pady=(8, 12))

        workspace = self._card(body)
        workspace.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        workspace.grid_rowconfigure(1, weight=1)
        workspace.grid_columnconfigure(0, weight=1)
        primary = tk.Frame(workspace, bg=COLORS["card"])
        primary.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 11))
        tk.Label(primary, text="♟", bg=COLORS["card"], fg=COLORS["muted"], font=("Segoe UI Symbol", 14)).pack(side="left", padx=(0, 9))
        self.primary_caption = tk.Label(primary, text="", bg=COLORS["card"], fg=COLORS["muted"], font=("Segoe UI", 10))
        self.primary_caption.pack(side="left")
        self.primary_label = tk.Label(primary, text="—", bg=COLORS["card"], fg=COLORS["accent"], font=("Segoe UI Semibold", 10))
        self.primary_label.pack(side="left", padx=(5, 0))

        panes = tk.Frame(workspace, bg=COLORS["card"])
        panes.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        panes.grid_rowconfigure(0, weight=1)
        panes.grid_columnconfigure(0, weight=51, minsize=470)
        panes.grid_columnconfigure(1, weight=49, minsize=430)
        middle = self._card(panes, bg=COLORS["surface"])
        right = self._card(panes, bg=COLORS["surface"])
        middle.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        middle.grid_rowconfigure(2, weight=1)
        middle.grid_columnconfigure(0, weight=1)
        cand_title_row, self.candidates_title = self._section_title(middle, "▣")
        cand_title_row.grid(row=0, column=0, sticky="ew", padx=13, pady=(13, 9))
        self.candidate_header = tk.Frame(middle, bg=COLORS["surface_alt"], highlightthickness=1, highlightbackground=COLORS["border_soft"])
        self.candidate_header.grid(row=1, column=0, sticky="ew", padx=12)
        self.candidate_header.grid_columnconfigure(0, minsize=34)
        self.candidate_header.grid_columnconfigure(1, weight=55)
        self.candidate_header.grid_columnconfigure(2, minsize=108)
        self.candidate_header.grid_columnconfigure(3, minsize=82)
        self.candidate_header.grid_columnconfigure(4, minsize=112)
        tk.Label(self.candidate_header, text="", bg=COLORS["surface_alt"]).grid(row=0, column=0, sticky="ew")
        self.candidate_h = self._flat_header(self.candidate_header, key="candidate", column="candidate", target="candidate")
        self.category_h = self._flat_header(self.candidate_header, key="category", column="category", target="candidate")
        self.confidence_h = self._flat_header(self.candidate_header, key="confidence", column="confidence", target="candidate", anchor="center")
        self.perspective_h = self._flat_header(self.candidate_header, key="perspective", column="perspective", target="candidate", anchor="center")
        self.candidate_h.grid(row=0, column=1, sticky="ew")
        self.category_h.grid(row=0, column=2, sticky="ew")
        self.confidence_h.grid(row=0, column=3, sticky="ew")
        self.perspective_h.grid(row=0, column=4, sticky="ew")
        self.candidates_list = _ScrollableList(middle, bg=COLORS["surface"], scrollbar_style="Reviewer.Vertical.TScrollbar")
        self.candidates_list.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))

        right.grid_rowconfigure(3, weight=1)
        right.grid_columnconfigure(0, weight=1)
        detail_title_row, self.detail_title = self._section_title(right, "▤")
        detail_title_row.grid(row=0, column=0, sticky="ew", padx=13, pady=(13, 9))
        self.selected_card = tk.Frame(right, bg=COLORS["surface_alt"], highlightthickness=1, highlightbackground=COLORS["border"])
        self.selected_card.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.selected_caption = tk.Label(self.selected_card, text="", bg=COLORS["surface_alt"], fg=COLORS["muted"], font=("Segoe UI", 9), anchor="w")
        self.selected_caption.pack(fill="x", padx=13, pady=(10, 3))
        selected_line = tk.Frame(self.selected_card, bg=COLORS["surface_alt"])
        selected_line.pack(fill="x", padx=13, pady=(0, 11))
        self.selected_badge = tk.Canvas(selected_line, width=24, height=24, bg=COLORS["surface_alt"], highlightthickness=0)
        self.selected_badge.pack(side="left", padx=(0, 9))
        self.selected_badge.create_oval(2, 2, 22, 22, fill=COLORS["accent"], outline="")
        self.selected_badge_text = self.selected_badge.create_text(12, 12, text="—", fill="#102015", font=("Segoe UI Semibold", 9))
        self.selected_title = tk.Label(selected_line, text="—", bg=COLORS["surface_alt"], fg=COLORS["accent"], font=("Segoe UI Semibold", 10), anchor="w")
        self.selected_title.pack(side="left", fill="x", expand=True)
        tk.Label(selected_line, text="⌄", bg=COLORS["surface_alt"], fg=COLORS["muted"], font=("Segoe UI", 11)).pack(side="right")

        evidence_card = tk.Frame(right, bg=COLORS["surface"], highlightthickness=1, highlightbackground=COLORS["border"])
        evidence_card.grid(row=2, column=0, rowspan=2, sticky="nsew", padx=12, pady=(0, 12))
        evidence_card.grid_rowconfigure(1, weight=1)
        evidence_card.grid_columnconfigure(0, weight=1)
        evidence_header = tk.Frame(evidence_card, bg=COLORS["surface_alt"])
        evidence_header.grid(row=0, column=0, sticky="ew")
        self.evidence_title = tk.Label(evidence_header, text="", bg=COLORS["surface_alt"], fg=COLORS["text"], font=("Segoe UI Semibold", 10))
        self.evidence_title.pack(side="left", padx=13, pady=10)
        self.raw_json_label = tk.Label(evidence_header, text="", bg=COLORS["surface_alt"], fg=COLORS["muted"], font=("Consolas", 9))
        self.raw_json_label.pack(side="right", padx=13, pady=10)
        self.detail = ScrolledText(evidence_card, bg=COLORS["surface"], fg=COLORS["text"], insertbackground=COLORS["accent"], selectbackground=COLORS["selected"], selectforeground=COLORS["text"], relief="flat", borderwidth=0, font=("Consolas", 9), wrap="word", padx=12, pady=10)
        self.detail.grid(row=1, column=0, sticky="nsew")
        self.detail.tag_configure("key", foreground="#9cc6e7")
        self.detail.tag_configure("string", foreground="#e7a873")
        self.detail.tag_configure("number", foreground="#e4c86f")
        self.detail.tag_configure("bool", foreground="#8ed18a")
        self.detail.tag_configure("plain", foreground=COLORS["text"])
        self.detail.configure(state="disabled")
        actions = tk.Frame(right, bg=COLORS["surface"])
        actions.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))
        for column in range(3):
            actions.grid_columnconfigure(column, weight=1)
        self.approve_button = ttk.Button(actions, text="", command=self._approve, state="disabled", style="Approve.TButton")
        self.edit_button = ttk.Button(actions, text="", command=self._edit_and_approve, state="disabled", style="Edit.TButton")
        self.reject_button = ttk.Button(actions, text="", command=self._reject, state="disabled", style="Reject.TButton")
        self.approve_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.edit_button.grid(row=0, column=1, sticky="ew", padx=6)
        self.reject_button.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self.status = tk.Label(self, text="", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 9))
        self.status.pack(fill="x", padx=17, pady=(0, 9))

    def _sort_rows(self, target: str, column: str) -> None:
        if target == "session":
            current_col, reverse = self._session_sort
            reverse = not reverse if current_col == column else False
            self._session_sort = (column, reverse)
            def session_key(session_id: str) -> Any:
                row = self._session_rows[session_id]
                if column == "pending": return int(row.get("pending_count", 0))
                if column == "character": return str(row.get("primary_character") or "").casefold()
                return session_id.casefold()
            self._session_order.sort(key=session_key, reverse=reverse)
            self._render_sessions()
            return
        current_col, reverse = self._candidate_sort
        reverse = not reverse if current_col == column else False
        self._candidate_sort = (column, reverse)
        def candidate_key(candidate_id: str) -> Any:
            row = self._candidate_rows[candidate_id]
            if column == "confidence":
                value = row.get("confidence")
                return float(value) if isinstance(value, (int, float)) else -1.0
            if column == "category": return self._display_category(row.get("canonical_category")).casefold()
            if column == "perspective": return self._display_perspective(row.get("perspective")).casefold()
            return _display_candidate(row["candidate"]).casefold()
        self._candidate_order.sort(key=candidate_key, reverse=reverse)
        self._render_candidates()

    def _build_menu(self) -> None:
        menu_options = {"tearoff": False, "bg": COLORS["surface_alt"], "fg": COLORS["text"], "activebackground": COLORS["selected"], "activeforeground": COLORS["accent_soft"], "relief": "flat", "borderwidth": 1}
        menu = tk.Menu(self, **menu_options)
        menu.add_command(label=self._t("menu_refresh"), command=self.refresh)
        menu.add_separator()
        menu.add_command(label=self._t("menu_folder"), command=lambda: self._open_path(self.reviewer.canonical_root))
        menu.add_command(label=self._t("menu_json"), command=lambda: self._open_path(self.reviewer.canonical_memory_path))
        menu.add_command(label=self._t("menu_md"), command=lambda: self._open_path(self.reviewer.canonical_markdown_path))
        menu.add_separator()
        language = tk.Menu(menu, **menu_options)
        language.add_radiobutton(label=self._t("lang_pt"), variable=self.language_var, value="pt-BR", command=lambda: self._set_language(self.language_var.get()))
        language.add_radiobutton(label=self._t("lang_en"), variable=self.language_var, value="en-US", command=lambda: self._set_language(self.language_var.get()))
        menu.add_cascade(label=self._t("menu_language"), menu=language)
        menu.add_separator()
        menu.add_command(label=self._t("menu_close"), command=self.destroy)
        self._menu = menu

    def _show_menu(self) -> None:
        if self._menu is None: self._build_menu()
        if self._menu is None: return
        x = self.menu_button.winfo_rootx() + self.menu_button.winfo_width() - 2
        y = self.menu_button.winfo_rooty() + self.menu_button.winfo_height() + 3
        try: self._menu.tk_popup(x, y)
        finally: self._menu.grab_release()

    def _apply_language(self) -> None:
        self.title(self._t("title"))
        self.title_label.configure(text=self._t("title"))
        self.subtitle_label.configure(text=self._t("subtitle"))
        self.refresh_button.configure(text=self._t("refresh"))
        self.sessions_title.configure(text=self._t("sessions_title"))
        self.primary_caption.configure(text=f"{self._t('primary_label')}:")
        self.candidates_title.configure(text=self._t("candidates_title"))
        self.detail_title.configure(text=self._t("detail_title"))
        self.selected_caption.configure(text=self._t("selected_candidate"))
        self.evidence_title.configure(text=f"</>  {self._t('evidence')}")
        self.raw_json_label.configure(text="{}  " + self._t("raw_json"))
        self.approve_button.configure(text=self._t("approve"))
        self.edit_button.configure(text=self._t("edit"))
        self.reject_button.configure(text=self._t("reject"))
        for widget in (self.session_h, self.character_h, self.pending_h, self.candidate_h, self.category_h, self.confidence_h, self.perspective_h):
            key = getattr(widget, "_text_key", "")
            widget.configure(text=self._t(key))
        self._build_menu()
        self._render_sessions()
        self._render_candidates()

    def _set_language(self, language: str) -> None:
        if language not in TEXT: return
        self.language = language
        self.language_var.set(language)
        self._apply_language()
        self.refresh()

    def _display_category(self, category: Any) -> str:
        value = str(category or "")
        key = f"cat_{value}"
        return self._t(key) if key in TEXT[self.language] else value

    def _display_perspective(self, perspective: Any) -> str:
        value = str(perspective or "").strip()
        if not value: return "—"
        key = f"per_{value}"
        return self._t(key) if key in TEXT[self.language] else value

    def _candidate_summary(self, candidate: dict[str, Any]) -> str:
        for key in ("description", "statement", "summary", "text", "content"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip(): return value.strip()
        return _display_candidate(candidate)

    def _open_path(self, path: Path) -> None:
        path = Path(path)
        if not path.exists():
            messagebox.showinfo("LeafOS Reviewer", self._t("path_missing", path=path), parent=self)
            return
        try: os.startfile(str(path))
        except (AttributeError, OSError) as error:
            messagebox.showerror("LeafOS Reviewer", self._t("path_error", path=path, error=error), parent=self)

    def _render_sessions(self) -> None:
        if not hasattr(self, "sessions_list"): return
        self.sessions_list.clear()
        for session_id in self._session_order:
            row = self._session_rows[session_id]
            selected = session_id == self._selected_session_id
            bg = COLORS["selected"] if selected else COLORS["surface"]
            item = tk.Frame(self.sessions_list.inner, bg=bg, highlightthickness=1 if selected else 0, highlightbackground=COLORS["border"])
            item.pack(fill="x")
            item.grid_columnconfigure(0, weight=42, uniform="sessionrow")
            item.grid_columnconfigure(1, weight=38, uniform="sessionrow")
            item.grid_columnconfigure(2, minsize=82)
            session_box = tk.Frame(item, bg=bg)
            session_box.grid(row=0, column=0, sticky="ew", padx=(7, 2), pady=10)
            tk.Label(session_box, text="●", bg=bg, fg=COLORS["accent"], font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
            tk.Label(session_box, text=session_id, bg=bg, fg=COLORS["accent"] if selected else COLORS["text"], font=("Segoe UI Semibold" if selected else "Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(item, text=row.get("primary_character") or "—", bg=bg, fg=COLORS["text"], font=("Segoe UI", 9), anchor="w", padx=5).grid(row=0, column=1, sticky="ew")
            tk.Label(item, text=str(row.get("pending_count", 0)), bg=bg, fg=COLORS["accent_soft"], font=("Segoe UI", 9), anchor="center").grid(row=0, column=2, sticky="ew")
            self._bind_click(item, lambda sid=session_id: self._select_session(sid))
        self.sessions_list.after_idle(self.sessions_list._sync_scrollregion)

    def _category_pill(self, parent: tk.Widget, category: str) -> tk.Label:
        bg, fg = CATEGORY_COLORS.get(category, ("#173022", COLORS["accent_soft"]))
        return tk.Label(parent, text=self._display_category(category), bg=bg, fg=fg, font=("Segoe UI", 9), padx=10, pady=5)

    def _render_candidates(self) -> None:
        if not hasattr(self, "candidates_list"): return
        self.candidates_list.clear()
        for index, candidate_id in enumerate(self._candidate_order, start=1):
            record = self._candidate_rows[candidate_id]
            selected = candidate_id == self._selected_candidate_id_value
            bg = COLORS["surface_hover"] if selected else COLORS["surface"]
            category = str(record.get("canonical_category") or "")
            _pill_bg, badge_color = CATEGORY_COLORS.get(category, ("#173022", COLORS["accent"]))
            item = tk.Frame(self.candidates_list.inner, bg=bg, highlightthickness=1 if selected else 0, highlightbackground=COLORS["accent"] if selected else COLORS["border_soft"])
            item.pack(fill="x")
            item.grid_columnconfigure(0, minsize=34)
            item.grid_columnconfigure(1, weight=55)
            item.grid_columnconfigure(2, minsize=108)
            item.grid_columnconfigure(3, minsize=82)
            item.grid_columnconfigure(4, minsize=112)
            badge = tk.Canvas(item, width=30, height=30, bg=bg, highlightthickness=0)
            badge.grid(row=0, column=0, sticky="n", padx=(7, 0), pady=(14, 0))
            badge.create_oval(4, 4, 26, 26, fill=badge_color, outline="")
            badge.create_text(15, 15, text=str(index), fill="#122016", font=("Segoe UI Semibold", 9))
            content = tk.Frame(item, bg=bg)
            content.grid(row=0, column=1, sticky="nsew", padx=(5, 8), pady=11)
            tk.Label(content, text=_display_candidate(record["candidate"]), bg=bg, fg=COLORS["text"], font=("Segoe UI Semibold", 10), anchor="w", justify="left", wraplength=310).pack(fill="x")
            tk.Label(content, text=self._candidate_summary(record["candidate"]), bg=bg, fg=COLORS["muted"], font=("Segoe UI", 9), anchor="w", justify="left", wraplength=310).pack(fill="x", pady=(6, 0))
            pill_holder = tk.Frame(item, bg=bg)
            pill_holder.grid(row=0, column=2, sticky="nsew", padx=5, pady=12)
            self._category_pill(pill_holder, category).pack(anchor="center", pady=(22, 0))
            confidence = record.get("confidence")
            confidence_text = f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "—"
            tk.Label(item, text=confidence_text, bg=bg, fg=COLORS["accent_soft"], font=("Segoe UI", 10), anchor="center").grid(row=0, column=3, sticky="nsew")
            tk.Label(item, text=self._display_perspective(record.get("perspective")), bg=bg, fg=COLORS["text"], font=("Segoe UI", 9), anchor="center").grid(row=0, column=4, sticky="nsew")
            tk.Frame(item, bg=COLORS["border_soft"], height=1).grid(row=1, column=0, columnspan=5, sticky="ew")
            self._bind_click(item, lambda cid=candidate_id: self._select_candidate(cid))
        self.candidates_list.after_idle(self.candidates_list._sync_scrollregion)

    def _set_selected_candidate_card(self, candidate_id: str | None) -> None:
        if not candidate_id or candidate_id not in self._candidate_rows:
            self.selected_title.configure(text="—", fg=COLORS["muted"])
            self.selected_badge.itemconfigure(self.selected_badge_text, text="—")
            return
        try: index = self._candidate_order.index(candidate_id) + 1
        except ValueError: index = 1
        record = self._candidate_rows[candidate_id]
        self.selected_badge.itemconfigure(self.selected_badge_text, text=str(index))
        self.selected_title.configure(text=_display_candidate(record["candidate"]), fg=COLORS["accent"])

    def _set_detail_text(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text, "plain")
        self.detail.configure(state="disabled")

    def _render_json(self, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text, "plain")
        for match in re.finditer(r'"(?:\\.|[^"\\])*"(?=\s*:)', text): self.detail.tag_add("key", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
        for match in re.finditer(r':\s*("(?:\\.|[^"\\])*")', text):
            start, end = match.span(1); self.detail.tag_add("string", f"1.0+{start}c", f"1.0+{end}c")
        for match in re.finditer(r'\b-?\d+(?:\.\d+)?\b', text): self.detail.tag_add("number", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
        for match in re.finditer(r'\b(?:true|false|null)\b', text): self.detail.tag_add("bool", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
        self.detail.configure(state="disabled")

    def refresh(self) -> None:
        previous_session = self._selected_session_id
        previous_candidate = self._selected_candidate_id_value
        self._session_rows.clear(); self._session_order.clear(); self._candidate_rows.clear(); self._candidate_order.clear(); self._selected_candidate_id_value = None
        try: sessions = self.reviewer.list_sessions()
        except ReviewerError as error:
            self.primary_label.configure(text="—", fg=COLORS["muted"])
            self._set_detail_text(f"{self._t('invalid_state')}\n\n{error}\n\n{self._t('invalid_state_body')}")
            self._set_action_state(False); self.pending_status.configure(text=""); self.status.configure(text=self._t("invalid_state_status")); messagebox.showerror("LeafOS Reviewer", str(error), parent=self); return
        for row in sessions:
            session_id = row["session_id"]; self._session_rows[session_id] = row; self._session_order.append(session_id)
        self._render_sessions()
        count = self._count_text(len(sessions))
        self.pending_status.configure(text=f"●  {count}", fg=COLORS["accent"] if sessions else COLORS["muted"])
        self.status.configure(text=count); self.primary_label.configure(text="—", fg=COLORS["muted"]); self._set_selected_candidate_card(None); self._set_detail_text(self._t("instructions")); self._set_action_state(False)
        if previous_session and previous_session in self._session_rows: self._select_session(previous_session, preserve_candidate=previous_candidate)

    def _set_action_state(self, promote: bool, *, reject: bool | None = None) -> None:
        self.approve_button.configure(state="normal" if promote else "disabled"); self.edit_button.configure(state="normal" if promote else "disabled")
        allow_reject = promote if reject is None else reject; self.reject_button.configure(state="normal" if allow_reject else "disabled")

    def _select_session(self, session_id: str, *, preserve_candidate: str | None = None) -> None:
        if session_id not in self._session_rows: return
        self._selected_session_id = session_id; self._render_sessions(); row = self._session_rows[session_id]
        primary = row.get("primary_character") or "—"; self.primary_label.configure(text=primary, fg=COLORS["accent"] if row.get("primary_character") else COLORS["muted"])
        self._candidate_rows.clear(); self._candidate_order.clear(); self._selected_candidate_id_value = None
        try: candidates = self.reviewer.list_candidates(session_id)
        except ReviewerError as error: messagebox.showerror("LeafOS Reviewer", str(error), parent=self); self.status.configure(text=self._t("load_error")); return
        for candidate in candidates:
            candidate_id = candidate["candidate_id"]; self._candidate_rows[candidate_id] = candidate; self._candidate_order.append(candidate_id)
        self._render_candidates(); self._set_selected_candidate_card(None); self._set_detail_text(row.get("summary") or self._t("no_summary")); self._set_action_state(False)
        if preserve_candidate and preserve_candidate in self._candidate_rows: self._select_candidate(preserve_candidate)

    def _selected_candidate_id(self) -> str | None:
        return self._selected_candidate_id_value

    def _select_candidate(self, candidate_id: str) -> None:
        if candidate_id not in self._candidate_rows: return
        self._selected_candidate_id_value = candidate_id; self._render_candidates(); self._set_selected_candidate_card(candidate_id)
        try: detail = self.reviewer.candidate_detail(candidate_id)
        except ReviewerError as error:
            self._set_detail_text(f"{self._t('invalid_evidence')}\n\n{error}\n\n{self._t('invalid_evidence_body')}"); self._set_action_state(False, reject=True); self.status.configure(text=self._t("invalid_evidence_status")); return
        payload = {"candidate_id": candidate_id, "session_id": detail["session_id"], "category": detail["category"], "canonical_category": detail["canonical_category"], "primary_character": detail.get("primary_character"), "candidate": detail["candidate"], "processor_session": detail["processor_session"], "bundle_path": detail["bundle_path"], "evidence": detail["evidence"]}
        self._render_json(payload); self._set_action_state(True); self.status.configure(text=self._t("evidence_ok"))

    def _approve(self) -> None:
        candidate_id = self._selected_candidate_id()
        if not candidate_id or not messagebox.askyesno("LeafOS Reviewer", self._t("approve_question"), parent=self): return
        try: entry = self.reviewer.approve(candidate_id)
        except ReviewerError as error: messagebox.showerror("LeafOS Reviewer", str(error), parent=self); return
        self.status.configure(text=self._t("approved", memory_id=entry["memory_id"])); self.refresh()

    def _edit_and_approve(self) -> None:
        candidate_id = self._selected_candidate_id()
        if not candidate_id: return
        record = self._candidate_rows.get(candidate_id)
        if not record: return
        original = deepcopy(record["candidate"])
        dialog = tk.Toplevel(self); dialog.title(self._t("edit_title")); dialog.geometry("780x580"); dialog.minsize(680, 480); dialog.configure(bg=COLORS["card"]); dialog.transient(self); dialog.grab_set()
        tk.Label(dialog, text=self._t("edit_hint"), anchor="w", bg=COLORS["card"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(fill="x", padx=14, pady=(14, 7))
        editor_border = tk.Frame(dialog, bg=COLORS["surface"], highlightthickness=1, highlightbackground=COLORS["border"]); editor_border.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        editor = ScrolledText(editor_border, bg=COLORS["surface"], fg=COLORS["text"], insertbackground=COLORS["accent"], selectbackground=COLORS["selected"], selectforeground=COLORS["text"], relief="flat", borderwidth=0, font=("Consolas", 10), wrap="none", padx=10, pady=10); editor.pack(fill="both", expand=True); editor.insert("1.0", json.dumps(original, ensure_ascii=False, indent=2))
        result: dict[str, Any] = {"saved": False}
        def save() -> None:
            try:
                decoded = json.loads(editor.get("1.0", "end"))
                if not isinstance(decoded, dict): raise ValueError(self._t("json_object"))
                entry = self.reviewer.approve(candidate_id, edited_candidate=decoded)
            except (json.JSONDecodeError, ValueError, ReviewerError) as error: messagebox.showerror("LeafOS Reviewer", str(error), parent=dialog); return
            result.update(saved=True, memory_id=entry["memory_id"]); dialog.destroy()
        footer = tk.Frame(dialog, bg=COLORS["card"]); footer.pack(fill="x", padx=14, pady=(2, 14))
        ttk.Button(footer, text=self._t("cancel"), command=dialog.destroy, style="Refresh.TButton").pack(side="right")
        ttk.Button(footer, text=self._t("save"), command=save, style="Edit.TButton").pack(side="right", padx=8)
        self.wait_window(dialog)
        if result.get("saved"): self.status.configure(text=self._t("edited", memory_id=result.get("memory_id"))); self.refresh()

    def _reject(self) -> None:
        candidate_id = self._selected_candidate_id()
        if not candidate_id or not messagebox.askyesno("LeafOS Reviewer", self._t("reject_question"), parent=self): return
        try: self.reviewer.reject(candidate_id)
        except ReviewerError as error: messagebox.showerror("LeafOS Reviewer", str(error), parent=self); return
        self.status.configure(text=self._t("rejected")); self.refresh()


def main() -> int:
    parser = argparse.ArgumentParser(description="Review LeafOS Interpreter candidates and promote human-approved canonical memory.")
    parser.add_argument("--vault", required=True, help="Path to the LeafOS Obsidian vault")
    parser.add_argument("--list", action="store_true", help="Print pending sessions as JSON instead of opening the UI")
    parser.add_argument("--lang", choices=("pt-BR", "en-US"), default=None, help="Reviewer UI language. Defaults to the operating-system locale.")
    args = parser.parse_args()
    reviewer = LeafOSMemoryReviewer(Path(args.vault))
    if args.list:
        print(json.dumps(reviewer.list_sessions(), ensure_ascii=False, indent=2, default=str)); return 0
    app = MemoryReviewerApp(reviewer, language=args.lang); app.mainloop(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
