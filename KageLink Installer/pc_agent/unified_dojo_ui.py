from __future__ import annotations

import threading
from tkinter import BOTH, LEFT, X, Button, Entry, Frame, Label, StringVar, messagebox

import unified_launcher as launcher


launcher.TEXT["pt-BR"].update(
    {
        "dojo": "Dojo Trainer",
        "dojo_title": "Treinamento autônomo no Dojo",
        "dojo_help": (
            "O KageLink controla o Taijutsu Dojo pelo PC Agent. Durante o treino, "
            "os controles manuais da aba GAME ficam bloqueados para evitar comandos concorrentes."
        ),
        "dojo_rounds": "Rodadas",
        "dojo_rounds_help": "Use 0 para continuar até F12 ou Parar. Máximo: 999.",
        "dojo_start": "Iniciar treino",
        "dojo_stop": "Parar com segurança",
        "dojo_phase": "Fase",
        "dojo_progress": "Progresso",
        "dojo_runtime": "Motor",
        "dojo_last_event": "Último evento",
        "dojo_available": "Instalado",
        "dojo_unavailable": "Não instalado",
        "dojo_idle": "Parado",
        "dojo_starting": "Iniciando",
        "dojo_requesting": "Solicitando luta",
        "dojo_combat": "Em combate",
        "dojo_victory": "Vitória confirmada",
        "dojo_recovery": "Recuperando",
        "dojo_ready": "Pronto",
        "dojo_stopping": "Parando",
        "dojo_stopped": "Finalizado",
        "dojo_error": "Erro",
        "dojo_round_progress": "{completed} concluída(s) · rodada atual {current}",
        "dojo_invalid_rounds": "Informe de 0 a 999 rodadas.",
        "dojo_start_failed": "Não foi possível iniciar o Dojo Trainer:\n\n{error}",
        "dojo_stop_failed": "Não foi possível parar o Dojo Trainer:\n\n{error}",
        "dojo_f12": "F12 permanece como parada de emergência dentro do jogo.",
    }
)
launcher.TEXT["en-US"].update(
    {
        "dojo": "Dojo Trainer",
        "dojo_title": "Autonomous Dojo training",
        "dojo_help": (
            "KageLink controls the Taijutsu Dojo through the PC Agent. While training, "
            "manual GAME controls are blocked to prevent competing commands."
        ),
        "dojo_rounds": "Rounds",
        "dojo_rounds_help": "Use 0 to continue until F12 or Stop. Maximum: 999.",
        "dojo_start": "Start training",
        "dojo_stop": "Stop safely",
        "dojo_phase": "Phase",
        "dojo_progress": "Progress",
        "dojo_runtime": "Runtime",
        "dojo_last_event": "Last event",
        "dojo_available": "Installed",
        "dojo_unavailable": "Not installed",
        "dojo_idle": "Idle",
        "dojo_starting": "Starting",
        "dojo_requesting": "Requesting fight",
        "dojo_combat": "In combat",
        "dojo_victory": "Victory confirmed",
        "dojo_recovery": "Recovering",
        "dojo_ready": "Ready",
        "dojo_stopping": "Stopping",
        "dojo_stopped": "Finished",
        "dojo_error": "Error",
        "dojo_round_progress": "{completed} completed · current round {current}",
        "dojo_invalid_rounds": "Enter from 0 to 999 rounds.",
        "dojo_start_failed": "The Dojo Trainer could not start:\n\n{error}",
        "dojo_stop_failed": "The Dojo Trainer could not stop:\n\n{error}",
        "dojo_f12": "F12 remains the in-game emergency stop.",
    }
)


_PHASE_KEYS = {
    "idle": "dojo_idle",
    "starting": "dojo_starting",
    "requesting": "dojo_requesting",
    "combat": "dojo_combat",
    "victory": "dojo_victory",
    "recovery": "dojo_recovery",
    "ready": "dojo_ready",
    "stopping": "dojo_stopping",
    "stopped": "dojo_stopped",
    "error": "dojo_error",
}


