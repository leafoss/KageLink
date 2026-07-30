from __future__ import annotations

import threading
from tkinter import BooleanVar, Checkbutton, Entry, Frame, Label, OptionMenu, StringVar, messagebox

import unified_launcher as launcher


launcher.TEXT["pt-BR"].update(
    {
        "dojo_debug_title": "Debug visual",
        "dojo_debug_enabled": "Exibir overlay sobre o jogo",
        "dojo_debug_level": "Nível",
        "dojo_debug_basic": "Básico",
        "dojo_debug_detections": "Detecções",
        "dojo_debug_processed": "Visão processada",
        "dojo_debug_opacity": "Opacidade (%)",
        "dojo_debug_fps": "FPS do overlay",
        "dojo_meditation_title": "Recuperação e meditação",
        "dojo_meditation_state": "Estado da meditação",
        "dojo_meditation_idle": "Inativa",
        "dojo_meditation_entering": "Entrando em meditação",
        "dojo_meditation_active": "Meditando",
        "dojo_meditation_exiting": "Saindo da meditação",
        "dojo_meditation_ready": "Recuperação concluída",
        "dojo_meditation_timeout": "Timeout de recuperação",
        "dojo_meditation_aborted": "Recuperação interrompida",
        "dojo_meditation_detail": "HP {hp} · Chakra {chakra} · V {cooldown:.1f}s",
        "dojo_meditation_enter_delay": "Delay para entrar (s)",
        "dojo_meditation_exit_delay": "Delay para sair (s)",
        "dojo_meditation_timeout_seconds": "Timeout (s)",
        "dojo_recovery_hp": "HP alvo (%)",
        "dojo_recovery_chakra": "Chakra alvo (%)",
        "dojo_combat_gate": "Início do combate",
        "dojo_combat_blocked": "Bloqueado",
        "dojo_combat_allowed": "Liberado",
        "dojo_debug_help": (
            "Os valores são carregados do backend e aplicados ao clicar em Iniciar. "
            "A opacidade aceita 10 a 100. F10 liga ou desliga o overlay durante a execução."
        ),
        "dojo_debug_invalid": "Revise os valores de debug e recuperação.",
        "dojo_debug_update_failed": "Não foi possível atualizar o debug:\n\n{error}",
    }
)
launcher.TEXT["en-US"].update(
    {
        "dojo_debug_title": "Visual debug",
        "dojo_debug_enabled": "Show overlay over the game",
        "dojo_debug_level": "Level",
        "dojo_debug_basic": "Basic",
        "dojo_debug_detections": "Detections",
        "dojo_debug_processed": "Processed view",
        "dojo_debug_opacity": "Opacity (%)",
        "dojo_debug_fps": "Overlay FPS",
        "dojo_meditation_title": "Recovery and meditation",
        "dojo_meditation_state": "Meditation state",
        "dojo_meditation_idle": "Idle",
        "dojo_meditation_entering": "Entering meditation",
        "dojo_meditation_active": "Meditating",
        "dojo_meditation_exiting": "Exiting meditation",
        "dojo_meditation_ready": "Recovery complete",
        "dojo_meditation_timeout": "Recovery timeout",
        "dojo_meditation_aborted": "Recovery aborted",
        "dojo_meditation_detail": "HP {hp} · Chakra {chakra} · V {cooldown:.1f}s",
        "dojo_meditation_enter_delay": "Enter delay (s)",
        "dojo_meditation_exit_delay": "Exit delay (s)",
        "dojo_meditation_timeout_seconds": "Timeout (s)",
        "dojo_recovery_hp": "Target HP (%)",
        "dojo_recovery_chakra": "Target Chakra (%)",
        "dojo_combat_gate": "Combat start",
        "dojo_combat_blocked": "Blocked",
        "dojo_combat_allowed": "Allowed",
        "dojo_debug_help": (
            "Values are loaded from the backend and applied when Start is clicked. "
            "Opacity accepts 10 to 100. F10 toggles the overlay while training is running."
        ),
        "dojo_debug_invalid": "Review the debug and recovery values.",
        "dojo_debug_update_failed": "The visual debug could not be updated:\n\n{error}",
    }
)


