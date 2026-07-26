from __future__ import annotations

import argparse
import json
import locale
import os
import sys
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from pc_agent.leafos_memory import LeafOSMemoryReviewer
from pc_agent.leafos_memory_support import ReviewerError, _display_candidate

COLORS = {
    "bg": "#07130d", "header": "#0a1a12", "card": "#0a1911", "surface": "#0b1b12",
    "surface_alt": "#0d2116", "surface_hover": "#10261a", "border": "#1c3b29",
    "border_soft": "#153021", "text": "#e8efe9", "muted": "#9aa89f", "accent": "#78d36d",
    "accent_soft": "#a9eba2", "selected": "#173a27", "disabled": "#536158", "button": "#10251a",
    "button_hover": "#173a26", "approve": "#1b4627", "approve_hover": "#245a32",
    "approve_border": "#4b8a52", "edit": "#7a5514", "edit_hover": "#91671a", "edit_border": "#ae8328",
    "reject": "#7b201b", "reject_hover": "#922a23", "reject_border": "#a8443b",
}
CATEGORY_COLORS = {
    "events": ("#173821", "#75d36b"), "characters": ("#12303a", "#6cc5da"),
    "locations": ("#3b2b12", "#e4bd65"), "relationships": ("#3a1c1c", "#e68b83"),
    "lore": ("#2c2138", "#c89be8"), "memories": ("#123531", "#7cd8c7"),
}
TEXT = {
    "pt-BR": {
        "title":"LeafOS Memory Reviewer","subtitle":"Revisão humana antes da memória canônica","refresh":"↻  Atualizar",
        "sessions_title":"Sessões pendentes","session":"Sessão","character":"Personagem","pending":"Pend.",
        "primary_label":"Personagem principal","candidates_title":"Candidatos","candidate":"Candidato",
        "category":"Categoria","confidence":"Conf.","perspective":"Perspectiva","detail_title":"Candidato e evidência",
        "selected_candidate":"Candidato selecionado","evidence":"Evidência","raw_json":"RAW JSON","approve":"✓  Aprovar",
        "edit":"✎  Editar + aprovar","reject":"✕  Rejeitar","menu_refresh":"Atualizar",
        "menu_folder":"Abrir pasta da Memória Canônica","menu_json":"Abrir memory.json","menu_md":"Abrir MEMORY.md",
        "menu_language":"Idioma","menu_close":"Fechar Reviewer","lang_pt":"Português (Brasil)","lang_en":"English (US)",
        "instructions":"Selecione uma sessão e um candidato.\n\nA promoção só é liberada quando a evidência chega até o RAW.",
        "invalid_state":"ESTADO DO REVIEWER INVÁLIDO","invalid_state_body":"O processamento foi bloqueado para proteger a memória persistida.",
        "invalid_state_status":"Reviewer bloqueado por estado persistido inválido","count_one":"1 sessão com candidatos pendentes",
        "count_many":"{count} sessões com candidatos pendentes","no_summary":"Sessão sem resumo.",
        "load_error":"Não foi possível carregar os candidatos da sessão","invalid_evidence":"EVIDÊNCIA INVÁLIDA",
        "invalid_evidence_body":"Aprovação bloqueada. Rejeição continua disponível para registrar a decisão humana.",
        "invalid_evidence_status":"Promoção bloqueada; rejeição auditável disponível","evidence_ok":"Evidência validada até o RAW",
        "approve_question":"Promover este candidato para a memória canônica?","approved":"Aprovado: {memory_id}",
        "edit_title":"Editar candidato antes da aprovação","edit_hint":"Edite somente o conteúdo. source_message_ids, confidence e review_status são protegidos.",
        "cancel":"Cancelar","save":"Salvar e aprovar","edited":"Editado e aprovado: {memory_id}","json_object":"O JSON precisa ser um objeto.",
        "reject_question":"Rejeitar este candidato? Ele ficará registrado como revisado.","rejected":"Candidato rejeitado e registrado",
        "path_missing":"Este caminho ainda não existe:\n\n{path}","path_error":"Não foi possível abrir:\n\n{path}\n\n{error}",
        "cat_events":"Eventos","cat_characters":"Personagens","cat_locations":"Locais","cat_relationships":"Relações",
        "cat_lore":"Lore","cat_memories":"Memórias","per_observed":"Observado","per_said":"Dito","per_inferred":"Inferido","unnamed_candidate":"Candidato sem título","invalid_json_input":"O JSON informado é inválido (linha {line}, coluna {column}).",
    },
    "en-US": {
        "title":"LeafOS Memory Reviewer","subtitle":"Human review before canonical memory","refresh":"↻  Refresh",
        "sessions_title":"Pending sessions","session":"Session","character":"Character","pending":"Pending",
        "primary_label":"Primary character","candidates_title":"Candidates","candidate":"Candidate","category":"Category",
        "confidence":"Conf.","perspective":"Perspective","detail_title":"Candidate and evidence","selected_candidate":"Selected candidate",
        "evidence":"Evidence","raw_json":"RAW JSON","approve":"✓  Approve","edit":"✎  Edit + approve","reject":"✕  Reject",
        "menu_refresh":"Refresh","menu_folder":"Open Canonical Memory folder","menu_json":"Open memory.json","menu_md":"Open MEMORY.md",
        "menu_language":"Language","menu_close":"Close Reviewer","lang_pt":"Português (Brasil)","lang_en":"English (US)",
        "instructions":"Select a session and a candidate.\n\nPromotion is enabled only when the evidence can be traced back to RAW.",
        "invalid_state":"INVALID REVIEWER STATE","invalid_state_body":"Processing was blocked to protect persisted memory.",
        "invalid_state_status":"Reviewer blocked by invalid persisted state","count_one":"1 session with pending candidates",
        "count_many":"{count} sessions with pending candidates","no_summary":"Session has no summary.","load_error":"Could not load candidates for this session",
        "invalid_evidence":"INVALID EVIDENCE","invalid_evidence_body":"Approval is blocked. Rejection remains available to record the human decision.",
        "invalid_evidence_status":"Promotion blocked; auditable rejection remains available","evidence_ok":"Evidence validated through RAW",
        "approve_question":"Promote this candidate to canonical memory?","approved":"Approved: {memory_id}","edit_title":"Edit candidate before approval",
        "edit_hint":"Edit content only. source_message_ids, confidence and review_status are protected.","cancel":"Cancel","save":"Save and approve",
        "edited":"Edited and approved: {memory_id}","json_object":"The JSON must be an object.",
        "reject_question":"Reject this candidate? It will remain recorded as reviewed.","rejected":"Candidate rejected and recorded",
        "path_missing":"This path does not exist yet:\n\n{path}","path_error":"Could not open:\n\n{path}\n\n{error}",
        "cat_events":"Events","cat_characters":"Characters","cat_locations":"Locations","cat_relationships":"Relationships",
        "cat_lore":"Lore","cat_memories":"Memories","per_observed":"Observed","per_said":"Said","per_inferred":"Inferred","unnamed_candidate":"Untitled candidate","invalid_json_input":"The provided JSON is invalid (line {line}, column {column}).",
    },
}


