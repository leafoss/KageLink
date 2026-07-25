from __future__ import annotations

import argparse
import json
import os
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from pc_agent.leafos_memory import LeafOSMemoryReviewer
from pc_agent.leafos_memory_support import ReviewerError, _display_candidate


class MemoryReviewerApp(tk.Tk):
    def __init__(self, reviewer: LeafOSMemoryReviewer) -> None:
        super().__init__()
        self.reviewer = reviewer
        self.title("LeafOS Memory Reviewer v1")
        self.geometry("1320x780")
        self.minsize(1080, 640)
        self.configure(bg="#0b1510")
        self._session_rows: dict[str, dict[str, Any]] = {}
        self._candidate_rows: dict[str, dict[str, Any]] = {}
        self._sort_reverse: dict[tuple[str, str], bool] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9), padding=(6, 6))
        style.configure("TButton", padding=7)

        top = tk.Frame(self, bg="#0b1510")
        top.pack(fill="x", padx=14, pady=(12, 6))

        title_block = tk.Frame(top, bg="#0b1510")
        title_block.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_block,
            text="LeafOS Memory Reviewer v1",
            bg="#0b1510",
            fg="#b8f5c8",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="Revisão humana antes da memória canônica",
            bg="#0b1510",
            fg="#789486",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(1, 0))

        header_actions = tk.Frame(top, bg="#0b1510")
        header_actions.pack(side="right")
        ttk.Button(header_actions, text="Atualizar", command=self.refresh).pack(side="left", padx=(0, 6))

        menu_button = ttk.Menubutton(header_actions, text="⋮", width=3)
        menu = tk.Menu(menu_button, tearoff=False)
        menu.add_command(label="Atualizar", command=self.refresh)
        menu.add_separator()
        menu.add_command(
            label="Abrir pasta da Canonical Memory",
            command=lambda: self._open_path(self.reviewer.canonical_root),
        )
        menu.add_command(
            label="Abrir memory.json",
            command=lambda: self._open_path(self.reviewer.canonical_memory_path),
        )
        menu.add_command(
            label="Abrir MEMORY.md",
            command=lambda: self._open_path(self.reviewer.canonical_markdown_path),
        )
        menu.add_separator()
        menu.add_command(label="Fechar Reviewer", command=self.destroy)
        menu_button.configure(menu=menu)
        menu_button.pack(side="left")

        body = tk.PanedWindow(self, orient="horizontal", sashwidth=5, bg="#1a2a20")
        body.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        left = tk.Frame(body, bg="#101e16")
        middle = tk.Frame(body, bg="#101e16")
        right = tk.Frame(body, bg="#101e16")
        body.add(left, minsize=310)
        body.add(middle, minsize=430)
        body.add(right, minsize=430)

        tk.Label(
            left,
            text="Sessões pendentes",
            bg="#101e16",
            fg="#d7e7dc",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", padx=10, pady=10)
        self.sessions_tree = ttk.Treeview(
            left,
            columns=("session", "character", "pending"),
            show="headings",
            selectmode="browse",
        )
        self._sortable_heading(self.sessions_tree, "session", "Sessão")
        self._sortable_heading(self.sessions_tree, "character", "Personagem")
        self._sortable_heading(self.sessions_tree, "pending", "Pendentes", numeric=True, anchor="center")
        self.sessions_tree.column("session", width=150, minwidth=110, anchor="w", stretch=True)
        self.sessions_tree.column("character", width=145, minwidth=110, anchor="w", stretch=True)
        self.sessions_tree.column("pending", width=75, minwidth=70, anchor="center", stretch=False)
        self.sessions_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.sessions_tree.bind("<<TreeviewSelect>>", self._on_session_selected)

        self.primary_label = tk.Label(
            middle,
            text="Personagem principal: —",
            bg="#101e16",
            fg="#8cd9a4",
            font=("Segoe UI Semibold", 10),
        )
        self.primary_label.pack(anchor="w", padx=10, pady=(10, 4))
        tk.Label(
            middle,
            text="Candidatos",
            bg="#101e16",
            fg="#d7e7dc",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", padx=10, pady=(2, 8))
        self.candidates_tree = ttk.Treeview(
            middle,
            columns=("candidate", "category", "confidence", "perspective"),
            show="headings",
            selectmode="browse",
        )
        self._sortable_heading(self.candidates_tree, "candidate", "Candidato")
        self._sortable_heading(self.candidates_tree, "category", "Categoria")
        self._sortable_heading(self.candidates_tree, "confidence", "Conf.", numeric=True, anchor="center")
        self._sortable_heading(self.candidates_tree, "perspective", "Perspectiva", anchor="center")
        self.candidates_tree.column("candidate", width=230, minwidth=150, anchor="w", stretch=True)
        self.candidates_tree.column("category", width=100, minwidth=85, anchor="w", stretch=False)
        self.candidates_tree.column("confidence", width=65, minwidth=60, anchor="center", stretch=False)
        self.candidates_tree.column("perspective", width=90, minwidth=80, anchor="center", stretch=False)
        self.candidates_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.candidates_tree.bind("<<TreeviewSelect>>", self._on_candidate_selected)

        tk.Label(
            right,
            text="Candidato e evidência",
            bg="#101e16",
            fg="#d7e7dc",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", padx=10, pady=10)
        self.detail = ScrolledText(
            right,
            bg="#08110c",
            fg="#d7e7dc",
            insertbackground="#b8f5c8",
            font=("Consolas", 9),
            wrap="word",
        )
        self.detail.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.detail.configure(state="disabled")

        actions = tk.Frame(right, bg="#101e16")
        actions.pack(fill="x", padx=10, pady=(0, 10))
        self.approve_button = ttk.Button(actions, text="Aprovar", command=self._approve, state="disabled")
        self.approve_button.pack(side="left")
        self.edit_button = ttk.Button(
            actions,
            text="Editar + aprovar",
            command=self._edit_and_approve,
            state="disabled",
        )
        self.edit_button.pack(side="left", padx=7)
        self.reject_button = ttk.Button(actions, text="Rejeitar", command=self._reject, state="disabled")
        self.reject_button.pack(side="left")

        self.status = tk.Label(
            self,
            text="",
            anchor="w",
            bg="#0b1510",
            fg="#8aa598",
            font=("Segoe UI", 9),
        )
        self.status.pack(fill="x", padx=16, pady=(0, 10))

    def _sortable_heading(
        self,
        tree: ttk.Treeview,
        column: str,
        text: str,
        *,
        numeric: bool = False,
        anchor: str = "w",
    ) -> None:
        tree.heading(
            column,
            text=text,
            anchor=anchor,
            command=lambda: self._sort_tree(tree, column, numeric=numeric),
        )

    def _sort_tree(self, tree: ttk.Treeview, column: str, *, numeric: bool = False) -> None:
        state_key = (str(tree), column)
        reverse = self._sort_reverse.get(state_key, False)

        def value_for(item_id: str) -> tuple[int, float] | tuple[int, str]:
            raw = tree.set(item_id, column)
            if numeric:
                try:
                    return (0, float(raw))
                except (TypeError, ValueError):
                    return (1, 0.0)
            return (0, str(raw).casefold())

        items = list(tree.get_children(""))
        items.sort(key=value_for, reverse=reverse)
        for index, item_id in enumerate(items):
            tree.move(item_id, "", index)
        self._sort_reverse[state_key] = not reverse

    def _open_path(self, path: Path) -> None:
        path = Path(path)
        if not path.exists():
            messagebox.showinfo(
                "LeafOS Reviewer",
                f"Este caminho ainda não existe:\n\n{path}",
                parent=self,
            )
            return
        try:
            os.startfile(str(path))
        except (AttributeError, OSError) as error:
            messagebox.showerror(
                "LeafOS Reviewer",
                f"Não foi possível abrir:\n\n{path}\n\n{error}",
                parent=self,
            )

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def refresh(self) -> None:
        for item in self.sessions_tree.get_children():
            self.sessions_tree.delete(item)
        for item in self.candidates_tree.get_children():
            self.candidates_tree.delete(item)
        self._session_rows.clear()
        self._candidate_rows.clear()
        try:
            sessions = self.reviewer.list_sessions()
        except ReviewerError as error:
            self.primary_label.configure(text="Personagem principal: —")
            self._set_detail(
                f"ESTADO DO REVIEWER INVÁLIDO\n\n{error}\n\n"
                "O processamento foi bloqueado para proteger a memória persistida."
            )
            self._set_action_state(False)
            self.status.configure(text="Reviewer bloqueado por estado persistido inválido")
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
        self.primary_label.configure(text="Personagem principal: —")
        self._set_detail(
            "Selecione uma sessão e um candidato.\n\n"
            "A promoção só é liberada quando a evidência chega até o RAW."
        )
        self._set_action_state(False)
        self.status.configure(text=f"{len(sessions)} sessão(ões) com candidatos pendentes")

    def _set_action_state(self, promote_enabled: bool, *, reject_enabled: bool | None = None) -> None:
        promote_state = "normal" if promote_enabled else "disabled"
        reject_state = "normal" if (promote_enabled if reject_enabled is None else reject_enabled) else "disabled"
        self.approve_button.configure(state=promote_state)
        self.edit_button.configure(state=promote_state)
        self.reject_button.configure(state=reject_state)

    def _on_session_selected(self, _event: Any = None) -> None:
        selected = self.sessions_tree.selection()
        if not selected:
            return
        session_id = selected[0]
        row = self._session_rows.get(session_id, {})
        self.primary_label.configure(text=f"Personagem principal: {row.get('primary_character') or '—'}")
        for item in self.candidates_tree.get_children():
            self.candidates_tree.delete(item)
        self._candidate_rows.clear()
        try:
            candidates = self.reviewer.list_candidates(session_id)
        except ReviewerError as error:
            messagebox.showerror("LeafOS Reviewer", str(error), parent=self)
            self.status.configure(text="Não foi possível carregar os candidatos da sessão")
            return
        for candidate in candidates:
            candidate_id = candidate["candidate_id"]
            self._candidate_rows[candidate_id] = candidate
            confidence = candidate.get("confidence")
            if isinstance(confidence, (int, float)):
                confidence_text = f"{float(confidence):.2f}"
            else:
                confidence_text = "—"
            self.candidates_tree.insert(
                "",
                "end",
                iid=candidate_id,
                values=(
                    _display_candidate(candidate["candidate"]),
                    candidate["canonical_category"],
                    confidence_text,
                    candidate.get("perspective") or "—",
                ),
            )
        self._set_detail(row.get("summary") or "Sessão sem resumo.")
        self._set_action_state(False)

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
                f"EVIDÊNCIA INVÁLIDA\n\n{error}\n\n"
                "Aprovação bloqueada. Rejeição continua disponível para registrar a decisão humana."
            )
            self._set_action_state(False, reject_enabled=True)
            self.status.configure(text="Promoção bloqueada; rejeição auditável disponível")
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
        self.status.configure(text="Evidência validada até o RAW")

    def _approve(self) -> None:
        candidate_id = self._selected_candidate_id()
        if not candidate_id:
            return
        if not messagebox.askyesno("LeafOS Reviewer", "Promover este candidato para a memória canônica?"):
            return
        try:
            entry = self.reviewer.approve(candidate_id)
        except ReviewerError as error:
            messagebox.showerror("LeafOS Reviewer", str(error), parent=self)
            return
        self.status.configure(text=f"Aprovado: {entry['memory_id']}")
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
        dialog.title("Editar candidato antes da aprovação")
        dialog.geometry("760x560")
        dialog.transient(self)
        dialog.grab_set()
        tk.Label(
            dialog,
            text="Edite somente o conteúdo sem alterar source_message_ids/confidence.",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 6))
        editor = ScrolledText(dialog, font=("Consolas", 10), wrap="none")
        editor.pack(fill="both", expand=True, padx=12, pady=6)
        editor.insert("1.0", json.dumps(original, ensure_ascii=False, indent=2))
        result: dict[str, Any] = {"saved": False}

        def save() -> None:
            try:
                decoded = json.loads(editor.get("1.0", "end"))
                if not isinstance(decoded, dict):
                    raise ValueError("O JSON precisa ser um objeto.")
                entry = self.reviewer.approve(candidate_id, edited_candidate=decoded)
            except (json.JSONDecodeError, ValueError, ReviewerError) as error:
                messagebox.showerror("LeafOS Reviewer", str(error), parent=dialog)
                return
            result["saved"] = True
            result["memory_id"] = entry["memory_id"]
            dialog.destroy()

        footer = tk.Frame(dialog)
        footer.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(footer, text="Cancelar", command=dialog.destroy).pack(side="right")
        ttk.Button(footer, text="Salvar e aprovar", command=save).pack(side="right", padx=8)
        self.wait_window(dialog)
        if result.get("saved"):
            self.status.configure(text=f"Editado e aprovado: {result.get('memory_id')}")
            self.refresh()

    def _reject(self) -> None:
        candidate_id = self._selected_candidate_id()
        if not candidate_id:
            return
        if not messagebox.askyesno(
            "LeafOS Reviewer",
            "Rejeitar este candidato? Ele ficará registrado como revisado.",
        ):
            return
        try:
            self.reviewer.reject(candidate_id)
        except ReviewerError as error:
            messagebox.showerror("LeafOS Reviewer", str(error), parent=self)
            return
        self.status.configure(text="Candidato rejeitado e registrado")
        self.refresh()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Review LeafOS Interpreter candidates and promote human-approved canonical memory."
    )
    parser.add_argument("--vault", required=True, help="Path to the LeafOS Obsidian vault")
    parser.add_argument("--list", action="store_true", help="Print pending sessions as JSON instead of opening the UI")
    args = parser.parse_args()

    reviewer = LeafOSMemoryReviewer(Path(args.vault))
    if args.list:
        print(json.dumps(reviewer.list_sessions(), ensure_ascii=False, indent=2, default=str))
        return 0

    app = MemoryReviewerApp(reviewer)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
