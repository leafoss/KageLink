from __future__ import annotations

import json
from pathlib import Path
import time
from tkinter import Button, Frame, Label, StringVar

from PIL import Image, ImageTk

import unified_dojo_ui_v351 as reliability
import unified_launcher as launcher
from pc_agent.kage_pilot.dojo_vision_lab_v351 import (
    VisionLabSettings,
    read_settings,
    vision_lab_root,
    write_settings,
)


launcher.TEXT["pt-BR"].update(
    {
        "dojo_tab_vision": "Vision Lab",
        "dojo_vision_title": "Dojo Vision Lab — visão real do pipeline",
        "dojo_vision_help": (
            "Mostra os mesmos frames processados pelo Dojo. Cada aquisição e rodada gera "
            "um vídeo, manifesto e imagens intermediárias em disco."
        ),
        "dojo_vision_enable": "Ativar laboratório",
        "dojo_vision_disable": "Desativar laboratório",
        "dojo_vision_pause": "Pausar tela",
        "dojo_vision_resume": "Retomar tela",
        "dojo_vision_open_session": "Abrir sessão atual",
        "dojo_vision_open_folder": "Abrir pasta do laboratório",
        "dojo_vision_waiting": "Aguardando frames do Dojo Trainer…",
        "dojo_vision_active": "Gravando",
        "dojo_vision_inactive": "Parado",
        "dojo_vision_enabled": "Ativo",
        "dojo_vision_disabled": "Desativado",
        "dojo_vision_last_update": "Última atualização: {seconds:.1f}s",
        "dojo_vision_frames": "Frames: {recorded}/{seen} · {fps:.1f} FPS",
        "dojo_vision_error": "Erro: {error}",
        "dojo_vision_raw": "Captura bruta",
        "dojo_vision_arena": "Arena usada",
        "dojo_vision_gray": "Escala de cinza",
        "dojo_vision_contrast": "Contraste/CLAHE",
        "dojo_vision_motion_mask": "Máscara de movimento",
        "dojo_vision_tracks": "Candidatos e alvos",
        "dojo_vision_trainer_scan": "Busca do Trainer",
        "dojo_vision_grid": "Grid efetivo",
        "dojo_vision_hud": "HUD tratado",
    }
)
launcher.TEXT["en-US"].update(
    {
        "dojo_tab_vision": "Vision Lab",
        "dojo_vision_title": "Dojo Vision Lab — real pipeline view",
        "dojo_vision_help": (
            "Shows the same frames processed by Dojo. Each acquisition and round writes "
            "a video, manifest and intermediate images to disk."
        ),
        "dojo_vision_enable": "Enable lab",
        "dojo_vision_disable": "Disable lab",
        "dojo_vision_pause": "Pause screen",
        "dojo_vision_resume": "Resume screen",
        "dojo_vision_open_session": "Open current session",
        "dojo_vision_open_folder": "Open lab folder",
        "dojo_vision_waiting": "Waiting for Dojo Trainer frames…",
        "dojo_vision_active": "Recording",
        "dojo_vision_inactive": "Stopped",
        "dojo_vision_enabled": "Enabled",
        "dojo_vision_disabled": "Disabled",
        "dojo_vision_last_update": "Last update: {seconds:.1f}s",
        "dojo_vision_frames": "Frames: {recorded}/{seen} · {fps:.1f} FPS",
        "dojo_vision_error": "Error: {error}",
        "dojo_vision_raw": "Raw capture",
        "dojo_vision_arena": "Arena input",
        "dojo_vision_gray": "Grayscale",
        "dojo_vision_contrast": "Contrast/CLAHE",
        "dojo_vision_motion_mask": "Motion mask",
        "dojo_vision_tracks": "Candidates and targets",
        "dojo_vision_trainer_scan": "Trainer search",
        "dojo_vision_grid": "Effective grid",
        "dojo_vision_hud": "Processed HUD",
    }
)


_PANEL_KEYS = (
    "raw",
    "arena",
    "gray",
    "contrast",
    "motion_mask",
    "tracks",
    "trainer_scan",
    "grid",
    "hud",
)