REVIEWER_ERROR_TEXT = {
    "pt-BR": {
        "UNKNOWN": "O Reviewer encontrou um erro controlado.",
        "INVALID_JSON": "O arquivo JSON persistido está inválido ou corrompido.",
        "JSON_ROOT_MUST_BE_OBJECT": "O arquivo JSON precisa conter um objeto na raiz.",
        "EDITED_CANDIDATE_MUST_BE_OBJECT": "O candidato editado precisa ser um objeto JSON.",
        "IMMUTABLE_FIELD_CHANGED": "Um campo protegido foi alterado durante a edição.",
        "INVALID_PERSPECTIVE": "A perspectiva informada não é válida.",
        "MEMORY_REQUIRES_VALID_PERSPECTIVE": "A memória subjetiva exige uma perspectiva válida.",
        "MEMORY_REQUIRES_PRIMARY_CHARACTER": "A memória subjetiva exige um personagem principal.",
        "INTERPRETATION_BUNDLE_NOT_FOUND": "O bundle de interpretação da sessão não foi encontrado.",
        "PROCESSOR_SESSION_NOT_FOUND": "A sessão fechada do Processor não foi encontrada.",
        "PROCESSOR_SESSION_ID_MISMATCH": "O ID da sessão do Processor não corresponde à sessão revisada.",
        "CANDIDATE_NOT_FOUND": "O candidato solicitado não foi encontrado.",
        "CANDIDATE_WITHOUT_SOURCE_MESSAGE_IDS": "O candidato não possui IDs de mensagens de origem.",
        "INVALID_SOURCE_MESSAGE_IDS": "Os IDs de mensagens de origem são inválidos.",
        "DUPLICATE_SOURCE_MESSAGE_IDS": "Existem IDs de mensagens de origem duplicados.",
        "INVALID_SESSION_MESSAGE_IDS": "A sessão possui IDs de mensagens inválidos.",
        "SOURCE_ID_NOT_IN_INTERPRETATION_BUNDLE": "Uma mensagem de origem não pertence ao bundle de interpretação.",
        "SOURCE_ID_NOT_IN_PROCESSOR_SESSION": "Uma mensagem de origem não pertence à sessão do Processor.",
        "BUNDLE_RAW_SOURCE_NOT_IN_PROCESSOR_SESSION": "Uma fonte RAW do bundle não pertence à sessão do Processor.",
        "PROCESSOR_MESSAGES_INVALID": "A lista de mensagens da sessão do Processor é inválida.",
        "SOURCE_MESSAGE_MISSING": "Uma mensagem de origem esperada não foi encontrada na sessão.",
        "RAW_SOURCE_MISSING": "A referência ao arquivo RAW está ausente.",
        "MESSAGE_RAW_SOURCE_NOT_IN_SESSION": "A fonte RAW da mensagem não pertence à sessão.",
        "RAW_FILE_NOT_FOUND": "O arquivo RAW referenciado não foi encontrado.",
        "SOURCE_ID_NOT_IN_RAW": "O ID da mensagem de origem não foi encontrado no RAW.",
        "RAW_TIMESTAMP_MISMATCH": "O timestamp da evidência diverge do RAW.",
        "RAW_CHANNEL_MISMATCH": "O canal da evidência diverge do RAW.",
        "RAW_SPEAKER_MISMATCH": "O falante da evidência diverge do RAW.",
        "RAW_TEXT_MISMATCH": "O texto da evidência diverge do RAW.",
        "CANDIDATE_ALREADY_REJECTED": "Este candidato já foi rejeitado.",
        "APPROVED_REVIEW_WITHOUT_MEMORY_ENTRY": "Existe uma aprovação registrada sem a entrada correspondente na memória canônica.",
        "code_label": "Código", "detail_label": "Detalhes",
    },
    "en-US": {
        "UNKNOWN": "The Reviewer encountered a controlled error.",
        "INVALID_JSON": "The persisted JSON file is invalid or corrupted.",
        "JSON_ROOT_MUST_BE_OBJECT": "The JSON file must contain an object at its root.",
        "EDITED_CANDIDATE_MUST_BE_OBJECT": "The edited candidate must be a JSON object.",
        "IMMUTABLE_FIELD_CHANGED": "A protected field was changed during editing.",
        "INVALID_PERSPECTIVE": "The selected perspective is invalid.",
        "MEMORY_REQUIRES_VALID_PERSPECTIVE": "Subjective memory requires a valid perspective.",
        "MEMORY_REQUIRES_PRIMARY_CHARACTER": "Subjective memory requires a primary character.",
        "INTERPRETATION_BUNDLE_NOT_FOUND": "The session interpretation bundle was not found.",
        "PROCESSOR_SESSION_NOT_FOUND": "The closed Processor session was not found.",
        "PROCESSOR_SESSION_ID_MISMATCH": "The Processor session ID does not match the reviewed session.",
        "CANDIDATE_NOT_FOUND": "The requested candidate was not found.",
        "CANDIDATE_WITHOUT_SOURCE_MESSAGE_IDS": "The candidate has no source message IDs.",
        "INVALID_SOURCE_MESSAGE_IDS": "The source message IDs are invalid.",
        "DUPLICATE_SOURCE_MESSAGE_IDS": "Duplicate source message IDs were found.",
        "INVALID_SESSION_MESSAGE_IDS": "The session contains invalid message IDs.",
        "SOURCE_ID_NOT_IN_INTERPRETATION_BUNDLE": "A source message does not belong to the interpretation bundle.",
        "SOURCE_ID_NOT_IN_PROCESSOR_SESSION": "A source message does not belong to the Processor session.",
        "BUNDLE_RAW_SOURCE_NOT_IN_PROCESSOR_SESSION": "A bundle RAW source does not belong to the Processor session.",
        "PROCESSOR_MESSAGES_INVALID": "The Processor session message list is invalid.",
        "SOURCE_MESSAGE_MISSING": "An expected source message was not found in the session.",
        "RAW_SOURCE_MISSING": "The RAW file reference is missing.",
        "MESSAGE_RAW_SOURCE_NOT_IN_SESSION": "The message RAW source does not belong to the session.",
        "RAW_FILE_NOT_FOUND": "The referenced RAW file was not found.",
        "SOURCE_ID_NOT_IN_RAW": "The source message ID was not found in RAW.",
        "RAW_TIMESTAMP_MISMATCH": "The evidence timestamp differs from RAW.",
        "RAW_CHANNEL_MISMATCH": "The evidence channel differs from RAW.",
        "RAW_SPEAKER_MISMATCH": "The evidence speaker differs from RAW.",
        "RAW_TEXT_MISMATCH": "The evidence text differs from RAW.",
        "CANDIDATE_ALREADY_REJECTED": "This candidate has already been rejected.",
        "APPROVED_REVIEW_WITHOUT_MEMORY_ENTRY": "An approval exists without the corresponding canonical-memory entry.",
        "code_label": "Code", "detail_label": "Details",
    },
}

