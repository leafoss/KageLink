from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Button, Entry, Frame, Label, Listbox, StringVar

import unified_launcher as launcher


_DOJO_TABS = ("summary", "settings", "images", "logs")


launcher.TEXT["pt-BR"].update(
    {
        "dojo_page_title": "Dojo Trainer",
        "dojo_tab_summary": "Resumo",
        "dojo_tab_settings": "Configurações",
        "dojo_tab_images": "Imagens",
        "dojo_tab_logs": "Logs",
        "dojo_current_round": "Rodada atual",
        "dojo_location": "Localização",
        "dojo_location_known": "Posição conhecida",
        "dojo_location_uncertain": "Posição incerta",
        "dojo_location_lost": "Posição perdida",
        "dojo_location_returning": "Retornando à origem",
        "dojo_location_relocalizing": "Relocalizando",
        "dojo_location_detail": "X {x:.2f} · Y {y:.2f} · confiança {confidence:.0%}",
        "dojo_training_control": "Controle do treino",
        "dojo_existing_settings": "Configurações disponíveis",
        "dojo_existing_settings_help": (
            "Esta versão mostra somente parâmetros que já fazem parte do contrato atual do Dojo Trainer."
        ),
        "dojo_recent_actions": "Últimas ações",
        "dojo_no_recent_actions": "Nenhuma ação recente.",
        "dojo_log_title": "Diagnóstico da última falha",
        "dojo_log_empty": "Nenhum erro de Dojo foi registrado neste computador.",
        "dojo_log_state": "Estado",
        "dojo_log_time": "Horário",
        "dojo_log_summary": "Resumo",
        "dojo_log_file": "Arquivo",
        "dojo_log_open": "Abrir log",
        "dojo_log_open_folder": "Abrir pasta de logs",
        "dojo_log_error": "Erro",
        "dojo_log_incomplete": "Sessão incompleta",
        "dojo_log_open_failed": "Não foi possível abrir o caminho:\n\n{error}",
        "dojo_images_help_short": (
            "As imagens ficam fora do executável, preservam a nitidez pixel-art e sobrevivem às atualizações."
        ),
    }
)
launcher.TEXT["en-US"].update(
    {
        "dojo_page_title": "Dojo Trainer",
        "dojo_tab_summary": "Summary",
        "dojo_tab_settings": "Settings",
        "dojo_tab_images": "Images",
        "dojo_tab_logs": "Logs",
        "dojo_current_round": "Current round",
        "dojo_location": "Location",
        "dojo_location_known": "Position known",
        "dojo_location_uncertain": "Position uncertain",
        "dojo_location_lost": "Position lost",
        "dojo_location_returning": "Returning to origin",
        "dojo_location_relocalizing": "Relocalizing",
        "dojo_location_detail": "X {x:.2f} · Y {y:.2f} · confidence {confidence:.0%}",
        "dojo_training_control": "Training control",
        "dojo_existing_settings": "Available settings",
        "dojo_existing_settings_help": (
            "This version shows only parameters that already belong to the current Dojo Trainer contract."
        ),
        "dojo_recent_actions": "Recent actions",
        "dojo_no_recent_actions": "No recent actions.",
        "dojo_log_title": "Latest failure diagnostics",
        "dojo_log_empty": "No Dojo error has been recorded on this computer.",
        "dojo_log_state": "State",
        "dojo_log_time": "Time",
        "dojo_log_summary": "Summary",
        "dojo_log_file": "File",
        "dojo_log_open": "Open log",
        "dojo_log_open_folder": "Open logs folder",
        "dojo_log_error": "Error",
        "dojo_log_incomplete": "Incomplete session",
        "dojo_log_open_failed": "The path could not be opened:\n\n{error}",
        "dojo_images_help_short": (
            "Images stay outside the executable, preserve pixel-art sharpness and survive updates."
        ),
    }
)