_LEVEL_LABELS = {
    "basic": "dojo_debug_basic",
    "detections": "dojo_debug_detections",
    "processed": "dojo_debug_processed",
}
_MEDITATION_LABELS = {
    "IDLE": "dojo_meditation_idle",
    "ENTERING_MEDITATION": "dojo_meditation_entering",
    "MEDITATING": "dojo_meditation_active",
    "EXITING_MEDITATION": "dojo_meditation_exiting",
    "READY": "dojo_meditation_ready",
    "MEDITATION_TIMEOUT": "dojo_meditation_timeout",
    "ABORTED": "dojo_meditation_aborted",
}


def install_dojo_debug_desktop(base_class):
    """Add PR23 meditation diagnostics and backend-backed settings to the Dojo UI."""

    class DebugDojoDesktopUI(base_class):
        def __init__(self, root) -> None:
            self.dojo_debug_enabled_var = BooleanVar(value=False)
            self.dojo_debug_level_var = StringVar(value="detections")
            self.dojo_debug_opacity_var = StringVar(value="85")
            self.dojo_debug_fps_var = StringVar(value="15")
            self.dojo_meditation_enter_delay_var = StringVar(value="5.5")
            self.dojo_meditation_exit_delay_var = StringVar(value="5.5")
            self.dojo_meditation_timeout_var = StringVar(value="120")
            self.dojo_recovery_hp_var = StringVar(value="90")
            self.dojo_recovery_chakra_var = StringVar(value="40")
            self.dojo_meditation_state_var = StringVar(value="—")
            self.dojo_meditation_detail_var = StringVar(value="—")
            self.dojo_combat_gate_var = StringVar(value="—")
            self._dojo_debug_syncing = False
            self._dojo_setting_dirty: set[str] = set()
            self._dojo_setting_vars = {
                "enabled": self.dojo_debug_enabled_var,
                "level": self.dojo_debug_level_var,
                "opacity": self.dojo_debug_opacity_var,
                "fps": self.dojo_debug_fps_var,
                "recovery_hp_percent": self.dojo_recovery_hp_var,
                "recovery_chakra_percent": self.dojo_recovery_chakra_var,
                "meditation_enter_delay_seconds": self.dojo_meditation_enter_delay_var,
                "meditation_exit_delay_seconds": self.dojo_meditation_exit_delay_var,
                "meditation_timeout_seconds": self.dojo_meditation_timeout_var,
            }
            super().__init__(root)
            for field, variable in self._dojo_setting_vars.items():
                variable.trace_add(
                    "write",
                    lambda *_args, name=field: self._dojo_mark_setting_dirty(name),
                )

        def _dojo_mark_setting_dirty(self, field: str) -> None:
            if not self._dojo_debug_syncing:
                self._dojo_setting_dirty.add(str(field))

        def _dojo_set_backend_value(self, field: str, variable, value) -> None:
            if field not in self._dojo_setting_dirty:
                variable.set(value)

        def _build_dojo_summary_tab(self, parent: Frame) -> None:
            super()._build_dojo_summary_tab(parent)
            right = getattr(self, "_dojo_summary_right", None)
            if right is None:
                return
            meditation = self._dojo_card(right)
            meditation.grid(row=2, column=0, sticky="ew", pady=(12, 0))
            meditation.grid_columnconfigure(0, weight=1)
            Label(
                meditation,
                text=launcher._t(self.lang, "dojo_meditation_title"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 11),
            ).grid(row=0, column=0, columnspan=2, sticky="w")
            Label(
                meditation,
                textvariable=self.dojo_meditation_state_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["accent_soft"],
                font=("Segoe UI Semibold", 10),
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
            Label(
                meditation,
                textvariable=self.dojo_meditation_detail_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                font=("Consolas", 9),
            ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
            Label(
                meditation,
                text=launcher._t(self.lang, "dojo_combat_gate"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
            ).grid(row=3, column=0, sticky="w", pady=(8, 0))
            Label(
                meditation,
                textvariable=self.dojo_combat_gate_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 9),
            ).grid(row=3, column=1, sticky="e", pady=(8, 0))

        def _setting_entry(self, card: Frame, *, row: int, label_key: str, variable: StringVar) -> None:
            Label(
                card,
                text=launcher._t(self.lang, label_key),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
            ).grid(row=row, column=0, sticky="w", pady=5)
            Entry(
                card,
                textvariable=variable,
                bg=launcher.COLORS["surface_alt"],
                fg=launcher.COLORS["text"],
                insertbackground=launcher.COLORS["accent"],
                relief="flat",
                width=12,
                justify="center",
            ).grid(row=row, column=1, sticky="w", padx=(16, 0), pady=5, ipady=6)

        def _build_dojo_settings_tab(self, parent: Frame) -> None:
            super()._build_dojo_settings_tab(parent)
            card = self._dojo_card(parent, padx=20, pady=18)
            card.grid(row=1, column=0, sticky="new", pady=(12, 0))
            card.grid_columnconfigure(0, weight=1)
            Label(
                card,
                text=launcher._t(self.lang, "dojo_debug_title"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 12),
            ).grid(row=0, column=0, columnspan=2, sticky="w")
            Checkbutton(
                card,
                text=launcher._t(self.lang, "dojo_debug_enabled"),
                variable=self.dojo_debug_enabled_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                activebackground=launcher.COLORS["card"],
                activeforeground=launcher.COLORS["accent_soft"],
                selectcolor=launcher.COLORS["surface_alt"],
                highlightthickness=0,
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 6))

            Label(
                card,
                text=launcher._t(self.lang, "dojo_debug_level"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
            ).grid(row=2, column=0, sticky="w", pady=5)
            current_level = str(self.dojo_debug_level_var.get() or "detections").strip().lower()
            if current_level not in _LEVEL_LABELS:
                current_level = "detections"
            level_labels = {
                key: launcher._t(self.lang, label_key)
                for key, label_key in _LEVEL_LABELS.items()
            }
            self.dojo_debug_level_var.set(level_labels[current_level])
            level_menu = OptionMenu(
                card,
                self.dojo_debug_level_var,
                *(level_labels[key] for key in ("basic", "detections", "processed")),
            )
            level_menu.configure(
                bg=launcher.COLORS["surface_alt"],
                fg=launcher.COLORS["text"],
                activebackground=launcher.COLORS["selected"],
                activeforeground=launcher.COLORS["accent_soft"],
                relief="flat",
                highlightthickness=0,
                width=14,
            )
            level_menu["menu"].configure(
                bg=launcher.COLORS["surface_alt"],
                fg=launcher.COLORS["text"],
            )
            level_menu.grid(row=2, column=1, sticky="w", padx=(16, 0), pady=5)

            rows = (
                (3, "dojo_debug_opacity", self.dojo_debug_opacity_var),
                (4, "dojo_debug_fps", self.dojo_debug_fps_var),
                (5, "dojo_recovery_hp", self.dojo_recovery_hp_var),
                (6, "dojo_recovery_chakra", self.dojo_recovery_chakra_var),
                (7, "dojo_meditation_enter_delay", self.dojo_meditation_enter_delay_var),
                (8, "dojo_meditation_exit_delay", self.dojo_meditation_exit_delay_var),
                (9, "dojo_meditation_timeout_seconds", self.dojo_meditation_timeout_var),
            )
            for row, key, variable in rows:
                self._setting_entry(card, row=row, label_key=key, variable=variable)
            Label(
                card,
                text=launcher._t(self.lang, "dojo_debug_help"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["accent_soft"],
                justify="left",
                wraplength=820,
            ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(12, 0))

        @staticmethod
        def _percent_text(value) -> str:
            try:
                return f"{max(0.0, min(1.0, float(value))) * 100:.0f}%"
            except (TypeError, ValueError):
                return "—"

        def _debug_request_payload(self) -> dict:
            try:
                opacity_percent = float(self.dojo_debug_opacity_var.get().strip())
                fps = float(self.dojo_debug_fps_var.get().strip())
                enter_delay = float(self.dojo_meditation_enter_delay_var.get().strip())
                exit_delay = float(self.dojo_meditation_exit_delay_var.get().strip())
                timeout = float(self.dojo_meditation_timeout_var.get().strip())
                hp = float(self.dojo_recovery_hp_var.get().strip())
                chakra = float(self.dojo_recovery_chakra_var.get().strip())
                if not 10.0 <= opacity_percent <= 100.0:
                    raise ValueError
                if not 5.0 <= fps <= 30.0:
                    raise ValueError
                if not 5.0 <= enter_delay <= 30.0 or not 5.0 <= exit_delay <= 30.0:
                    raise ValueError
                if not 15.0 <= timeout <= 1800.0:
                    raise ValueError
                if not 90.0 <= hp <= 100.0 or not 40.0 <= chakra <= 100.0:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError(launcher._t(self.lang, "dojo_debug_invalid"))
            selected_level = str(self.dojo_debug_level_var.get() or "").strip()
            labels_to_level = {
                launcher._t(self.lang, label_key): key
                for key, label_key in _LEVEL_LABELS.items()
            }
            level = labels_to_level.get(selected_level, selected_level.lower())
            if level not in _LEVEL_LABELS:
                level = "detections"
            return {
                "enabled": bool(self.dojo_debug_enabled_var.get()),
                "level": level,
                "opacity": opacity_percent / 100.0,
                "fps": fps,
                "meditation_enter_delay_seconds": enter_delay,
                "meditation_exit_delay_seconds": exit_delay,
                "meditation_timeout_seconds": timeout,
                "recovery_hp_percent": hp,
                "recovery_chakra_percent": chakra,
            }

        def _dojo_update_debug_live(self) -> None:
            """Compatibility hook; numeric and selection edits are intentionally Start-bound."""
            if self._dojo_debug_syncing:
                return
            try:
                values = self._debug_request_payload()
            except ValueError:
                return
            payload = {
                key: values[key]
                for key in (
                    "enabled",
                    "level",
                    "opacity",
                    "fps",
                    "meditation_enter_delay_seconds",
                    "meditation_exit_delay_seconds",
                    "meditation_timeout_seconds",
                )
            }

            def worker() -> None:
                try:
                    response = self._api_json("POST", "/api/dojo/debug", payload, timeout=5)
                    self.ui(lambda value=response: self._apply_dojo_status(value))
                except Exception as error:
                    self.ui(
                        lambda value=error: messagebox.showerror(
                            "KageLink Dojo",
                            launcher._t(self.lang, "dojo_debug_update_failed", error=value),
                            parent=self.root,
                        )
                    )

            threading.Thread(target=worker, name="DojoDebugUpdate", daemon=True).start()

        def _accept_started_dojo_status(self, payload: dict) -> None:
            self._dojo_setting_dirty.clear()
            self._apply_dojo_status(payload)

        def start_dojo(self) -> None:
            try:
                rounds = int(self.dojo_rounds_var.get().strip())
                if not 0 <= rounds <= 999:
                    raise ValueError
                values = self._debug_request_payload()
            except ValueError as error:
                messagebox.showerror(
                    "KageLink",
                    str(error) or launcher._t(self.lang, "dojo_invalid_rounds"),
                    parent=self.root,
                )
                return
            if self._dojo_busy:
                return
            self._dojo_busy = True
            self._update_dojo_buttons()
            payload = {
                "rounds": rounds,
                "recovery_hp_percent": values["recovery_hp_percent"],
                "recovery_chakra_percent": values["recovery_chakra_percent"],
                "debug_visual": values["enabled"],
                "debug_level": values["level"],
                "debug_overlay_opacity": values["opacity"],
                "debug_overlay_fps": values["fps"],
                "meditation_enter_delay_seconds": values["meditation_enter_delay_seconds"],
                "meditation_exit_delay_seconds": values["meditation_exit_delay_seconds"],
                "meditation_timeout_seconds": values["meditation_timeout_seconds"],
            }

            def worker() -> None:
                try:
                    response = self._api_json("POST", "/api/dojo/start", payload, timeout=15)
                    self.ui(lambda value=response: self._accept_started_dojo_status(value))
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

        def _apply_dojo_status(self, payload: dict) -> None:
            super()._apply_dojo_status(payload)
            debug = payload.get("debug")
            defaults = payload.get("defaults")
            recovery_defaults = (
                defaults.get("recovery", {})
                if isinstance(defaults, dict)
                else {}
            )
            if isinstance(debug, dict):
                self._dojo_debug_syncing = True
                try:
                    self._dojo_set_backend_value(
                        "enabled",
                        self.dojo_debug_enabled_var,
                        bool(debug.get("enabled", False)),
                    )
                    level = str(debug.get("level") or "detections")
                    if level not in _LEVEL_LABELS:
                        level = "detections"
                    self._dojo_set_backend_value(
                        "level",
                        self.dojo_debug_level_var,
                        launcher._t(self.lang, _LEVEL_LABELS[level]),
                    )
                    self._dojo_set_backend_value(
                        "opacity",
                        self.dojo_debug_opacity_var,
                        f"{float(debug.get('opacity', 0.85)) * 100:.0f}",
                    )
                    self._dojo_set_backend_value(
                        "fps",
                        self.dojo_debug_fps_var,
                        f"{float(debug.get('fps', 15.0)):.0f}",
                    )
                    self._dojo_set_backend_value(
                        "meditation_enter_delay_seconds",
                        self.dojo_meditation_enter_delay_var,
                        f"{float(debug.get('meditation_enter_delay_seconds', 5.5)):.1f}",
                    )
                    self._dojo_set_backend_value(
                        "meditation_exit_delay_seconds",
                        self.dojo_meditation_exit_delay_var,
                        f"{float(debug.get('meditation_exit_delay_seconds', 5.5)):.1f}",
                    )
                    self._dojo_set_backend_value(
                        "meditation_timeout_seconds",
                        self.dojo_meditation_timeout_var,
                        f"{float(debug.get('meditation_timeout_seconds', 120.0)):.0f}",
                    )
                    hp = payload.get(
                        "recovery_hp_percent",
                        recovery_defaults.get("hp_percent", 90.0),
                    )
                    chakra = payload.get(
                        "recovery_chakra_percent",
                        recovery_defaults.get("chakra_percent", 40.0),
                    )
                    self._dojo_set_backend_value(
                        "recovery_hp_percent",
                        self.dojo_recovery_hp_var,
                        f"{float(hp):.0f}",
                    )
                    self._dojo_set_backend_value(
                        "recovery_chakra_percent",
                        self.dojo_recovery_chakra_var,
                        f"{float(chakra):.0f}",
                    )
                except (TypeError, ValueError):
                    pass
                finally:
                    self._dojo_debug_syncing = False

            state = str(payload.get("meditation_state") or "IDLE").upper()
            state_key = _MEDITATION_LABELS.get(state, "dojo_meditation_idle")
            self.dojo_meditation_state_var.set(launcher._t(self.lang, state_key))
            self.dojo_meditation_detail_var.set(
                launcher._t(
                    self.lang,
                    "dojo_meditation_detail",
                    hp=self._percent_text(payload.get("meditation_hp")),
                    chakra=self._percent_text(payload.get("meditation_chakra")),
                    cooldown=max(0.0, float(payload.get("v_cooldown_remaining", 0.0) or 0.0)),
                )
            )
            self.dojo_combat_gate_var.set(
                launcher._t(
                    self.lang,
                    "dojo_combat_blocked"
                    if bool(payload.get("combat_start_blocked"))
                    else "dojo_combat_allowed",
                )
            )

    return DebugDojoDesktopUI


__all__ = ["install_dojo_debug_desktop"]