CLI_TEXT = {
    "pt-BR": {
        "description": "Revise candidatos do LeafOS Interpreter e promova memória canônica aprovada por humano.",
        "vault_help": "Caminho da Vault LeafOS.", "list_help": "Lista sessões pendentes sem abrir a interface.",
        "lang_help": "Idioma da interface e da CLI.", "help_help": "Mostra esta ajuda e encerra.",
        "usage_prefix": "uso:", "options_title": "opções:", "error_prefix": "erro",
    },
    "en-US": {
        "description": "Review LeafOS Interpreter candidates and promote human-approved canonical memory.",
        "vault_help": "Path to the LeafOS Vault.", "list_help": "List pending sessions without opening the interface.",
        "lang_help": "Interface and CLI language.", "help_help": "Show this help message and exit.",
        "usage_prefix": "usage:", "options_title": "options:", "error_prefix": "error",
    },
}


def _reviewer_error_message(error: BaseException, language: str) -> str:
    catalog = REVIEWER_ERROR_TEXT.get(language, REVIEWER_ERROR_TEXT["en-US"])
    raw = str(error).strip()
    code, separator, details = raw.partition(":")
    code = code.strip() if code.strip() else "UNKNOWN"
    message = catalog.get(code, catalog["UNKNOWN"])
    result = f"{message}\n\n{catalog['code_label']}: {code}"
    if separator and details.strip():
        result += f"\n{catalog['detail_label']}: {details.strip()}"
    return result


def _requested_cli_language() -> str:
    values = sys.argv[1:]
    for index, value in enumerate(values):
        if value == "--lang" and index + 1 < len(values) and values[index + 1] in TEXT:
            return values[index + 1]
        if value.startswith("--lang="):
            candidate = value.split("=", 1)[1]
            if candidate in TEXT:
                return candidate
    return _default_language()


class _LocalizedArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, language: str, **kwargs: Any) -> None:
        self.language = language
        super().__init__(*args, **kwargs)

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", CLI_TEXT[self.language]["usage_prefix"], 1)

    def format_help(self) -> str:
        text = super().format_help()
        text = text.replace("usage:", CLI_TEXT[self.language]["usage_prefix"], 1)
        return text.replace("options:", CLI_TEXT[self.language]["options_title"], 1)

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: {CLI_TEXT[self.language]['error_prefix']}: {message}\n")

def _default_language() -> str:
    try:
        current = locale.getlocale()[0] or ""
    except (AttributeError, ValueError):
        current = ""
    return "pt-BR" if current.lower().startswith("pt") else "en-US"


class _ScrollableList(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=COLORS["surface"])
        self.canvas = tk.Canvas(self, bg=COLORS["surface"], highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Reviewer.Vertical.TScrollbar")
        self.inner = tk.Frame(self.canvas, bg=COLORS["surface"])
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(2, 0))
        self.grid_rowconfigure(0, weight=1); self.grid_columnconfigure(0, weight=1)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.inner.bind("<Configure>", lambda _e: self._sync())
        self.canvas.bind("<Configure>", self._resize)
        self._scroll_visible = True

    def _resize(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=max(int(event.width), 1)); self.after_idle(self._sync)
    def _on_scroll(self, first: str, last: str) -> None:
        self.scrollbar.set(first, last)
    def _sync(self) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all")); bbox = self.canvas.bbox("all")
        content = 0 if not bbox else bbox[3] - bbox[1]; show = content > self.canvas.winfo_height() + 2
        if show and not self._scroll_visible: self.scrollbar.grid(); self._scroll_visible = True
        elif not show and self._scroll_visible: self.scrollbar.grid_remove(); self._scroll_visible = False
    def clear(self) -> None:
        for child in self.inner.winfo_children(): child.destroy()
        self.canvas.yview_moveto(0); self.after_idle(self._sync)