def _open_path(path: str) -> None:
    value = str(path or "").strip()
    if not value:
        raise FileNotFoundError("EMPTY_PATH")
    resolved = Path(value).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(str(resolved))
    if os.name == "nt":
        os.startfile(str(resolved))  # type: ignore[attr-defined]
        return
    command = ["open", str(resolved)] if sys.platform == "darwin" else ["xdg-open", str(resolved)]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install_dojo_reliability_desktop(base_class):
    """Replace only the Dojo page with a responsive 3.5.1 tabbed composition."""

    class ReliableDojoDesktopUI(base_class):
        def __init__(self, root) -> None:
            self.dojo_current_round_var = StringVar(value="0")
            self.dojo_location_var = StringVar(value="—")
            self.dojo_location_detail_var = StringVar(value="—")
            self.dojo_log_state_var = StringVar(value="—")
            self.dojo_log_time_var = StringVar(value="—")
            self.dojo_log_summary_var = StringVar(value="—")
            self.dojo_log_file_var = StringVar(value="—")
            self._dojo_log_path = ""
            self._dojo_log_directory = ""
            self._dojo_tab_frames: dict[str, Frame] = {}
            self._dojo_tab_buttons: dict[str, Button] = {}
            self._dojo_active_tab = "summary"
            self._dojo_resize_after = None
            self._dojo_summary_body = None
            self._dojo_summary_left = None
            self._dojo_summary_right = None
            self._dojo_images_grid = None
            self._dojo_recent_list = None
            self._dojo_log_open_button = None
            super().__init__(root)

        def _build_ui(self) -> None:
            super()._build_ui()
            try:
                self.root.minsize(1100, 720)
            except Exception:
                pass
            self._rebuild_dojo_page_v351()
            self.root.bind("<Configure>", self._dojo_on_configure, add="+")
            self.root.after_idle(self._dojo_apply_responsive_layout)

        def _clear_dojo_template_widget_registry(self) -> None:
            self._dojo_template_preview_labels.clear()
            self._dojo_template_images.clear()
            self._dojo_template_hashes.clear()
            self._dojo_template_buttons.clear()

        def _rebuild_dojo_page_v351(self) -> None:
            page = self._pages["dojo"]
            for child in page.winfo_children():
                child.destroy()
            for row in range(8):
                page.grid_rowconfigure(row, weight=0)
            for column in range(4):
                page.grid_columnconfigure(column, weight=0)
            page.grid_columnconfigure(0, weight=1)
            page.grid_rowconfigure(2, weight=1)

            header = Frame(page, bg=launcher.COLORS["bg"])
            header.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 12))
            header.grid_columnconfigure(0, weight=1)
            Label(
                header,
                text="⚔  " + launcher._t(self.lang, "dojo_page_title"),
                bg=launcher.COLORS["bg"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 17),
            ).grid(row=0, column=0, sticky="w")

            tabs = Frame(
                page,
                bg=launcher.COLORS["card"],
                highlightthickness=1,
                highlightbackground=launcher.COLORS["border_soft"],
            )
            tabs.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 12))
            for index, key in enumerate(_DOJO_TABS):
                tabs.grid_columnconfigure(index, weight=1)
                button = Button(
                    tabs,
                    text=launcher._t(self.lang, f"dojo_tab_{key}"),
                    command=lambda value=key: self._dojo_show_tab(value),
                    bg=launcher.COLORS["card"],
                    fg=launcher.COLORS["muted"],
                    activebackground=launcher.COLORS["selected"],
                    activeforeground=launcher.COLORS["accent_soft"],
                    relief="flat",
                    bd=0,
                    pady=12,
                    font=("Segoe UI Semibold", 10),
                )
                button.grid(row=0, column=index, sticky="ew", padx=1, pady=1)
                self._dojo_tab_buttons[key] = button

            body = Frame(page, bg=launcher.COLORS["bg"])
            body.grid(row=2, column=0, sticky="nsew", padx=4)
            body.grid_rowconfigure(0, weight=1)
            body.grid_columnconfigure(0, weight=1)

            self._dojo_tab_frames.clear()
            for key in _DOJO_TABS:
                frame = Frame(body, bg=launcher.COLORS["bg"])
                frame.grid(row=0, column=0, sticky="nsew")
                frame.grid_columnconfigure(0, weight=1)
                self._dojo_tab_frames[key] = frame

            self._build_dojo_summary_tab(self._dojo_tab_frames["summary"])
            self._build_dojo_settings_tab(self._dojo_tab_frames["settings"])
            self._build_dojo_images_tab(self._dojo_tab_frames["images"])
            self._build_dojo_logs_tab(self._dojo_tab_frames["logs"])
            self._dojo_show_tab(self._dojo_active_tab)
            self._update_dojo_buttons()

        def _dojo_card(self, parent: Frame, *, padx: int = 16, pady: int = 14) -> Frame:
            return Frame(
                parent,
                bg=launcher.COLORS["card"],
                highlightthickness=1,
                highlightbackground=launcher.COLORS["border_soft"],
                padx=padx,
                pady=pady,
            )

        def _dojo_status_card(self, parent: Frame, title: str, variable: StringVar) -> Frame:
            card = self._dojo_card(parent, padx=16, pady=12)
            card.grid_columnconfigure(1, weight=1)
            Label(
                card,
                text=title,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                font=("Segoe UI", 9),
            ).grid(row=0, column=0, sticky="w")
            Label(
                card,
                textvariable=variable,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["accent_soft"],
                font=("Segoe UI Semibold", 11),
                justify="left",
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
            return card

        def _build_dojo_summary_tab(self, parent: Frame) -> None:
            parent.grid_rowconfigure(1, weight=1)
            statuses = Frame(parent, bg=launcher.COLORS["bg"])
            statuses.grid(row=0, column=0, sticky="ew")
            for column in range(4):
                statuses.grid_columnconfigure(column, weight=1, uniform="dojo_status")
            status_values = (
                (launcher._t(self.lang, "dojo_runtime"), self.dojo_runtime_var),
                (launcher._t(self.lang, "dojo_phase"), self.dojo_phase_var),
                (launcher._t(self.lang, "dojo_progress"), self.dojo_progress_var),
                (launcher._t(self.lang, "dojo_current_round"), self.dojo_current_round_var),
            )
            for column, (title, variable) in enumerate(status_values):
                self._dojo_status_card(statuses, title, variable).grid(
                    row=0,
                    column=column,
                    sticky="nsew",
                    padx=(0 if column == 0 else 5, 0 if column == 3 else 5),
                )

            body = Frame(parent, bg=launcher.COLORS["bg"])
            body.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
            body.grid_rowconfigure(0, weight=1)
            body.grid_columnconfigure(0, weight=3)
            body.grid_columnconfigure(1, weight=2)
            self._dojo_summary_body = body

            left = Frame(body, bg=launcher.COLORS["bg"])
            left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
            left.grid_columnconfigure(0, weight=1)
            left.grid_rowconfigure(1, weight=1)
            self._dojo_summary_left = left

            location = self._dojo_card(left)
            location.grid(row=0, column=0, sticky="ew")
            Label(
                location,
                text=launcher._t(self.lang, "dojo_location"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 11),
            ).pack(anchor="w")
            Label(
                location,
                textvariable=self.dojo_location_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["accent_soft"],
                font=("Segoe UI Semibold", 11),
            ).pack(anchor="w", pady=(8, 0))
            Label(
                location,
                textvariable=self.dojo_location_detail_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                font=("Consolas", 9),
            ).pack(anchor="w", pady=(3, 0))

            actions = self._dojo_card(left)
            actions.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
            actions.grid_rowconfigure(1, weight=1)
            actions.grid_columnconfigure(0, weight=1)
            Label(
                actions,
                text=launcher._t(self.lang, "dojo_recent_actions"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 11),
            ).grid(row=0, column=0, sticky="w", pady=(0, 8))
            recent = Listbox(
                actions,
                bg=launcher.COLORS["surface_alt"],
                fg=launcher.COLORS["text"],
                selectbackground=launcher.COLORS["selected"],
                selectforeground=launcher.COLORS["accent_soft"],
                relief="flat",
                bd=0,
                highlightthickness=0,
                font=("Consolas", 9),
                activestyle="none",
            )
            recent.grid(row=1, column=0, sticky="nsew")
            self._dojo_recent_list = recent

            right = Frame(body, bg=launcher.COLORS["bg"])
            right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
            right.grid_columnconfigure(0, weight=1)
            self._dojo_summary_right = right
            self._build_dojo_control_card(right, row=0)

            event = self._dojo_card(right)
            event.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
            Label(
                event,
                text=launcher._t(self.lang, "dojo_last_event"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
            ).pack(anchor="w")
            Label(
                event,
                textvariable=self.dojo_last_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                justify="left",
                anchor="nw",
                wraplength=440,
                font=("Consolas", 9),
            ).pack(fill=BOTH, expand=True, pady=(8, 0))

        def _build_dojo_control_card(self, parent: Frame, *, row: int) -> Frame:
            card = self._dojo_card(parent)
            card.grid(row=row, column=0, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            Label(
                card,
                text=launcher._t(self.lang, "dojo_training_control"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 11),
            ).grid(row=0, column=0, columnspan=3, sticky="w")
            Label(
                card,
                text=launcher._t(self.lang, "dojo_rounds"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
            ).grid(row=1, column=0, sticky="w", pady=(12, 4))
            rounds = Entry(
                card,
                textvariable=self.dojo_rounds_var,
                bg=launcher.COLORS["surface_alt"],
                fg=launcher.COLORS["text"],
                insertbackground=launcher.COLORS["accent"],
                relief="flat",
                justify="center",
                width=10,
            )
            rounds.grid(row=1, column=1, sticky="e", padx=(8, 0), pady=(12, 4), ipady=7)
            Label(
                card,
                text=launcher._t(self.lang, "dojo_rounds_help"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                justify="left",
                wraplength=360,
            ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 12))

            self._dojo_start_button = Button(
                card,
                text=launcher._t(self.lang, "dojo_start"),
                command=self.start_dojo,
                bg=launcher.COLORS["approve"],
                fg=launcher.COLORS["text"],
                activebackground=launcher.COLORS["selected"],
                activeforeground=launcher.COLORS["accent_soft"],
                relief="flat",
                padx=18,
                pady=11,
                font=("Segoe UI Semibold", 10),
            )
            self._dojo_start_button.grid(row=3, column=0, columnspan=3, sticky="ew")
            self._dojo_stop_button = Button(
                card,
                text=launcher._t(self.lang, "dojo_stop"),
                command=self.stop_dojo,
                bg=launcher.COLORS["button"],
                fg=launcher.COLORS["text"],
                activebackground=launcher.COLORS["selected"],
                activeforeground=launcher.COLORS["accent_soft"],
                relief="flat",
                padx=18,
                pady=10,
            )
            self._dojo_stop_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
            return card

        def _build_dojo_settings_tab(self, parent: Frame) -> None:
            card = self._dojo_card(parent, padx=20, pady=18)
            card.grid(row=0, column=0, sticky="new")
            card.grid_columnconfigure(0, weight=1)
            Label(
                card,
                text=launcher._t(self.lang, "dojo_existing_settings"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 12),
            ).grid(row=0, column=0, columnspan=2, sticky="w")
            Label(
                card,
                text=launcher._t(self.lang, "dojo_existing_settings_help"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                justify="left",
                wraplength=820,
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 16))
            Label(
                card,
                text=launcher._t(self.lang, "dojo_rounds"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
            ).grid(row=2, column=0, sticky="w")
            Entry(
                card,
                textvariable=self.dojo_rounds_var,
                bg=launcher.COLORS["surface_alt"],
                fg=launcher.COLORS["text"],
                insertbackground=launcher.COLORS["accent"],
                relief="flat",
                width=12,
                justify="center",
            ).grid(row=2, column=1, sticky="w", padx=(16, 0), ipady=8)
            Label(
                card,
                text=launcher._t(self.lang, "dojo_rounds_help"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
            ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        def _build_dojo_images_tab(self, parent: Frame) -> None:
            self._clear_dojo_template_widget_registry()
            parent.grid_rowconfigure(1, weight=1)
            header = self._dojo_card(parent, padx=18, pady=14)
            header.grid(row=0, column=0, sticky="ew")
            Label(
                header,
                text=launcher._t(self.lang, "dojo_templates"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 12),
            ).pack(anchor="w")
            Label(
                header,
                text=launcher._t(self.lang, "dojo_images_help_short"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                justify="left",
                wraplength=900,
            ).pack(anchor="w", pady=(5, 0))

            grid = Frame(parent, bg=launcher.COLORS["bg"])
            grid.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
            grid.grid_columnconfigure(0, weight=1, uniform="dojo_images")
            grid.grid_columnconfigure(1, weight=1, uniform="dojo_images")
            self._dojo_images_grid = grid
            for column, mode in enumerate(("64", "32")):
                card = self._build_template_card(grid, mode)
                card.grid(
                    row=0,
                    column=column,
                    sticky="nsew",
                    padx=(0 if column == 0 else 6, 0 if column == 1 else 6),
                )

            footer = self._dojo_card(parent, padx=18, pady=12)
            footer.grid(row=2, column=0, sticky="ew", pady=(12, 0))
            Label(
                footer,
                textvariable=self.dojo_template_summary_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["accent_soft"],
                font=("Segoe UI Semibold", 9),
            ).pack(anchor="w")
            Label(
                footer,
                textvariable=self.dojo_template_storage_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                justify="left",
                wraplength=900,
            ).pack(anchor="w", pady=(4, 0))

        def _build_dojo_logs_tab(self, parent: Frame) -> None:
            card = self._dojo_card(parent, padx=20, pady=18)
            card.grid(row=0, column=0, sticky="new")
            card.grid_columnconfigure(1, weight=1)
            Label(
                card,
                text=launcher._t(self.lang, "dojo_log_title"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 12),
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
            rows = (
                ("dojo_log_state", self.dojo_log_state_var),
                ("dojo_log_time", self.dojo_log_time_var),
                ("dojo_log_summary", self.dojo_log_summary_var),
                ("dojo_log_file", self.dojo_log_file_var),
            )
            for row, (key, variable) in enumerate(rows, start=1):
                Label(
                    card,
                    text=launcher._t(self.lang, key),
                    bg=launcher.COLORS["card"],
                    fg=launcher.COLORS["muted"],
                ).grid(row=row, column=0, sticky="nw", padx=(0, 18), pady=5)
                Label(
                    card,
                    textvariable=variable,
                    bg=launcher.COLORS["card"],
                    fg=launcher.COLORS["text"],
                    justify="left",
                    anchor="w",
                    wraplength=760,
                    font=("Consolas", 9) if key in {"dojo_log_summary", "dojo_log_file"} else None,
                ).grid(row=row, column=1, sticky="ew", pady=5)

            buttons = Frame(card, bg=launcher.COLORS["card"])
            buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(18, 0))
            self._dojo_log_open_button = Button(
                buttons,
                text=launcher._t(self.lang, "dojo_log_open"),
                command=self._dojo_open_log,
                bg=launcher.COLORS["approve"],
                fg=launcher.COLORS["text"],
                relief="flat",
                padx=16,
                pady=9,
            )
            self._dojo_log_open_button.pack(side=LEFT, padx=(0, 8))
            Button(
                buttons,
                text=launcher._t(self.lang, "dojo_log_open_folder"),
                command=self._dojo_open_log_folder,
                bg=launcher.COLORS["button"],
                fg=launcher.COLORS["text"],
                relief="flat",
                padx=16,
                pady=9,
            ).pack(side=LEFT)

        def _dojo_show_tab(self, key: str) -> None:
            value = key if key in self._dojo_tab_frames else "summary"
            self._dojo_active_tab = value
            for item, frame in self._dojo_tab_frames.items():
                if item == value:
                    frame.tkraise()
                button = self._dojo_tab_buttons.get(item)
                if button is not None:
                    button.configure(
                        bg=launcher.COLORS["selected"] if item == value else launcher.COLORS["card"],
                        fg=launcher.COLORS["accent_soft"] if item == value else launcher.COLORS["muted"],
                    )

        def _dojo_on_configure(self, event) -> None:
            if event.widget is not self.root:
                return
            if self._dojo_resize_after is not None:
                try:
                    self.root.after_cancel(self._dojo_resize_after)
                except Exception:
                    pass
            self._dojo_resize_after = self.root.after(120, self._dojo_apply_responsive_layout)

        def _dojo_apply_responsive_layout(self) -> None:
            self._dojo_resize_after = None
            body = self._dojo_summary_body
            left = self._dojo_summary_left
            right = self._dojo_summary_right
            image_grid = self._dojo_images_grid
            if body is None or left is None or right is None:
                return
            try:
                width = max(1, int(self.root.winfo_width()))
            except Exception:
                width = 1280
            compact = width < 1220
            left.grid_forget()
            right.grid_forget()
            if compact:
                body.grid_columnconfigure(0, weight=1)
                body.grid_columnconfigure(1, weight=0)
                body.grid_rowconfigure(0, weight=0)
                body.grid_rowconfigure(1, weight=1)
                right.grid(row=0, column=0, sticky="ew")
                left.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
            else:
                body.grid_columnconfigure(0, weight=3)
                body.grid_columnconfigure(1, weight=2)
                body.grid_rowconfigure(0, weight=1)
                body.grid_rowconfigure(1, weight=0)
                left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
                right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
            if image_grid is not None:
                for child in image_grid.grid_slaves():
                    child.grid_forget()
                cards = list(reversed(image_grid.winfo_children()))
                if compact:
                    image_grid.grid_columnconfigure(0, weight=1)
                    image_grid.grid_columnconfigure(1, weight=0)
                    for row, card in enumerate(cards):
                        card.grid(row=row, column=0, sticky="ew", pady=(0 if row == 0 else 6, 6))
                else:
                    image_grid.grid_columnconfigure(0, weight=1, uniform="dojo_images")
                    image_grid.grid_columnconfigure(1, weight=1, uniform="dojo_images")
                    for column, card in enumerate(cards):
                        card.grid(
                            row=0,
                            column=column,
                            sticky="nsew",
                            padx=(0 if column == 0 else 6, 0 if column == 1 else 6),
                        )

        def _location_text_for_payload(self, payload: dict) -> tuple[str, str]:
            state = str(payload.get("position_state") or "LOST").upper()
            last_line = str(payload.get("last_line") or "").upper()
            if "DOJO_RETURN_" in last_line or "RETURN_TO_ANCHOR" in last_line:
                key = "dojo_location_returning"
            elif "RELOCALIZ" in last_line:
                key = "dojo_location_relocalizing"
            elif state == "KNOWN":
                key = "dojo_location_known"
            elif state == "UNCERTAIN":
                key = "dojo_location_uncertain"
            else:
                key = "dojo_location_lost"
            try:
                x = float(payload.get("position_x", 0.0) or 0.0)
                y = float(payload.get("position_y", 0.0) or 0.0)
                confidence = max(0.0, min(1.0, float(payload.get("position_confidence", 0.0) or 0.0)))
            except (TypeError, ValueError):
                x = y = confidence = 0.0
            return (
                launcher._t(self.lang, key),
                launcher._t(self.lang, "dojo_location_detail", x=x, y=y, confidence=confidence),
            )

        def _apply_log_status(self, payload: dict) -> None:
            log = payload.get("last_log")
            if not isinstance(log, dict):
                log = payload if "exists" in payload else {}
            self._dojo_log_directory = str(log.get("directory") or "")
            if not bool(log.get("exists")):
                self._dojo_log_path = ""
                empty = launcher._t(self.lang, "dojo_log_empty")
                self.dojo_log_state_var.set(empty)
                self.dojo_log_time_var.set("—")
                self.dojo_log_summary_var.set("—")
                self.dojo_log_file_var.set("—")
                if self._dojo_log_open_button is not None:
                    self._dojo_log_open_button.configure(state="disabled")
                return
            self._dojo_log_path = str(log.get("path") or "")
            kind = str(log.get("kind") or "error")
            self.dojo_log_state_var.set(
                launcher._t(self.lang, "dojo_log_incomplete" if kind == "incomplete" else "dojo_log_error")
            )
            self.dojo_log_time_var.set(str(log.get("modified_at") or "—"))
            self.dojo_log_summary_var.set(str(log.get("summary") or "—"))
            self.dojo_log_file_var.set(str(log.get("filename") or self._dojo_log_path or "—"))
            if self._dojo_log_open_button is not None:
                self._dojo_log_open_button.configure(state="normal" if self._dojo_log_path else "disabled")

        def _apply_dojo_status(self, payload: dict) -> None:
            super()._apply_dojo_status(payload)
            self.dojo_current_round_var.set(str(int(payload.get("current_round", 0) or 0)))
            location, detail = self._location_text_for_payload(payload)
            self.dojo_location_var.set(location)
            self.dojo_location_detail_var.set(detail)
            actions = payload.get("recent_actions")
            if not isinstance(actions, list):
                actions = []
            if self._dojo_recent_list is not None:
                self._dojo_recent_list.delete(0, END)
                if actions:
                    for action in actions[-8:]:
                        self._dojo_recent_list.insert(END, str(action))
                else:
                    self._dojo_recent_list.insert(END, launcher._t(self.lang, "dojo_no_recent_actions"))
            self._apply_log_status(payload)

        def _dojo_open_log(self) -> None:
            try:
                _open_path(self._dojo_log_path)
            except Exception as error:
                from tkinter import messagebox

                messagebox.showerror(
                    "KageLink Dojo",
                    launcher._t(self.lang, "dojo_log_open_failed", error=error),
                    parent=self.root,
                )

        def _dojo_open_log_folder(self) -> None:
            try:
                _open_path(self._dojo_log_directory)
            except Exception as error:
                from tkinter import messagebox

                messagebox.showerror(
                    "KageLink Dojo",
                    launcher._t(self.lang, "dojo_log_open_failed", error=error),
                    parent=self.root,
                )

    return ReliableDojoDesktopUI


__all__ = ["install_dojo_reliability_desktop"]
