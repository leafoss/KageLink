from __future__ import annotations

import argparse
import json
import locale
import os
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from pc_agent.leafos_memory import LeafOSMemoryReviewer
from pc_agent.leafos_memory_support import ReviewerError, _display_candidate


COLORS = {
    "bg": "#07110c",
    "header": "#08170f",
    "card": "#0a1911",
    "surface": "#08150e",
    "surface_alt": "#0d2116",
    "border": "#1c3b29",
    "border_soft": "#153021",
    "text": "#e7efe9",
    "muted": "#8ca095",
    "accent": "#72cf68",
    "accent_soft": "#a9eba2",
    "selected": "#153a27",
    "disabled": "#536158",
    "button": "#10251a",
    "button_hover": "#173a26",
    "approve": "#173821",
    "approve_border": "#3e7847",
    "edit": "#2b2412",
    "edit_border": "#8f7027",
    "reject": "#2b1715",
    "reject_border": "#88423a",
}


TEXT = {
    "pt-BR": {
        "title": "LeafOS Memory Reviewer v1",
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
        "title": "LeafOS Memory Reviewer v1",
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


def _default_language() -> str:
    try:
        current = locale.getlocale()[0] or ""
    except (AttributeError, ValueError):
        current = ""
    return "pt-BR" if current.lower().startswith("pt") else "en-US"


class MemoryReviewerApp(tk.Tk):
    def __init__(self, reviewer: LeafOSMemoryReviewer, *, language: str | None = None) -> None:
        super().__init__()
        self.reviewer = reviewer
        self.language = language if language in TEXT else _default_language()
        self.language_var = tk.StringVar(value=self.language)
        self._session_rows: dict[str, dict[str, Any]] = {}
        self._candidate_rows: dict[str, dict[str, Any]] = {}
        self._sort_reverse: dict[tuple[str, str], bool] = {}
        self._headings: list[tuple[ttk.Treeview, str, str, bool, str]] = []
        self._tree_layouts: list[tuple[ttk.Treeview, tuple[tuple[str, float], ...]]] = []
        self._menu: tk.Menu | None = None

        self.geometry("1380x800")
        self.minsize(1160, 680)
        self.configure(bg=COLORS["bg"])
        self._configure_styles()
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

        style.configure(
            "Reviewer.Treeview",
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border_soft"],
            lightcolor=COLORS["border_soft"],
            darkcolor=COLORS["border_soft"],
            relief="flat",
            borderwidth=0,
            rowheight=34,
            font=("Segoe UI", 9),
        )
        style.map(
            "Reviewer.Treeview",
            background=[("selected", COLORS["selected"])],
            foreground=[("selected", COLORS["accent_soft"])],
        )
        style.configure(
            "Reviewer.Treeview.Heading",
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border_soft"],
            lightcolor=COLORS["border_soft"],
            darkcolor=COLORS["border_soft"],
            relief="flat",
            padding=(8, 9),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Reviewer.Treeview.Heading",
            background=[("active", "#13301f")],
            foreground=[("active", COLORS["accent_soft"])],
        )
        style.configure(
            "Reviewer.Vertical.TScrollbar",
            background="#183224",
            troughcolor=COLORS["surface"],
            bordercolor=COLORS["surface"],
            arrowcolor=COLORS["muted"],
            lightcolor="#183224",
            darkcolor="#183224",
        )

        self._button_style("Refresh.TButton", COLORS["button"], COLORS["button_hover"], "#315d3d", COLORS["text"])
        self._button_style("Approve.TButton", COLORS["approve"], "#214b2c", COLORS["approve_border"], "#dff5df")
        self._button_style("Edit.TButton", COLORS["edit"], "#3b3014", COLORS["edit_border"], "#f2df9e")
        self._button_style("Reject.TButton", COLORS["reject"], "#421e1a", COLORS["reject_border"], "#f2b4ae")

    @staticmethod
    def _style_map(style: ttk.Style, name: str, active: str) -> None:
        style.map(
            name,
            background=[("disabled", "#151d18"), ("pressed", active), ("active", active)],
            foreground=[("disabled", COLORS["disabled"])],
            bordercolor=[("disabled", "#26342b")],
        )

    def _button_style(self, name: str, normal: str, active: str, border: str, foreground: str) -> None:
        style = ttk.Style(self)
        style.configure(
            name,
            padding=(12, 8),
            background=normal,
            foreground=foreground,
            bordercolor=border,
            lightcolor=border,
            darkcolor=border,
            relief="flat",
            font=("Segoe UI Semibold", 9),
        )
        self._style_map(style, name, active)

    def _card(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=COLORS["card"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )

    def _section_header(self, parent: tk.Widget) -> tk.Label:
        row = tk.Frame(parent, bg=COLORS["card"])
        row.pack(fill="x", padx=13, pady=(12, 9))
        tk.Frame(row, bg=COLORS["accent"], width=3, height=17).pack(side="left", padx=(0, 8))
        label = tk.Label(
            row,
            text="",
            anchor="w",
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 11),
        )
        label.pack(side="left", fill="x", expand=True)
        return label

    def _draw_logo(self, canvas: tk.Canvas) -> None:
        """Draw a restrained LeafOS product mark using native vector primitives."""
        canvas.delete("all")
        canvas.create_oval(3, 3, 49, 49, fill="#0d2417", outline="#2e6040", width=1)
        canvas.create_oval(7, 7, 45, 45, outline="#173b27", width=1)

        leaf_points = (
            14, 31,
            13, 23,
            17, 16,
            25, 11,
            35, 12,
            40, 18,
            39, 27,
            34, 35,
            25, 40,
            18, 38,
        )
        canvas.create_polygon(
            *leaf_points,
            smooth=True,
            splinesteps=28,
            fill="#143921",
            outline=COLORS["accent"],
            width=2,
        )
        canvas.create_line(17, 35, 22, 30, 28, 24, 34, 17, smooth=True, fill="#9be892", width=2)
        canvas.create_line(24, 28, 20, 23, fill="#4d8f55", width=1)
        canvas.create_line(29, 23, 34, 24, fill="#4d8f55", width=1)
        canvas.create_oval(24, 23, 27, 26, fill="#c7f5c2", outline="")

    def _build_ui(self) -> None:
        header = tk.Frame(
            self,
            bg=COLORS["header"],
            highlightthickness=1,
            highlightbackground=COLORS["border_soft"],
        )
        header.pack(fill="x", padx=12, pady=(12, 9))

        brand = tk.Frame(header, bg=COLORS["header"])
        brand.pack(side="left", fill="x", expand=True, padx=15, pady=12)

        self.logo = tk.Canvas(brand, width=52, height=52, bg=COLORS["header"], highlightthickness=0)
        self.logo.pack(side="left", padx=(0, 13))
        self._draw_logo(self.logo)

        title_box = tk.Frame(brand, bg=COLORS["header"])
        title_box.pack(side="left", fill="x", expand=True)
        self.title_label = tk.Label(
            title_box,
            text="",
            bg=COLORS["header"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 18),
        )
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(
            title_box,
            text="",
            bg=COLORS["header"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        self.subtitle_label.pack(anchor="w", pady=(3, 0))

        header_actions = tk.Frame(header, bg=COLORS["header"])
        header_actions.pack(side="right", padx=15, pady=14)
        self.refresh_button = ttk.Button(
            header_actions,
            text="",
            command=self.refresh,
            style="Refresh.TButton",
        )
        self.refresh_button.pack(side="left", padx=(0, 8))

        self.menu_button = tk.Button(
            header_actions,
            text="⋮",
            command=self._show_menu,
            width=3,
            bg=COLORS["button"],
            fg=COLORS["text"],
            activebackground=COLORS["button_hover"],
            activeforeground=COLORS["accent_soft"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#315d3d",
            cursor="hand2",
            font=("Segoe UI Semibold", 12),
            padx=6,
            pady=5,
        )
        self.menu_button.pack(side="left")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=12, pady=(0, 9))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=29, minsize=315)
        body.grid_columnconfigure(1, weight=39, minsize=430)
        body.grid_columnconfigure(2, weight=32, minsize=360)

        left = self._card(body)
        middle = self._card(body)
        right = self._card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        middle.grid(row=0, column=1, sticky="nsew", padx=5)
        right.grid(row=0, column=2, sticky="nsew", padx=(5, 0))

        self.sessions_title = self._section_header(left)
        self.sessions_tree = self._make_tree(
            left,
            ("session", "character", "pending"),
            self._on_session_selected,
            (("session", 0.37), ("character", 0.40), ("pending", 0.23)),
        )
        self._heading(self.sessions_tree, "session", "session")
        self._heading(self.sessions_tree, "character", "character")
        self._heading(self.sessions_tree, "pending", "pending", numeric=True, anchor="center")

        self.pending_status = tk.Label(
            left,
            text="",
            anchor="w",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        self.pending_status.pack(fill="x", padx=13, pady=(1, 11))

        primary_bar = tk.Frame(middle, bg=COLORS["card"])
        primary_bar.pack(fill="x", padx=13, pady=(12, 4))
        self.primary_caption = tk.Label(
            primary_bar,
            text="",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        self.primary_caption.pack(side="left")
        self.primary_label = tk.Label(
            primary_bar,
            text="—",
            bg=COLORS["card"],
            fg=COLORS["accent_soft"],
            font=("Segoe UI Semibold", 9),
        )
        self.primary_label.pack(side="left", padx=(6, 0))

        self.candidates_title = self._section_header(middle)
        self.candidates_tree = self._make_tree(
            middle,
            ("candidate", "category", "confidence", "perspective"),
            self._on_candidate_selected,
            (("candidate", 0.48), ("category", 0.19), ("confidence", 0.14), ("perspective", 0.19)),
        )
        self._heading(self.candidates_tree, "candidate", "candidate")
        self._heading(self.candidates_tree, "category", "category")
        self._heading(self.candidates_tree, "confidence", "confidence", numeric=True, anchor="center")
        self._heading(self.candidates_tree, "perspective", "perspective", anchor="center")

        self.detail_title = self._section_header(right)
        detail_border = tk.Frame(
            right,
            bg=COLORS["surface"],
            highlightthickness=1,
            highlightbackground=COLORS["border_soft"],
        )
        detail_border.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.detail = ScrolledText(
            detail_border,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            insertbackground=COLORS["accent"],
            selectbackground=COLORS["selected"],
            selectforeground=COLORS["text"],
            relief="flat",
            borderwidth=0,
            font=("Consolas", 9),
            wrap="word",
            padx=11,
            pady=11,
        )
        self.detail.pack(fill="both", expand=True)
        self.detail.configure(state="disabled")

        actions = tk.Frame(right, bg=COLORS["card"])
        actions.pack(fill="x", padx=10, pady=(0, 10))
        for column in range(3):
            actions.grid_columnconfigure(column, weight=1)
        self.approve_button = ttk.Button(
            actions,
            text="",
            command=self._approve,
            state="disabled",
            style="Approve.TButton",
        )
        self.edit_button = ttk.Button(
            actions,
            text="",
            command=self._edit_and_approve,
            state="disabled",
            style="Edit.TButton",
        )
        self.reject_button = ttk.Button(
            actions,
            text="",
            command=self._reject,
            state="disabled",
            style="Reject.TButton",
        )
        self.approve_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.edit_button.grid(row=0, column=1, sticky="ew", padx=4)
        self.reject_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        self.status = tk.Label(
            self,
            text="",
            anchor="w",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        self.status.pack(fill="x", padx=14, pady=(0, 9))

    def _make_tree(
        self,
        parent: tk.Widget,
        columns: tuple[str, ...],
        callback: Any,
        layout: tuple[tuple[str, float], ...],
    ) -> ttk.Treeview:
        holder = tk.Frame(parent, bg=COLORS["card"])
        holder.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        tree = ttk.Treeview(
            holder,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Reviewer.Treeview",
        )
        tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(
            holder,
            orient="vertical",
            command=tree.yview,
            style="Reviewer.Vertical.TScrollbar",
        )
        scroll.grid(row=0, column=1, sticky="ns", padx=(2, 0))
        tree.configure(yscrollcommand=scroll.set)
        tree.bind("<<TreeviewSelect>>", callback)
        tree.bind("<Configure>", lambda event, t=tree, l=layout: self._resize_tree_columns(t, l))
        self._tree_layouts.append((tree, layout))
        return tree

    def _resize_tree_columns(
        self,
        tree: ttk.Treeview,
        layout: tuple[tuple[str, float], ...],
    ) -> None:
        available = max(tree.winfo_width() - 4, 1)
        allocated = 0
        for index, (column, ratio) in enumerate(layout):
            width = available - allocated if index == len(layout) - 1 else int(available * ratio)
            allocated += width
            tree.column(column, width=max(width, 1), minwidth=1, stretch=False)

    def _heading(
        self,
        tree: ttk.Treeview,
        column: str,
        key: str,
        *,
        numeric: bool = False,
        anchor: str = "w",
    ) -> None:
        self._headings.append((tree, column, key, numeric, anchor))
        tree.heading(
            column,
            text="",
            anchor=anchor,
            command=lambda: self._sort_tree(tree, column, numeric=numeric),
        )

    def _update_headings(self) -> None:
        for tree, column, key, numeric, anchor in self._headings:
            tree.heading(
                column,
                text=self._t(key),
                anchor=anchor,
                command=lambda t=tree, c=column, n=numeric: self._sort_tree(t, c, numeric=n),
            )
        self.after_idle(self._resize_all_trees)

    def _resize_all_trees(self) -> None:
        for tree, layout in self._tree_layouts:
            if tree.winfo_exists():
                self._resize_tree_columns(tree, layout)

    def _sort_tree(self, tree: ttk.Treeview, column: str, *, numeric: bool = False) -> None:
        state = (str(tree), column)
        reverse = self._sort_reverse.get(state, False)

        def key(item: str) -> tuple[int, float] | tuple[int, str]:
            value = tree.set(item, column)
            if numeric:
                try:
                    return (0, float(value))
                except (TypeError, ValueError):
                    return (1, 0.0)
            return (0, str(value).casefold())

        items = list(tree.get_children(""))
        items.sort(key=key, reverse=reverse)
        for index, item in enumerate(items):
            tree.move(item, "", index)
        self._sort_reverse[state] = not reverse

    def _build_menu(self) -> None:
        menu_options = {
            "tearoff": False,
            "bg": COLORS["surface_alt"],
            "fg": COLORS["text"],
            "activebackground": COLORS["selected"],
            "activeforeground": COLORS["accent_soft"],
            "relief": "flat",
            "borderwidth": 1,
        }
        menu = tk.Menu(self, **menu_options)
        menu.add_command(label=self._t("menu_refresh"), command=self.refresh)
        menu.add_separator()
        menu.add_command(
            label=self._t("menu_folder"),
            command=lambda: self._open_path(self.reviewer.canonical_root),
        )
        menu.add_command(
            label=self._t("menu_json"),
            command=lambda: self._open_path(self.reviewer.canonical_memory_path),
        )
        menu.add_command(
            label=self._t("menu_md"),
            command=lambda: self._open_path(self.reviewer.canonical_markdown_path),
        )
        menu.add_separator()

        language = tk.Menu(menu, **menu_options)
        language.add_radiobutton(
            label=self._t("lang_pt"),
            variable=self.language_var,
            value="pt-BR",
            command=lambda: self._set_language(self.language_var.get()),
        )
        language.add_radiobutton(
            label=self._t("lang_en"),
            variable=self.language_var,
            value="en-US",
            command=lambda: self._set_language(self.language_var.get()),
        )
        menu.add_cascade(label=self._t("menu_language"), menu=language)
        menu.add_separator()
        menu.add_command(label=self._t("menu_close"), command=self.destroy)
        self._menu = menu

    def _show_menu(self) -> None:
        if self._menu is None:
            self._build_menu()
        if self._menu is None:
            return
        x = self.menu_button.winfo_rootx() + self.menu_button.winfo_width() - 2
        y = self.menu_button.winfo_rooty() + self.menu_button.winfo_height() + 3
        try:
            self._menu.tk_popup(x, y)
        finally:
            self._menu.grab_release()

    def _apply_language(self) -> None:
        self.title(self._t("title"))
        self.title_label.configure(text=self._t("title"))
        self.subtitle_label.configure(text=self._t("subtitle"))
        self.refresh_button.configure(text=self._t("refresh"))
        self.sessions_title.configure(text=self._t("sessions_title"))
        self.candidates_title.configure(text=self._t("candidates_title"))
        self.detail_title.configure(text=self._t("detail_title"))
        self.primary_caption.configure(text=f"{self._t('primary_label')}:")
        self.approve_button.configure(text=self._t("approve"))
        self.edit_button.configure(text=self._t("edit"))
        self.reject_button.configure(text=self._t("reject"))
        self._update_headings()
        self._build_menu()

    def _set_language(self, language: str) -> None:
        if language not in TEXT:
            return
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
        if not value:
            return "—"
        key = f"per_{value}"
        return self._t(key) if key in TEXT[self.language] else value

    def _open_path(self, path: Path) -> None:
        path = Path(path)
        if not path.exists():
            messagebox.showinfo("LeafOS Reviewer", self._t("path_missing", path=path), parent=self)
            return
        try:
            os.startfile(str(path))
        except (AttributeError, OSError) as error:
            messagebox.showerror(
                "LeafOS Reviewer",
                self._t("path_error", path=path, error=error),
                parent=self,
            )

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def refresh(self) -> None:
        selected = self.sessions_tree.selection()
        previous = selected[0] if selected else None
        for tree in (self.sessions_tree, self.candidates_tree):
            for item in tree.get_children():
                tree.delete(item)
        self._session_rows.clear()
        self._candidate_rows.clear()

        try:
            sessions = self.reviewer.list_sessions()
        except ReviewerError as error:
            self.primary_label.configure(text="—", fg=COLORS["muted"])
            self._set_detail(f"{self._t('invalid_state')}\n\n{error}\n\n{self._t('invalid_state_body')}")
            self._set_action_state(False)
            self.pending_status.configure(text="")
            self.status.configure(text=self._t("invalid_state_status"))
            messagebox.showerror("LeafOS Reviewer", str(error), parent=self)
            return

        for row in sessions:
            session_id = row["session_id"]
            self._session_rows[session_id] = row
            self.sessions_tree.insert(
                "",
                "end",
                iid=session_id,
                values=(
                    session_id,
                    row.get("primary_character") or "—",
                    row.get("pending_count", 0),
                ),
            )

        count = self._count_text(len(sessions))
        self.pending_status.configure(
            text=count,
            fg=COLORS["accent"] if sessions else COLORS["muted"],
        )
        self.status.configure(text=count)
        self.primary_label.configure(text="—", fg=COLORS["muted"])
        self._set_detail(self._t("instructions"))
        self._set_action_state(False)
        self.after_idle(self._resize_all_trees)

        if previous and self.sessions_tree.exists(previous):
            self.sessions_tree.selection_set(previous)
            self.sessions_tree.focus(previous)
            self._on_session_selected()

    def _set_action_state(self, promote: bool, *, reject: bool | None = None) -> None:
        self.approve_button.configure(state="normal" if promote else "disabled")
        self.edit_button.configure(state="normal" if promote else "disabled")
        allow_reject = promote if reject is None else reject
        self.reject_button.configure(state="normal" if allow_reject else "disabled")

    def _on_session_selected(self, _event: Any = None) -> None:
        selected = self.sessions_tree.selection()
        if not selected:
            return
        session_id = selected[0]
        row = self._session_rows.get(session_id, {})
        self.primary_label.configure(
            text=row.get("primary_character") or "—",
            fg=COLORS["accent_soft"] if row.get("primary_character") else COLORS["muted"],
        )

        for item in self.candidates_tree.get_children():
            self.candidates_tree.delete(item)
        self._candidate_rows.clear()
        try:
            candidates = self.reviewer.list_candidates(session_id)
        except ReviewerError as error:
            messagebox.showerror("LeafOS Reviewer", str(error), parent=self)
            self.status.configure(text=self._t("load_error"))
            return

        for candidate in candidates:
            candidate_id = candidate["candidate_id"]
            self._candidate_rows[candidate_id] = candidate
            confidence = candidate.get("confidence")
            confidence_text = f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "—"
            self.candidates_tree.insert(
                "",
                "end",
                iid=candidate_id,
                values=(
                    _display_candidate(candidate["candidate"]),
                    self._display_category(candidate["canonical_category"]),
                    confidence_text,
                    self._display_perspective(candidate.get("perspective")),
                ),
            )
        self._set_detail(row.get("summary") or self._t("no_summary"))
        self._set_action_state(False)
        self.after_idle(self._resize_all_trees)

    def _selected_candidate_id(self) -> str | None:
        selected = self.candidates_tree.selection()
        return selected[0] if selected else None

    def _on_candidate_selected(self, _event: Any = None) -> None:
        candidate_id = self._selected_candidate_id()
        if not candidate_id:
            self._set_action_state(False)
            return
        try:
            detail = self.reviewer.candidate_detail(candidate_id)
        except ReviewerError as error:
            self._set_detail(
                f"{self._t('invalid_evidence')}\n\n{error}\n\n{self._t('invalid_evidence_body')}"
            )
            self._set_action_state(False, reject=True)
            self.status.configure(text=self._t("invalid_evidence_status"))
            return

        payload = {
            "candidate_id": candidate_id,
            "session_id": detail["session_id"],
            "category": detail["category"],
            "canonical_category": detail["canonical_category"],
            "primary_character": detail.get("primary_character"),
            "candidate": detail["candidate"],
            "processor_session": detail["processor_session"],
            "bundle_path": detail["bundle_path"],
            "evidence": detail["evidence"],
        }
        self._set_detail(json.dumps(payload, ensure_ascii=False, indent=2))
        self._set_action_state(True)
        self.status.configure(text=self._t("evidence_ok"))

    def _approve(self) -> None:
        candidate_id = self._selected_candidate_id()
        if not candidate_id:
            return
        if not messagebox.askyesno("LeafOS Reviewer", self._t("approve_question"), parent=self):
            return
        try:
            entry = self.reviewer.approve(candidate_id)
        except ReviewerError as error:
            messagebox.showerror("LeafOS Reviewer", str(error), parent=self)
            return
        self.status.configure(text=self._t("approved", memory_id=entry["memory_id"]))
        self.refresh()

    def _edit_and_approve(self) -> None:
        candidate_id = self._selected_candidate_id()
        if not candidate_id:
            return
        record = self._candidate_rows.get(candidate_id)
        if not record:
            return
        original = deepcopy(record["candidate"])

        dialog = tk.Toplevel(self)
        dialog.title(self._t("edit_title"))
        dialog.geometry("780x580")
        dialog.minsize(680, 480)
        dialog.configure(bg=COLORS["card"])
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(
            dialog,
            text=self._t("edit_hint"),
            anchor="w",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(fill="x", padx=14, pady=(14, 7))

        editor_border = tk.Frame(
            dialog,
            bg=COLORS["surface"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        editor_border.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        editor = ScrolledText(
            editor_border,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            insertbackground=COLORS["accent"],
            selectbackground=COLORS["selected"],
            selectforeground=COLORS["text"],
            relief="flat",
            borderwidth=0,
            font=("Consolas", 10),
            wrap="none",
            padx=10,
            pady=10,
        )
        editor.pack(fill="both", expand=True)
        editor.insert("1.0", json.dumps(original, ensure_ascii=False, indent=2))
        result: dict[str, Any] = {"saved": False}

        def save() -> None:
            try:
                decoded = json.loads(editor.get("1.0", "end"))
                if not isinstance(decoded, dict):
                    raise ValueError(self._t("json_object"))
                entry = self.reviewer.approve(candidate_id, edited_candidate=decoded)
            except (json.JSONDecodeError, ValueError, ReviewerError) as error:
                messagebox.showerror("LeafOS Reviewer", str(error), parent=dialog)
                return
            result.update(saved=True, memory_id=entry["memory_id"])
            dialog.destroy()

        footer = tk.Frame(dialog, bg=COLORS["card"])
        footer.pack(fill="x", padx=14, pady=(2, 14))
        ttk.Button(
            footer,
            text=self._t("cancel"),
            command=dialog.destroy,
            style="Refresh.TButton",
        ).pack(side="right")
        ttk.Button(
            footer,
            text=self._t("save"),
            command=save,
            style="Edit.TButton",
        ).pack(side="right", padx=8)
        self.wait_window(dialog)
        if result.get("saved"):
            self.status.configure(text=self._t("edited", memory_id=result.get("memory_id")))
            self.refresh()

    def _reject(self) -> None:
        candidate_id = self._selected_candidate_id()
        if not candidate_id:
            return
        if not messagebox.askyesno("LeafOS Reviewer", self._t("reject_question"), parent=self):
            return
        try:
            self.reviewer.reject(candidate_id)
        except ReviewerError as error:
            messagebox.showerror("LeafOS Reviewer", str(error), parent=self)
            return
        self.status.configure(text=self._t("rejected"))
        self.refresh()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Review LeafOS Interpreter candidates and promote human-approved canonical memory."
    )
    parser.add_argument("--vault", required=True, help="Path to the LeafOS Obsidian vault")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print pending sessions as JSON instead of opening the UI",
    )
    parser.add_argument(
        "--lang",
        choices=("pt-BR", "en-US"),
        default=None,
        help="Reviewer UI language. Defaults to the operating-system locale.",
    )
    args = parser.parse_args()

    reviewer = LeafOSMemoryReviewer(Path(args.vault))
    if args.list:
        print(json.dumps(reviewer.list_sessions(), ensure_ascii=False, indent=2, default=str))
        return 0

    app = MemoryReviewerApp(reviewer, language=args.lang)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