class MemoryReviewerApp(tk.Tk):
    def __init__(self, reviewer: LeafOSMemoryReviewer, *, language: str | None = None) -> None:
        super().__init__()
        self.reviewer = reviewer; self.language = language if language in TEXT else _default_language(); self.language_var = tk.StringVar(value=self.language)
        self._session_rows: dict[str, dict[str, Any]] = {}; self._candidate_rows: dict[str, dict[str, Any]] = {}
        self._session_order: list[str] = []; self._candidate_order: list[str] = []; self._selected_session_id: str | None = None; self._selected_candidate: str | None = None
        self._session_sort_key: str | None = None; self._session_sort_reverse = False
        self._candidate_sort_key: str | None = None; self._candidate_sort_reverse = False
        self._menu: tk.Menu | None = None
        self.geometry("1586x992"); self.minsize(1240, 760); self.configure(bg=COLORS["bg"])
        self._configure_styles(); self._load_brand_image(); self._build_ui(); self._apply_language(); self.refresh()

    def _t(self, key: str, **kwargs: Any) -> str:
        value = TEXT[self.language].get(key, key); return value.format(**kwargs) if kwargs else value
    def _reviewer_error(self, error: BaseException) -> str:
        return _reviewer_error_message(error, self.language)
    def _count_text(self, count: int) -> str:
        return self._t("count_one") if count == 1 else self._t("count_many", count=count)
    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("Reviewer.Vertical.TScrollbar", background="#193527", troughcolor=COLORS["surface"], bordercolor=COLORS["surface"], arrowcolor=COLORS["muted"])
        for name, normal, active, border, fg in (
            ("Refresh.TButton", COLORS["button"], COLORS["button_hover"], "#315d3d", COLORS["text"]),
            ("Approve.TButton", COLORS["approve"], COLORS["approve_hover"], COLORS["approve_border"], "#eff8f0"),
            ("Edit.TButton", COLORS["edit"], COLORS["edit_hover"], COLORS["edit_border"], "#fff2d0"),
            ("Reject.TButton", COLORS["reject"], COLORS["reject_hover"], COLORS["reject_border"], "#ffe6e2"),
        ):
            style.configure(name, padding=(14, 11), background=normal, foreground=fg, bordercolor=border, relief="flat", font=("Segoe UI Semibold", 10))
            style.map(name, background=[("disabled", "#151d18"), ("active", active)], foreground=[("disabled", COLORS["disabled"])])

    def _load_brand_image(self) -> None:
        asset_path = Path(__file__).resolve().parent / "assets" / "leafos_emblem.png"
        self._logo_image = tk.PhotoImage(file=str(asset_path))
        try:
            self.iconphoto(True, self._logo_image)
        except tk.TclError:
            pass

    def _card(self, parent: tk.Widget, *, bg: str | None = None) -> tk.Frame:
        return tk.Frame(parent, bg=bg or COLORS["card"], highlightthickness=1, highlightbackground=COLORS["border"])
    def _bind_click(self, widget: tk.Widget, callback: Callable[[], None]) -> None:
        widget.bind("<Button-1>", lambda _e: callback())
        for child in widget.winfo_children(): self._bind_click(child, callback)
    def _header_label(self, parent: tk.Widget, key: str, anchor: str = "w") -> tk.Label:
        label = tk.Label(
            parent,
            text="",
            bg=COLORS["surface_alt"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 9),
            anchor=anchor,
            padx=6,
            pady=8,
            cursor="hand2",
        )
        setattr(label, "_key", key)
        return label

    def _sort_indicator(self, key: str, active_key: str | None, reverse: bool) -> str:
        if key != active_key:
            return ""
        if key in {"pending", "confidence"}:
            return "  ↓" if reverse else "  ↑"
        return "  Z-A" if reverse else "  A-Z"

    def _update_header_texts(self) -> None:
        self.session_h.configure(
            text=self._t("session") + self._sort_indicator("session", self._session_sort_key, self._session_sort_reverse)
        )
        self.character_h.configure(
            text=self._t("character") + self._sort_indicator("character", self._session_sort_key, self._session_sort_reverse)
        )
        self.pending_h.configure(
            text=self._t("pending") + self._sort_indicator("pending", self._session_sort_key, self._session_sort_reverse)
        )
        self.candidate_h.configure(
            text=self._t("candidate") + self._sort_indicator("candidate", self._candidate_sort_key, self._candidate_sort_reverse)
        )
        self.category_h.configure(
            text=self._t("category") + self._sort_indicator("category", self._candidate_sort_key, self._candidate_sort_reverse)
        )
        self.confidence_h.configure(
            text=self._t("confidence") + self._sort_indicator("confidence", self._candidate_sort_key, self._candidate_sort_reverse)
        )
        self.perspective_h.configure(
            text=self._t("perspective") + self._sort_indicator("perspective", self._candidate_sort_key, self._candidate_sort_reverse)
        )

    def _toggle_session_sort(self, key: str) -> None:
        if self._session_sort_key == key:
            self._session_sort_reverse = not self._session_sort_reverse
        else:
            self._session_sort_key = key
            self._session_sort_reverse = False
        self._apply_session_sort()
        self._update_header_texts()
        self._render_sessions()

    def _toggle_candidate_sort(self, key: str) -> None:
        if self._candidate_sort_key == key:
            self._candidate_sort_reverse = not self._candidate_sort_reverse
        else:
            self._candidate_sort_key = key
            self._candidate_sort_reverse = False
        self._apply_candidate_sort()
        self._update_header_texts()
        self._render_candidates()

    def _apply_session_sort(self) -> None:
        if not self._session_sort_key:
            return

        def sort_value(session_id: str) -> Any:
            row = self._session_rows[session_id]
            if self._session_sort_key == "session":
                return str(session_id).casefold()
            if self._session_sort_key == "character":
                return str(row.get("primary_character") or "").casefold()
            if self._session_sort_key == "pending":
                return int(row.get("pending_count") or 0)
            return str(session_id).casefold()

        self._session_order.sort(key=sort_value, reverse=self._session_sort_reverse)

    def _apply_candidate_sort(self) -> None:
        if not self._candidate_sort_key:
            return

        def sort_value(candidate_id: str) -> Any:
            row = self._candidate_rows[candidate_id]
            if self._candidate_sort_key == "candidate":
                return _display_candidate(row["candidate"], fallback=self._t("unnamed_candidate")).casefold()
            if self._candidate_sort_key == "category":
                return self._display_category(row.get("canonical_category") or "").casefold()
            if self._candidate_sort_key == "confidence":
                return float(row.get("confidence") or 0.0)
            if self._candidate_sort_key == "perspective":
                return self._display_perspective(row.get("perspective")).casefold()
            return _display_candidate(row["candidate"], fallback=self._t("unnamed_candidate")).casefold()

        self._candidate_order.sort(key=sort_value, reverse=self._candidate_sort_reverse)

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=COLORS["header"]); header.pack(fill="x", padx=14, pady=(12, 10))
        brand = tk.Frame(header, bg=COLORS["header"]); brand.pack(side="left", fill="x", expand=True, padx=(4,0), pady=3)
        tk.Label(brand, image=self._logo_image, bg=COLORS["header"], bd=0).pack(side="left", padx=(0,15))
        titles = tk.Frame(brand, bg=COLORS["header"]); titles.pack(side="left", fill="x", expand=True, pady=(4,0))
        self.title_label = tk.Label(titles, bg=COLORS["header"], fg=COLORS["text"], font=("Segoe UI Semibold", 22)); self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(titles, bg=COLORS["header"], fg=COLORS["muted"], font=("Segoe UI",10)); self.subtitle_label.pack(anchor="w", pady=(3,0))
        actions = tk.Frame(header, bg=COLORS["header"]); actions.pack(side="right", padx=(0,7), pady=19)
        self.refresh_button = ttk.Button(actions, command=self.refresh, style="Refresh.TButton"); self.refresh_button.pack(side="left", padx=(0,18))
        self.menu_button = tk.Button(actions, text="⋮", command=self._show_menu, width=3, bg=COLORS["button"], fg=COLORS["text"], activebackground=COLORS["button_hover"], relief="flat", bd=0, highlightthickness=1, highlightbackground=COLORS["border_soft"], font=("Segoe UI Semibold",14), padx=8, pady=7); self.menu_button.pack(side="left")

        body = tk.Frame(self, bg=COLORS["bg"]); body.pack(fill="both", expand=True, padx=14, pady=(0,13)); body.grid_rowconfigure(0, weight=1); body.grid_columnconfigure(0, weight=23, minsize=330); body.grid_columnconfigure(1, weight=77, minsize=820)
        left = self._card(body); left.grid(row=0,column=0,sticky="nsew",padx=(0,7)); left.grid_rowconfigure(2,weight=1); left.grid_columnconfigure(0,weight=1)
        lt = tk.Frame(left,bg=COLORS["card"]); lt.grid(row=0,column=0,sticky="ew",padx=15,pady=(15,10)); tk.Label(lt,text="●",bg=COLORS["card"],fg=COLORS["accent"],font=("Segoe UI",12)).pack(side="left",padx=(0,8)); self.sessions_title=tk.Label(lt,bg=COLORS["card"],fg=COLORS["text"],font=("Segoe UI Semibold",11)); self.sessions_title.pack(side="left")
        sh = tk.Frame(left,bg=COLORS["surface_alt"],highlightthickness=1,highlightbackground=COLORS["border_soft"]); sh.grid(row=1,column=0,sticky="ew",padx=12); sh.grid_columnconfigure(0,weight=42,uniform="s"); sh.grid_columnconfigure(1,weight=38,uniform="s"); sh.grid_columnconfigure(2,minsize=82)
        self.session_h=self._header_label(sh,"session"); self.character_h=self._header_label(sh,"character"); self.pending_h=self._header_label(sh,"pending","center"); self.session_h.grid(row=0,column=0,sticky="ew"); self.character_h.grid(row=0,column=1,sticky="ew"); self.pending_h.grid(row=0,column=2,sticky="ew")
        self.session_h.bind("<Button-1>", lambda _e: self._toggle_session_sort("session"))
        self.character_h.bind("<Button-1>", lambda _e: self._toggle_session_sort("character"))
        self.pending_h.bind("<Button-1>", lambda _e: self._toggle_session_sort("pending"))
        self.sessions_list=_ScrollableList(left); self.sessions_list.grid(row=2,column=0,sticky="nsew",padx=12); self.pending_status=tk.Label(left,bg=COLORS["card"],fg=COLORS["muted"],font=("Segoe UI",9),anchor="w"); self.pending_status.grid(row=3,column=0,sticky="ew",padx=15,pady=(8,12))

        workspace=self._card(body); workspace.grid(row=0,column=1,sticky="nsew",padx=(7,0)); workspace.grid_rowconfigure(1,weight=1); workspace.grid_columnconfigure(0,weight=1)
        primary=tk.Frame(workspace,bg=COLORS["card"]); primary.grid(row=0,column=0,sticky="ew",padx=18,pady=(14,11)); tk.Label(primary,text="♟",bg=COLORS["card"],fg=COLORS["muted"],font=("Segoe UI Symbol",14)).pack(side="left",padx=(0,9)); self.primary_caption=tk.Label(primary,bg=COLORS["card"],fg=COLORS["muted"],font=("Segoe UI",10)); self.primary_caption.pack(side="left"); self.primary_label=tk.Label(primary,text="—",bg=COLORS["card"],fg=COLORS["accent"],font=("Segoe UI Semibold",10)); self.primary_label.pack(side="left",padx=(5,0))
        panes=tk.Frame(workspace,bg=COLORS["card"]); panes.grid(row=1,column=0,sticky="nsew",padx=12,pady=(0,12)); panes.grid_rowconfigure(0,weight=1); panes.grid_columnconfigure(0,weight=51,minsize=470); panes.grid_columnconfigure(1,weight=49,minsize=430)
        middle=self._card(panes,bg=COLORS["surface"]); right=self._card(panes,bg=COLORS["surface"]); middle.grid(row=0,column=0,sticky="nsew",padx=(0,7)); right.grid(row=0,column=1,sticky="nsew",padx=(7,0)); middle.grid_rowconfigure(2,weight=1); middle.grid_columnconfigure(0,weight=1)
        mt=tk.Frame(middle,bg=COLORS["surface"]); mt.grid(row=0,column=0,sticky="ew",padx=13,pady=(13,9)); tk.Label(mt,text="▣",bg=COLORS["surface"],fg=COLORS["accent"],font=("Segoe UI Symbol",15)).pack(side="left",padx=(0,8)); self.candidates_title=tk.Label(mt,bg=COLORS["surface"],fg=COLORS["text"],font=("Segoe UI Semibold",11)); self.candidates_title.pack(side="left")
        ch=tk.Frame(middle,bg=COLORS["surface_alt"],highlightthickness=1,highlightbackground=COLORS["border_soft"]); ch.grid(row=1,column=0,sticky="ew",padx=12); ch.grid_columnconfigure(0,minsize=34); ch.grid_columnconfigure(1,weight=55); ch.grid_columnconfigure(2,minsize=108); ch.grid_columnconfigure(3,minsize=82); ch.grid_columnconfigure(4,minsize=112); tk.Label(ch,bg=COLORS["surface_alt"]).grid(row=0,column=0,sticky="ew")
        self.candidate_h=self._header_label(ch,"candidate"); self.category_h=self._header_label(ch,"category"); self.confidence_h=self._header_label(ch,"confidence","center"); self.perspective_h=self._header_label(ch,"perspective","center"); self.candidate_h.grid(row=0,column=1,sticky="ew"); self.category_h.grid(row=0,column=2,sticky="ew"); self.confidence_h.grid(row=0,column=3,sticky="ew"); self.perspective_h.grid(row=0,column=4,sticky="ew")
        self.candidate_h.bind("<Button-1>", lambda _e: self._toggle_candidate_sort("candidate"))
        self.category_h.bind("<Button-1>", lambda _e: self._toggle_candidate_sort("category"))
        self.confidence_h.bind("<Button-1>", lambda _e: self._toggle_candidate_sort("confidence"))
        self.perspective_h.bind("<Button-1>", lambda _e: self._toggle_candidate_sort("perspective"))
        self.candidates_list=_ScrollableList(middle); self.candidates_list.grid(row=2,column=0,sticky="nsew",padx=12,pady=(0,12))

        right.grid_rowconfigure(3,weight=1); right.grid_columnconfigure(0,weight=1)
        rt=tk.Frame(right,bg=COLORS["surface"]); rt.grid(row=0,column=0,sticky="ew",padx=13,pady=(13,9)); tk.Label(rt,text="▤",bg=COLORS["surface"],fg=COLORS["text"],font=("Segoe UI Symbol",15)).pack(side="left",padx=(0,8)); self.detail_title=tk.Label(rt,bg=COLORS["surface"],fg=COLORS["text"],font=("Segoe UI Semibold",11)); self.detail_title.pack(side="left")
        self.selected_card=tk.Frame(right,bg=COLORS["surface_alt"],highlightthickness=1,highlightbackground=COLORS["border"]); self.selected_card.grid(row=1,column=0,sticky="ew",padx=12,pady=(0,12)); self.selected_caption=tk.Label(self.selected_card,bg=COLORS["surface_alt"],fg=COLORS["muted"],font=("Segoe UI",9),anchor="w"); self.selected_caption.pack(fill="x",padx=13,pady=(10,3)); sl=tk.Frame(self.selected_card,bg=COLORS["surface_alt"]); sl.pack(fill="x",padx=13,pady=(0,11)); self.selected_title=tk.Label(sl,text="—",bg=COLORS["surface_alt"],fg=COLORS["accent"],font=("Segoe UI Semibold",10),anchor="w",justify="left",wraplength=420); self.selected_title.pack(side="left",fill="x",expand=True)
        self.selected_card.bind("<Configure>", lambda event: self.selected_title.configure(wraplength=max(event.width - 42, 220)))
        evidence=tk.Frame(right,bg=COLORS["surface"],highlightthickness=1,highlightbackground=COLORS["border"]); evidence.grid(row=2,column=0,rowspan=2,sticky="nsew",padx=12,pady=(0,12)); evidence.grid_rowconfigure(1,weight=1); evidence.grid_columnconfigure(0,weight=1); eh=tk.Frame(evidence,bg=COLORS["surface_alt"]); eh.grid(row=0,column=0,sticky="ew"); self.evidence_title=tk.Label(eh,bg=COLORS["surface_alt"],fg=COLORS["text"],font=("Segoe UI Semibold",10)); self.evidence_title.pack(side="left",padx=13,pady=10); self.raw_json_label=tk.Label(eh,bg=COLORS["surface_alt"],fg=COLORS["muted"],font=("Consolas",9)); self.raw_json_label.pack(side="right",padx=13,pady=10)
        self.detail=ScrolledText(evidence,bg=COLORS["surface"],fg=COLORS["text"],insertbackground=COLORS["accent"],selectbackground=COLORS["selected"],relief="flat",borderwidth=0,font=("Consolas",9),wrap="word",padx=12,pady=10); self.detail.grid(row=1,column=0,sticky="nsew"); self.detail.configure(state="disabled")
        ab=tk.Frame(right,bg=COLORS["surface"]); ab.grid(row=4,column=0,sticky="ew",padx=12,pady=(0,12)); [ab.grid_columnconfigure(i,weight=1) for i in range(3)]; self.approve_button=ttk.Button(ab,command=self._approve,state="disabled",style="Approve.TButton"); self.edit_button=ttk.Button(ab,command=self._edit_and_approve,state="disabled",style="Edit.TButton"); self.reject_button=ttk.Button(ab,command=self._reject,state="disabled",style="Reject.TButton"); self.approve_button.grid(row=0,column=0,sticky="ew",padx=(0,6)); self.edit_button.grid(row=0,column=1,sticky="ew",padx=6); self.reject_button.grid(row=0,column=2,sticky="ew",padx=(6,0))
        self.status=tk.Label(self,bg=COLORS["bg"],fg=COLORS["muted"],font=("Segoe UI",9),anchor="w"); self.status.pack(fill="x",padx=17,pady=(0,9))

    def _build_menu(self) -> None:
        opts={"tearoff":False,"bg":COLORS["surface_alt"],"fg":COLORS["text"],"activebackground":COLORS["selected"],"activeforeground":COLORS["accent_soft"]}; menu=tk.Menu(self,**opts); menu.add_command(label=self._t("menu_refresh"),command=self.refresh); menu.add_separator(); menu.add_command(label=self._t("menu_folder"),command=lambda:self._open_path(self.reviewer.canonical_root)); menu.add_command(label=self._t("menu_json"),command=lambda:self._open_path(self.reviewer.canonical_memory_path)); menu.add_command(label=self._t("menu_md"),command=lambda:self._open_path(self.reviewer.canonical_markdown_path)); menu.add_separator(); lang=tk.Menu(menu,**opts); lang.add_radiobutton(label=self._t("lang_pt"),variable=self.language_var,value="pt-BR",command=lambda:self._set_language(self.language_var.get())); lang.add_radiobutton(label=self._t("lang_en"),variable=self.language_var,value="en-US",command=lambda:self._set_language(self.language_var.get())); menu.add_cascade(label=self._t("menu_language"),menu=lang); menu.add_separator(); menu.add_command(label=self._t("menu_close"),command=self.destroy); self._menu=menu
    def _show_menu(self) -> None:
        if self._menu is None: self._build_menu()
        assert self._menu is not None
        try: self._menu.tk_popup(self.menu_button.winfo_rootx()+self.menu_button.winfo_width()-2,self.menu_button.winfo_rooty()+self.menu_button.winfo_height()+3)
        finally: self._menu.grab_release()
    def _apply_language(self) -> None:
        self.title(self._t("title")); self.title_label.configure(text=self._t("title")); self.subtitle_label.configure(text=self._t("subtitle")); self.refresh_button.configure(text=self._t("refresh")); self.sessions_title.configure(text=self._t("sessions_title")); self.primary_caption.configure(text=f"{self._t('primary_label')}:"); self.candidates_title.configure(text=self._t("candidates_title")); self.detail_title.configure(text=self._t("detail_title")); self.selected_caption.configure(text=self._t("selected_candidate")); self.evidence_title.configure(text=f"</>  {self._t('evidence')}"); self.raw_json_label.configure(text="{}  "+self._t("raw_json")); self.approve_button.configure(text=self._t("approve")); self.edit_button.configure(text=self._t("edit")); self.reject_button.configure(text=self._t("reject"));
        self._update_header_texts()
        self._build_menu(); self._render_sessions(); self._render_candidates()
    def _set_language(self, language: str) -> None:
        if language in TEXT: self.language=language; self.language_var.set(language); self._apply_language(); self.refresh()
    def _display_category(self, category: Any) -> str:
        value=str(category or ""); key=f"cat_{value}"; return self._t(key) if key in TEXT[self.language] else value
    def _display_perspective(self, perspective: Any) -> str:
        value=str(perspective or "").strip(); key=f"per_{value}"; return "—" if not value else (self._t(key) if key in TEXT[self.language] else value)
    def _candidate_summary(self, candidate: dict[str,Any]) -> str:
        for key in ("description","statement","summary","text","content"):
            value=candidate.get(key)
            if isinstance(value,str) and value.strip(): return value.strip()
        return _display_candidate(candidate, fallback=self._t("unnamed_candidate"))
    def _open_path(self,path:Path)->None:
        path=Path(path)
        if not path.exists(): messagebox.showinfo("LeafOS Reviewer",self._t("path_missing",path=path),parent=self); return
        try: os.startfile(str(path))
        except (AttributeError,OSError) as error: messagebox.showerror("LeafOS Reviewer",self._t("path_error",path=path,error=error),parent=self)
    def _set_detail(self,text:str)->None:
        self.detail.configure(state="normal"); self.detail.delete("1.0","end"); self.detail.insert("1.0",text); self.detail.configure(state="disabled")

    def _render_sessions(self)->None:
        if not hasattr(self,"sessions_list"): return
        self.sessions_list.clear()
        for sid in self._session_order:
            row=self._session_rows[sid]; selected=sid==self._selected_session_id; bg=COLORS["selected"] if selected else COLORS["surface"]
            item=tk.Frame(self.sessions_list.inner,bg=bg); item.pack(fill="x"); item.grid_columnconfigure(0,weight=42,uniform="sr"); item.grid_columnconfigure(1,weight=38,uniform="sr"); item.grid_columnconfigure(2,minsize=82)
            sf=tk.Frame(item,bg=bg); sf.grid(row=0,column=0,sticky="ew",padx=(7,2),pady=10); tk.Label(sf,text="●",bg=bg,fg=COLORS["accent"],font=("Segoe UI",9)).pack(side="left",padx=(0,6)); tk.Label(sf,text=sid,bg=bg,fg=COLORS["accent"] if selected else COLORS["text"],font=("Segoe UI Semibold" if selected else "Segoe UI",9),anchor="w").pack(side="left",fill="x",expand=True); tk.Label(item,text=row.get("primary_character") or "—",bg=bg,fg=COLORS["text"],font=("Segoe UI",9),anchor="w",padx=5).grid(row=0,column=1,sticky="ew"); tk.Label(item,text=str(row.get("pending_count",0)),bg=bg,fg=COLORS["accent_soft"],font=("Segoe UI",9),anchor="center").grid(row=0,column=2,sticky="ew"); self._bind_click(item,lambda s=sid:self._select_session(s))
    def _render_candidates(self)->None:
        if not hasattr(self,"candidates_list"): return
        self.candidates_list.clear()
        for index,cid in enumerate(self._candidate_order,1):
            rec=self._candidate_rows[cid]; selected=cid==self._selected_candidate; bg=COLORS["surface_hover"] if selected else COLORS["surface"]; category=str(rec.get("canonical_category") or ""); pill_bg,pill_fg=CATEGORY_COLORS.get(category,("#173022",COLORS["accent_soft"]))
            item=tk.Frame(self.candidates_list.inner,bg=bg); item.pack(fill="x"); item.grid_columnconfigure(0,minsize=34); item.grid_columnconfigure(1,weight=55); item.grid_columnconfigure(2,minsize=108); item.grid_columnconfigure(3,minsize=82); item.grid_columnconfigure(4,minsize=112)
            tk.Label(item,text=str(index),bg=pill_fg,fg="#122016",font=("Segoe UI Semibold",9),width=2).grid(row=0,column=0,sticky="n",padx=(7,0),pady=(16,0)); content=tk.Frame(item,bg=bg); content.grid(row=0,column=1,sticky="nsew",padx=(5,8),pady=11); tk.Label(content,text=_display_candidate(rec["candidate"], fallback=self._t("unnamed_candidate")),bg=bg,fg=COLORS["text"],font=("Segoe UI Semibold",10),anchor="w",justify="left",wraplength=310).pack(fill="x"); tk.Label(content,text=self._candidate_summary(rec["candidate"]),bg=bg,fg=COLORS["muted"],font=("Segoe UI",9),anchor="w",justify="left",wraplength=310).pack(fill="x",pady=(6,0)); tk.Label(item,text=self._display_category(category),bg=pill_bg,fg=pill_fg,font=("Segoe UI",9),padx=10,pady=5).grid(row=0,column=2); confidence=rec.get("confidence"); tk.Label(item,text=f"{float(confidence):.2f}" if isinstance(confidence,(int,float)) else "—",bg=bg,fg=COLORS["accent_soft"],font=("Segoe UI",10)).grid(row=0,column=3); tk.Label(item,text=self._display_perspective(rec.get("perspective")),bg=bg,fg=COLORS["text"],font=("Segoe UI",9)).grid(row=0,column=4); tk.Frame(item,bg=COLORS["border_soft"],height=1).grid(row=1,column=0,columnspan=5,sticky="ew"); self._bind_click(item,lambda c=cid:self._select_candidate(c))
    def _set_action_state(self,promote:bool,*,reject:bool|None=None)->None:
        self.approve_button.configure(state="normal" if promote else "disabled"); self.edit_button.configure(state="normal" if promote else "disabled"); self.reject_button.configure(state="normal" if (promote if reject is None else reject) else "disabled")
    def refresh(self)->None:
        previous=self._selected_session_id; self._session_rows.clear(); self._session_order.clear(); self._candidate_rows.clear(); self._candidate_order.clear(); self._selected_candidate=None
        try: sessions=self.reviewer.list_sessions()
        except ReviewerError as error: self._set_detail(f"{self._t('invalid_state')}\n\n{self._reviewer_error(error)}\n\n{self._t('invalid_state_body')}"); self._set_action_state(False); messagebox.showerror("LeafOS Reviewer",self._reviewer_error(error),parent=self); return
        for row in sessions: self._session_rows[row["session_id"]]=row; self._session_order.append(row["session_id"])
        self._apply_session_sort(); self._update_header_texts(); self._render_sessions(); count=self._count_text(len(sessions)); self.pending_status.configure(text=f"●  {count}",fg=COLORS["accent"] if sessions else COLORS["muted"]); self.status.configure(text=count); self.primary_label.configure(text="—",fg=COLORS["muted"]); self.selected_title.configure(text="—",fg=COLORS["muted"]); self._set_detail(self._t("instructions")); self._set_action_state(False)
        if previous and previous in self._session_rows: self._select_session(previous)
    def _select_session(self,sid:str)->None:
        self._selected_session_id=sid; self._render_sessions(); row=self._session_rows[sid]; self.primary_label.configure(text=row.get("primary_character") or "—",fg=COLORS["accent"] if row.get("primary_character") else COLORS["muted"]); self._candidate_rows.clear(); self._candidate_order.clear(); self._selected_candidate=None
        try: candidates=self.reviewer.list_candidates(sid)
        except ReviewerError as error: messagebox.showerror("LeafOS Reviewer",self._reviewer_error(error),parent=self); self.status.configure(text=self._t("load_error")); return
        for candidate in candidates: self._candidate_rows[candidate["candidate_id"]]=candidate; self._candidate_order.append(candidate["candidate_id"])
        self._apply_candidate_sort(); self._update_header_texts(); self._render_candidates(); self.selected_title.configure(text="—",fg=COLORS["muted"]); self._set_detail(row.get("summary") or self._t("no_summary")); self._set_action_state(False)
    def _selected_candidate_id(self)->str|None: return self._selected_candidate
    def _select_candidate(self,cid:str)->None:
        self._selected_candidate=cid; self._render_candidates(); rec=self._candidate_rows[cid]; self.selected_title.configure(text=_display_candidate(rec["candidate"], fallback=self._t("unnamed_candidate")),fg=COLORS["accent"])
        try: detail=self.reviewer.candidate_detail(cid)
        except ReviewerError as error: self._set_detail(f"{self._t('invalid_evidence')}\n\n{self._reviewer_error(error)}\n\n{self._t('invalid_evidence_body')}"); self._set_action_state(False,reject=True); return
        payload={"candidate_id":cid,"session_id":detail["session_id"],"category":detail["category"],"canonical_category":detail["canonical_category"],"primary_character":detail.get("primary_character"),"candidate":detail["candidate"],"processor_session":detail["processor_session"],"bundle_path":detail["bundle_path"],"evidence":detail["evidence"]}; self._set_detail(json.dumps(payload,ensure_ascii=False,indent=2)); self._set_action_state(True); self.status.configure(text=self._t("evidence_ok"))
    def _approve(self)->None:
        cid=self._selected_candidate_id()
        if not cid or not messagebox.askyesno("LeafOS Reviewer",self._t("approve_question"),parent=self): return
        try: entry=self.reviewer.approve(cid)
        except ReviewerError as error: messagebox.showerror("LeafOS Reviewer",self._reviewer_error(error),parent=self); return
        self.status.configure(text=self._t("approved",memory_id=entry["memory_id"])); self.refresh()
    def _edit_and_approve(self)->None:
        cid=self._selected_candidate_id(); rec=self._candidate_rows.get(cid or "")
        if not cid or not rec: return
        original=deepcopy(rec["candidate"]); dialog=tk.Toplevel(self); dialog.title(self._t("edit_title")); dialog.geometry("780x580"); dialog.configure(bg=COLORS["card"]); dialog.transient(self); dialog.grab_set(); tk.Label(dialog,text=self._t("edit_hint"),bg=COLORS["card"],fg=COLORS["muted"],font=("Segoe UI",9),anchor="w").pack(fill="x",padx=14,pady=(14,7)); editor=ScrolledText(dialog,bg=COLORS["surface"],fg=COLORS["text"],insertbackground=COLORS["accent"],font=("Consolas",10),wrap="none"); editor.pack(fill="both",expand=True,padx=14,pady=(0,8)); editor.insert("1.0",json.dumps(original,ensure_ascii=False,indent=2)); result={"saved":False}
        def save()->None:
            try:
                decoded=json.loads(editor.get("1.0","end"))
                if not isinstance(decoded,dict): raise ValueError(self._t("json_object"))
                entry=self.reviewer.approve(cid,edited_candidate=decoded)
            except json.JSONDecodeError as error: messagebox.showerror("LeafOS Reviewer",self._t("invalid_json_input",line=error.lineno,column=error.colno),parent=dialog); return
            except ValueError as error: messagebox.showerror("LeafOS Reviewer",str(error),parent=dialog); return
            except ReviewerError as error: messagebox.showerror("LeafOS Reviewer",self._reviewer_error(error),parent=dialog); return
            result.update(saved=True,memory_id=entry["memory_id"]); dialog.destroy()
        footer=tk.Frame(dialog,bg=COLORS["card"]); footer.pack(fill="x",padx=14,pady=(2,14)); ttk.Button(footer,text=self._t("cancel"),command=dialog.destroy,style="Refresh.TButton").pack(side="right"); ttk.Button(footer,text=self._t("save"),command=save,style="Edit.TButton").pack(side="right",padx=8); self.wait_window(dialog)
        if result["saved"]: self.status.configure(text=self._t("edited",memory_id=result.get("memory_id"))); self.refresh()
    def _reject(self)->None:
        cid=self._selected_candidate_id()
        if not cid or not messagebox.askyesno("LeafOS Reviewer",self._t("reject_question"),parent=self): return
        try: self.reviewer.reject(cid)
        except ReviewerError as error: messagebox.showerror("LeafOS Reviewer",self._reviewer_error(error),parent=self); return
        self.status.configure(text=self._t("rejected")); self.refresh()


def main() -> int:
    cli_language = _requested_cli_language()
    cli = CLI_TEXT[cli_language]
    parser = _LocalizedArgumentParser(language=cli_language, description=cli["description"], add_help=False)
    parser.add_argument("-h", "--help", action="help", help=cli["help_help"])
    parser.add_argument("--vault", required=True, help=cli["vault_help"])
    parser.add_argument("--list", action="store_true", help=cli["list_help"])
    parser.add_argument("--lang", choices=("pt-BR", "en-US"), default=None, help=cli["lang_help"])
    args = parser.parse_args()
    reviewer = LeafOSMemoryReviewer(Path(args.vault))
    if args.list:
        print(json.dumps(reviewer.list_sessions(), ensure_ascii=False, indent=2, default=str))
        return 0
    app = MemoryReviewerApp(reviewer, language=args.lang or cli_language)
    app.mainloop()
    return 0

if __name__ == "__main__": raise SystemExit(main())