def install_dojo_vision_lab_desktop(base_class):
    """Add a file-backed Vision Lab without touching the game window or focus."""

    class DojoVisionLabDesktop(base_class):
        def __init__(self, root) -> None:
            self._dojo_vision_labels = {}
            self._dojo_vision_images = {}
            self._dojo_vision_mtimes = {}
            self._dojo_vision_poll_after = None
            self._dojo_vision_paused = False
            self._dojo_vision_current_session = ""
            self.dojo_vision_state_var = StringVar(master=root, value="—")
            self.dojo_vision_detail_var = StringVar(master=root, value="—")
            self.dojo_vision_session_var = StringVar(master=root, value="—")
            self._dojo_vision_toggle_button = None
            self._dojo_vision_pause_button = None
            super().__init__(root)
            self._dojo_vision_schedule_poll(immediate=True)

        def _rebuild_dojo_page_v351(self) -> None:
            original_tabs = reliability._DOJO_TABS
            if "vision" not in original_tabs:
                reliability._DOJO_TABS = original_tabs + ("vision",)
            try:
                super()._rebuild_dojo_page_v351()
            finally:
                reliability._DOJO_TABS = original_tabs
            frame = self._dojo_tab_frames.get("vision")
            if frame is not None:
                self._build_dojo_vision_lab_tab(frame)

        def _build_dojo_vision_lab_tab(self, parent: Frame) -> None:
            for child in parent.winfo_children():
                child.destroy()
            for column in range(3):
                parent.grid_columnconfigure(column, weight=1, uniform="dojo_vision")
            for row in range(2, 5):
                parent.grid_rowconfigure(row, weight=1)

            header = self._dojo_card(parent, padx=16, pady=12)
            header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
            header.grid_columnconfigure(0, weight=1)
            Label(
                header,
                text=launcher._t(self.lang, "dojo_vision_title"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 12),
            ).grid(row=0, column=0, sticky="w")
            Label(
                header,
                text=launcher._t(self.lang, "dojo_vision_help"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                justify="left",
                wraplength=720,
                font=("Segoe UI", 9),
            ).grid(row=1, column=0, sticky="w", pady=(5, 0))

            controls = Frame(header, bg=launcher.COLORS["card"])
            controls.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
            self._dojo_vision_toggle_button = self._vision_button(
                controls,
                "",
                self._dojo_vision_toggle,
            )
            self._dojo_vision_toggle_button.pack(side="left", padx=(0, 6))
            self._dojo_vision_pause_button = self._vision_button(
                controls,
                "",
                self._dojo_vision_toggle_pause,
            )
            self._dojo_vision_pause_button.pack(side="left", padx=(0, 6))
            self._vision_button(
                controls,
                launcher._t(self.lang, "dojo_vision_open_session"),
                self._dojo_vision_open_session,
            ).pack(side="left", padx=(0, 6))
            self._vision_button(
                controls,
                launcher._t(self.lang, "dojo_vision_open_folder"),
                self._dojo_vision_open_root,
            ).pack(side="left")

            status = self._dojo_card(parent, padx=14, pady=9)
            status.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10))
            status.grid_columnconfigure(1, weight=1)
            Label(
                status,
                textvariable=self.dojo_vision_state_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["accent_soft"],
                font=("Segoe UI Semibold", 10),
            ).grid(row=0, column=0, sticky="w")
            Label(
                status,
                textvariable=self.dojo_vision_detail_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                font=("Consolas", 9),
            ).grid(row=0, column=1, sticky="w", padx=(14, 0))
            Label(
                status,
                textvariable=self.dojo_vision_session_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                font=("Consolas", 8),
                anchor="e",
            ).grid(row=0, column=2, sticky="e", padx=(10, 0))

            self._dojo_vision_labels.clear()
            self._dojo_vision_images.clear()
            self._dojo_vision_mtimes.clear()
            for index, key in enumerate(_PANEL_KEYS):
                row, column = divmod(index, 3)
                card = self._dojo_card(parent, padx=8, pady=7)
                card.grid(
                    row=2 + row,
                    column=column,
                    sticky="nsew",
                    padx=(0 if column == 0 else 5, 0 if column == 2 else 5),
                    pady=(0 if row == 0 else 5, 0 if row == 2 else 5),
                )
                card.grid_rowconfigure(1, weight=1)
                card.grid_columnconfigure(0, weight=1)
                Label(
                    card,
                    text=launcher._t(self.lang, f"dojo_vision_{key}"),
                    bg=launcher.COLORS["card"],
                    fg=launcher.COLORS["text"],
                    font=("Segoe UI Semibold", 9),
                ).grid(row=0, column=0, sticky="w", pady=(0, 5))
                image_label = Label(
                    card,
                    text=launcher._t(self.lang, "dojo_vision_waiting"),
                    bg="#090c0a",
                    fg=launcher.COLORS["muted"],
                    anchor="center",
                    font=("Segoe UI", 8),
                )
                image_label.grid(row=1, column=0, sticky="nsew")
                self._dojo_vision_labels[key] = image_label
            self._dojo_vision_refresh_buttons()

        def _vision_button(self, parent, text, command):
            return Button(
                parent,
                text=text,
                command=command,
                bg=launcher.COLORS["card_alt"],
                fg=launcher.COLORS["text"],
                activebackground=launcher.COLORS["selected"],
                activeforeground=launcher.COLORS["accent_soft"],
                relief="flat",
                bd=0,
                padx=12,
                pady=7,
                font=("Segoe UI Semibold", 9),
            )

        def _dojo_vision_schedule_poll(self, *, immediate=False) -> None:
            try:
                if self._dojo_vision_poll_after is not None:
                    self.root.after_cancel(self._dojo_vision_poll_after)
            except Exception:
                pass
            try:
                self._dojo_vision_poll_after = self.root.after(
                    20 if immediate else 250,
                    self._dojo_vision_poll,
                )
            except Exception:
                self._dojo_vision_poll_after = None

        def _dojo_vision_poll(self) -> None:
            self._dojo_vision_poll_after = None
            try:
                self._dojo_vision_refresh_status()
                if not self._dojo_vision_paused:
                    self._dojo_vision_refresh_images()
            except Exception as error:
                self.dojo_vision_detail_var.set(
                    launcher._t(self.lang, "dojo_vision_error", error=error)
                )
            finally:
                self._dojo_vision_schedule_poll()

        def _dojo_vision_refresh_status(self) -> None:
            root = vision_lab_root()
            try:
                payload = json.loads((root / "live" / "status.json").read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    payload = {}
            except (OSError, ValueError, json.JSONDecodeError):
                payload = {}
            settings = read_settings()
            active = bool(payload.get("active"))
            state = launcher._t(
                self.lang,
                "dojo_vision_active" if active else "dojo_vision_inactive",
            )
            state += " · " + launcher._t(
                self.lang,
                "dojo_vision_enabled" if settings.enabled else "dojo_vision_disabled",
            )
            self.dojo_vision_state_var.set(state)

            updated_at = float(payload.get("updated_at", 0.0) or 0.0)
            age = max(0.0, time.time() - updated_at) if updated_at else 0.0
            seen = int(payload.get("seen", 0) or 0)
            recorded = int(payload.get("recorded", 0) or 0)
            fps = float(payload.get("fps", settings.fps) or settings.fps)
            details = [
                launcher._t(
                    self.lang,
                    "dojo_vision_frames",
                    recorded=recorded,
                    seen=seen,
                    fps=fps,
                )
            ]
            if updated_at:
                details.append(
                    launcher._t(self.lang, "dojo_vision_last_update", seconds=age)
                )
            source = str(payload.get("source") or "")
            if source:
                details.append(source)
            error = str(payload.get("error") or "").strip()
            if error:
                details.append(launcher._t(self.lang, "dojo_vision_error", error=error))
            self.dojo_vision_detail_var.set(" · ".join(details))

            session = str(payload.get("session_dir") or "").strip()
            self._dojo_vision_current_session = session
            self.dojo_vision_session_var.set(session or str(root))
            self._dojo_vision_refresh_buttons()

        def _dojo_vision_refresh_images(self) -> None:
            live = vision_lab_root() / "live"
            for key, label in tuple(self._dojo_vision_labels.items()):
                path = live / f"{key}.jpg"
                try:
                    signature = int(path.stat().st_mtime_ns)
                except OSError:
                    continue
                if self._dojo_vision_mtimes.get(key) == signature:
                    continue
                try:
                    with Image.open(path) as source:
                        image = source.convert("RGB")
                        width = max(260, int(label.winfo_width() or 300) - 8)
                        height = max(135, int(label.winfo_height() or 160) - 8)
                        image.thumbnail((width, height), Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(image)
                    label.configure(image=photo, text="")
                    self._dojo_vision_images[key] = photo
                    self._dojo_vision_mtimes[key] = signature
                except (OSError, ValueError):
                    continue

        def _dojo_vision_refresh_buttons(self) -> None:
            settings = read_settings()
            if self._dojo_vision_toggle_button is not None:
                self._dojo_vision_toggle_button.configure(
                    text=launcher._t(
                        self.lang,
                        "dojo_vision_disable" if settings.enabled else "dojo_vision_enable",
                    )
                )
            if self._dojo_vision_pause_button is not None:
                self._dojo_vision_pause_button.configure(
                    text=launcher._t(
                        self.lang,
                        "dojo_vision_resume" if self._dojo_vision_paused else "dojo_vision_pause",
                    )
                )

        def _dojo_vision_toggle(self) -> None:
            settings = read_settings()
            write_settings(
                VisionLabSettings(
                    enabled=not settings.enabled,
                    fps=settings.fps,
                    record_video=settings.record_video,
                    save_stages=settings.save_stages,
                    stage_interval=settings.stage_interval,
                    jpeg_quality=settings.jpeg_quality,
                )
            )
            self._dojo_vision_refresh_status()

        def _dojo_vision_toggle_pause(self) -> None:
            self._dojo_vision_paused = not self._dojo_vision_paused
            self._dojo_vision_refresh_buttons()
            if not self._dojo_vision_paused:
                self._dojo_vision_mtimes.clear()
                self._dojo_vision_refresh_images()

        def _dojo_vision_open_root(self) -> None:
            root = vision_lab_root()
            root.mkdir(parents=True, exist_ok=True)
            reliability._open_path(str(root))

        def _dojo_vision_open_session(self) -> None:
            value = self._dojo_vision_current_session.strip()
            path = Path(value) if value else vision_lab_root()
            if not path.exists():
                path = vision_lab_root()
                path.mkdir(parents=True, exist_ok=True)
            reliability._open_path(str(path))

    return DojoVisionLabDesktop


__all__ = ["install_dojo_vision_lab_desktop"]