def install_dojo_desktop(base_class):
    class DojoEnabledKageLinkAgentUI(base_class):
        def __init__(self, root) -> None:
            self.dojo_phase_var = StringVar(value="—")
            self.dojo_progress_var = StringVar(value="0")
            self.dojo_runtime_var = StringVar(value="—")
            self.dojo_last_var = StringVar(value="—")
            self.dojo_rounds_var = StringVar(value="10")
            self._dojo_running = False
            self._dojo_busy = False
            self._dojo_start_button = None
            self._dojo_stop_button = None
            super().__init__(root)
            self.root.after(1100, self._refresh_dojo_status)

        def _build_ui(self) -> None:
            super()._build_ui()
            sidebar = self._page_buttons["overview"].master
            content = self._pages["overview"].master
            key = "dojo"
            button = Button(
                sidebar,
                text=launcher._t(self.lang, key),
                command=lambda: self._show_page(key),
                anchor="w",
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                activebackground=launcher.COLORS["selected"],
                activeforeground=launcher.COLORS["accent_soft"],
                relief="flat",
                bd=0,
                padx=18,
                pady=13,
                font=("Segoe UI Semibold", 10),
            )
            button.pack(fill=X, padx=8, pady=(2, 0))
            page = Frame(content, bg=launcher.COLORS["bg"])
            self._page_buttons[key] = button
            self._pages[key] = page
            self._build_dojo_page(page)

        def _build_dojo_page(self, page: Frame) -> None:
            self._section_title(page, launcher._t(self.lang, "dojo_title"))
            intro = self._card(page)
            intro.pack(fill=X)
            Label(
                intro,
                text=launcher._t(self.lang, "dojo_help"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                wraplength=820,
                justify="left",
            ).pack(anchor="w")
            Label(
                intro,
                text=launcher._t(self.lang, "dojo_f12"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["accent_soft"],
                font=("Segoe UI Semibold", 9),
            ).pack(anchor="w", pady=(8, 0))

            statuses = Frame(page, bg=launcher.COLORS["bg"])
            statuses.pack(fill=X, pady=(14, 0))
            for title, variable in (
                (launcher._t(self.lang, "dojo_runtime"), self.dojo_runtime_var),
                (launcher._t(self.lang, "dojo_phase"), self.dojo_phase_var),
                (launcher._t(self.lang, "dojo_progress"), self.dojo_progress_var),
            ):
                self._status_card(statuses, title, variable).pack(
                    side=LEFT,
                    fill=X,
                    expand=True,
                    padx=4,
                )

            controls = self._card(page)
            controls.pack(fill=X, pady=(14, 0))
            Label(
                controls,
                text=launcher._t(self.lang, "dojo_rounds"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
            ).pack(anchor="w")
            Entry(
                controls,
                textvariable=self.dojo_rounds_var,
                bg=launcher.COLORS["surface_alt"],
                fg=launcher.COLORS["text"],
                insertbackground=launcher.COLORS["accent"],
                relief="flat",
                width=10,
            ).pack(anchor="w", ipady=8, pady=(5, 3))
            Label(
                controls,
                text=launcher._t(self.lang, "dojo_rounds_help"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
            ).pack(anchor="w", pady=(0, 12))
            buttons = Frame(controls, bg=launcher.COLORS["card"])
            buttons.pack(fill=X)
            self._dojo_start_button = Button(
                buttons,
                text=launcher._t(self.lang, "dojo_start"),
                command=self.start_dojo,
                bg=launcher.COLORS["approve"],
                fg=launcher.COLORS["text"],
                relief="flat",
                padx=18,
                pady=10,
                font=("Segoe UI Semibold", 10),
            )
            self._dojo_start_button.pack(side=LEFT, padx=(0, 8))
            self._dojo_stop_button = Button(
                buttons,
                text=launcher._t(self.lang, "dojo_stop"),
                command=self.stop_dojo,
                bg=launcher.COLORS["button"],
                fg=launcher.COLORS["text"],
                relief="flat",
                padx=18,
                pady=10,
            )
            self._dojo_stop_button.pack(side=LEFT)

            events = self._card(page)
            events.pack(fill=BOTH, expand=True, pady=(14, 0))
            Label(
                events,
                text=launcher._t(self.lang, "dojo_last_event"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
            ).pack(anchor="w")
            Label(
                events,
                textvariable=self.dojo_last_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                justify="left",
                anchor="nw",
                wraplength=820,
                font=("Consolas", 9),
            ).pack(fill=BOTH, expand=True, pady=(8, 0))
            self._update_dojo_buttons()

        def _update_dojo_buttons(self) -> None:
            if self._dojo_start_button is None or self._dojo_stop_button is None:
                return
            start_state = "disabled" if self._dojo_running or self._dojo_busy else "normal"
            stop_state = "normal" if self._dojo_running and not self._dojo_busy else "disabled"
            self._dojo_start_button.configure(state=start_state)
            self._dojo_stop_button.configure(state=stop_state)

        def _apply_dojo_status(self, payload: dict) -> None:
            available = bool(payload.get("available"))
            self._dojo_running = bool(payload.get("running"))
            phase = str(payload.get("phase") or "idle")
            phase_key = _PHASE_KEYS.get(phase, "dojo_idle")
            self.dojo_runtime_var.set(
                launcher._t(self.lang, "dojo_available" if available else "dojo_unavailable")
            )
            self.dojo_phase_var.set(launcher._t(self.lang, phase_key))
            self.dojo_progress_var.set(
                launcher._t(
                    self.lang,
                    "dojo_round_progress",
                    completed=int(payload.get("completed_rounds", 0) or 0),
                    current=int(payload.get("current_round", 0) or 0),
                )
            )
            last_error = str(payload.get("last_error") or "").strip()
            last_line = str(payload.get("last_line") or "").strip()
            self.dojo_last_var.set(last_error or last_line or "—")
            self._update_dojo_buttons()

        def _refresh_dojo_status(self) -> None:
            if self.stopping:
                return
            try:
                if self._server_is_healthy():
                    payload = self._api_json("GET", "/api/dojo/status", timeout=2.5)
                    self._apply_dojo_status(payload)
            except Exception:
                pass
            finally:
                self.root.after(1200, self._refresh_dojo_status)

        def start_dojo(self) -> None:
            try:
                rounds = int(self.dojo_rounds_var.get().strip())
                if not 0 <= rounds <= 999:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "KageLink",
                    launcher._t(self.lang, "dojo_invalid_rounds"),
                    parent=self.root,
                )
                return
            if self._dojo_busy:
                return
            self._dojo_busy = True
            self._update_dojo_buttons()

            def worker() -> None:
                try:
                    payload = self._api_json(
                        "POST",
                        "/api/dojo/start",
                        {"rounds": rounds},
                        timeout=15,
                    )
                    self.ui(lambda value=payload: self._apply_dojo_status(value))
                    self.ui(lambda: self._show_page("dojo"))
                except Exception as error:
                    self.ui(
                        lambda value=error: messagebox.showerror(
                            "KageLink Dojo",
                            launcher._t(self.lang, "dojo_start_failed", error=value),
                            parent=self.root,
                        )
                    )
                finally:
                    self._dojo_busy = False
                    self.ui(self._update_dojo_buttons)

            threading.Thread(target=worker, name="DojoStart", daemon=True).start()

        def stop_dojo(self) -> None:
            if self._dojo_busy:
                return
            self._dojo_busy = True
            self._update_dojo_buttons()

            def worker() -> None:
                try:
                    payload = self._api_json("POST", "/api/dojo/stop", {}, timeout=15)
                    self.ui(lambda value=payload: self._apply_dojo_status(value))
                except Exception as error:
                    self.ui(
                        lambda value=error: messagebox.showerror(
                            "KageLink Dojo",
                            launcher._t(self.lang, "dojo_stop_failed", error=value),
                            parent=self.root,
                        )
                    )
                finally:
                    self._dojo_busy = False
                    self.ui(self._update_dojo_buttons)

            threading.Thread(target=worker, name="DojoStop", daemon=True).start()

    return DojoEnabledKageLinkAgentUI


__all__ = ["install_dojo_desktop"]
