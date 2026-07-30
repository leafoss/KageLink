from __future__ import annotations

import base64
import math
from pathlib import Path
import threading
from tkinter import (
    BOTH,
    LEFT,
    X,
    Button,
    Frame,
    Label,
    PhotoImage,
    StringVar,
    filedialog,
    messagebox,
)

import unified_launcher as launcher


CANONICAL_SIDEBAR_ORDER = ("overview", "memory", "connection", "dojo", "settings")
_TEMPLATE_MODES = ("64", "32")
_MAX_DESKTOP_UPLOAD_BYTES = 5 * 1024 * 1024
_PREVIEW_BOX_WIDTH = 240
_PREVIEW_BOX_HEIGHT = 170
_PREVIEW_MAX_WIDTH = 210
_PREVIEW_MAX_HEIGHT = 145
_PREVIEW_MAX_ZOOM = 4


launcher.TEXT["pt-BR"].update(
    {
        "dojo_templates": "Imagens do Dojo Trainer",
        "dojo_templates_help": (
            "Envie um recorte do Trainer para cada modo do jogo usado neste computador. "
            "As imagens ficam salvas fora do executável e são preservadas nas atualizações."
        ),
        "dojo_template_mode": "Modo do jogo {mode}×{mode}",
        "dojo_template_upload": "Escolher imagem",
        "dojo_template_remove": "Remover",
        "dojo_template_configured": "Configurado · {width}×{height} px",
        "dojo_template_missing": "Não configurado",
        "dojo_template_ready": "Ao menos um template está pronto.",
        "dojo_template_required": "Adicione uma imagem 32×32 ou 64×64 antes de iniciar.",
        "dojo_template_upload_success": "Imagem do modo {mode}×{mode} salva com sucesso.",
        "dojo_template_upload_failed": "Não foi possível salvar a imagem:\n\n{error}",
        "dojo_template_remove_confirm": "Remover a imagem do modo {mode}×{mode}?",
        "dojo_template_remove_failed": "Não foi possível remover a imagem:\n\n{error}",
        "dojo_template_file_too_large": "A imagem deve ter no máximo 5 MB.",
        "dojo_template_preview_unavailable": "Prévia indisponível",
        "dojo_template_storage": "Armazenamento: {path}",
    }
)
launcher.TEXT["en-US"].update(
    {
        "dojo_templates": "Dojo Trainer images",
        "dojo_templates_help": (
            "Provide one Trainer crop for each game mode used on this computer. "
            "Images are stored outside the executable and survive updates."
        ),
        "dojo_template_mode": "Game mode {mode}×{mode}",
        "dojo_template_upload": "Choose image",
        "dojo_template_remove": "Remove",
        "dojo_template_configured": "Configured · {width}×{height} px",
        "dojo_template_missing": "Not configured",
        "dojo_template_ready": "At least one template is ready.",
        "dojo_template_required": "Add a 32×32 or 64×64 image before starting.",
        "dojo_template_upload_success": "The {mode}×{mode} image was saved.",
        "dojo_template_upload_failed": "The image could not be saved:\n\n{error}",
        "dojo_template_remove_confirm": "Remove the {mode}×{mode} image?",
        "dojo_template_remove_failed": "The image could not be removed:\n\n{error}",
        "dojo_template_file_too_large": "The image must be at most 5 MB.",
        "dojo_template_preview_unavailable": "Preview unavailable",
        "dojo_template_storage": "Storage: {path}",
    }
)


def _detail_from_error(error: BaseException) -> str:
    text = str(error)
    return text or type(error).__name__


def preview_scale_steps(width: int, height: int) -> tuple[int, int]:
    """Return integer ``(subsample, zoom)`` steps for a crisp Tk preview.

    Tk ``PhotoImage`` only offers integer nearest-neighbour scaling. Large images
    are reduced first, then small sprite crops are enlarged as much as possible
    inside the fixed preview box without changing their aspect ratio.
    """

    width = max(1, int(width))
    height = max(1, int(height))
    subsample = max(
        1,
        math.ceil(width / _PREVIEW_MAX_WIDTH),
        math.ceil(height / _PREVIEW_MAX_HEIGHT),
    )
    fitted_width = max(1, width // subsample)
    fitted_height = max(1, height // subsample)
    zoom = max(
        1,
        min(
            _PREVIEW_MAX_ZOOM,
            _PREVIEW_MAX_WIDTH // fitted_width,
            _PREVIEW_MAX_HEIGHT // fitted_height,
        ),
    )
    return subsample, zoom


def _fit_preview_image(image: PhotoImage) -> PhotoImage:
    subsample, zoom = preview_scale_steps(image.width(), image.height())
    if subsample > 1:
        image = image.subsample(subsample, subsample)
    if zoom > 1:
        image = image.zoom(zoom, zoom)
    return image


def install_dojo_templates_desktop(base_class):
    """Add user-owned 32/64 Trainer templates and keep Settings last."""

    class DojoTemplateEnabledUI(base_class):
        def __init__(self, root) -> None:
            self.dojo_templates_ready = False
            self.dojo_template_summary_var = StringVar(value="—")
            self.dojo_template_storage_var = StringVar(value="—")
            self.dojo_template_status_vars = {
                mode: StringVar(value="—") for mode in _TEMPLATE_MODES
            }
            self._dojo_template_preview_labels = {}
            self._dojo_template_images = {}
            self._dojo_template_hashes = {}
            self._dojo_template_buttons = []
            super().__init__(root)
            self.root.after(700, self._refresh_dojo_templates)

        def _build_ui(self) -> None:
            super()._build_ui()
            self._repack_sidebar_canonically()
            self._build_template_panel(self._pages["dojo"])

        def _repack_sidebar_canonically(self) -> None:
            """Canonical navigation rule: Settings is always the final item."""

            for button in self._page_buttons.values():
                button.pack_forget()
            extras = [
                key
                for key in self._page_buttons
                if key not in CANONICAL_SIDEBAR_ORDER
            ]
            order = [
                *CANONICAL_SIDEBAR_ORDER[:-1],
                *extras,
                CANONICAL_SIDEBAR_ORDER[-1],
            ]
            for index, key in enumerate(order):
                button = self._page_buttons.get(key)
                if button is None:
                    continue
                button.pack(
                    fill=X,
                    padx=8,
                    pady=(8 if index == 0 else 2, 0),
                )

        def _build_template_panel(self, page: Frame) -> None:
            children = page.winfo_children()
            before = children[-1] if children else None
            panel = self._card(page)
            pack_options = {"fill": X, "pady": (14, 0)}
            if before is not None:
                pack_options["before"] = before
            panel.pack(**pack_options)

            Label(
                panel,
                text=launcher._t(self.lang, "dojo_templates"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 11),
            ).pack(anchor="w")
            Label(
                panel,
                text=launcher._t(self.lang, "dojo_templates_help"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                wraplength=820,
                justify="left",
            ).pack(anchor="w", pady=(4, 10))

            row = Frame(panel, bg=launcher.COLORS["card"])
            row.pack(fill=X)
            for index, mode in enumerate(_TEMPLATE_MODES):
                self._build_template_card(row, mode).pack(
                    side=LEFT,
                    fill=BOTH,
                    expand=True,
                    padx=(0, 6) if index == 0 else (6, 0),
                )

            Label(
                panel,
                textvariable=self.dojo_template_summary_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["accent_soft"],
                font=("Segoe UI Semibold", 9),
            ).pack(anchor="w", pady=(10, 0))
            Label(
                panel,
                textvariable=self.dojo_template_storage_var,
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                wraplength=820,
                justify="left",
            ).pack(anchor="w", pady=(3, 0))

        def _build_template_card(self, parent: Frame, mode: str) -> Frame:
            card = Frame(
                parent,
                bg=launcher.COLORS["surface_alt"],
                highlightthickness=1,
                highlightbackground=launcher.COLORS["border_soft"],
                padx=14,
                pady=12,
            )
            Label(
                card,
                text=launcher._t(self.lang, "dojo_template_mode", mode=mode),
                bg=launcher.COLORS["surface_alt"],
                fg=launcher.COLORS["text"],
                font=("Segoe UI Semibold", 10),
            ).pack(anchor="w")

            preview_box = Frame(
                card,
                width=_PREVIEW_BOX_WIDTH,
                height=_PREVIEW_BOX_HEIGHT,
                bg=launcher.COLORS["card"],
                highlightthickness=1,
                highlightbackground=launcher.COLORS["border"],
            )
            preview_box.pack(pady=(10, 10))
            preview_box.pack_propagate(False)
            preview = Label(
                preview_box,
                text=launcher._t(self.lang, "dojo_template_preview_unavailable"),
                bg=launcher.COLORS["card"],
                fg=launcher.COLORS["muted"],
                anchor="center",
                justify="center",
            )
            preview.pack(fill=BOTH, expand=True, padx=8, pady=8)
            self._dojo_template_preview_labels[mode] = preview

            Label(
                card,
                textvariable=self.dojo_template_status_vars[mode],
                bg=launcher.COLORS["surface_alt"],
                fg=launcher.COLORS["accent"],
                font=("Segoe UI Semibold", 9),
            ).pack(anchor="w", pady=(0, 8))
            buttons = Frame(card, bg=launcher.COLORS["surface_alt"])
            buttons.pack(fill=X)
            upload = Button(
                buttons,
                text=launcher._t(self.lang, "dojo_template_upload"),
                command=lambda value=mode: self.choose_dojo_template(value),
                bg=launcher.COLORS["approve"],
                fg=launcher.COLORS["text"],
                relief="flat",
                padx=12,
                pady=8,
            )
            upload.pack(side=LEFT, padx=(0, 6))
            remove = Button(
                buttons,
                text=launcher._t(self.lang, "dojo_template_remove"),
                command=lambda value=mode: self.remove_dojo_template(value),
                bg=launcher.COLORS["button"],
                fg=launcher.COLORS["text"],
                relief="flat",
                padx=12,
                pady=8,
            )
            remove.pack(side=LEFT)
            self._dojo_template_buttons.extend((upload, remove))
            return card

        def _update_dojo_buttons(self) -> None:
            super()._update_dojo_buttons()
            if self._dojo_start_button is not None and not self.dojo_templates_ready:
                self._dojo_start_button.configure(state="disabled")
            template_state = (
                "disabled" if self._dojo_running or self._dojo_busy else "normal"
            )
            for button in self._dojo_template_buttons:
                button.configure(state=template_state)

        def _reset_template_preview(self, mode: str) -> None:
            self._dojo_template_hashes.pop(mode, None)
            self._dojo_template_images.pop(mode, None)
            label = self._dojo_template_preview_labels.get(mode)
            if label is not None:
                label.configure(
                    image="",
                    text=launcher._t(
                        self.lang,
                        "dojo_template_preview_unavailable",
                    ),
                )

        def _apply_template_status(self, payload: dict) -> None:
            templates = payload.get("templates")
            if not isinstance(templates, dict):
                templates = {}
            self.dojo_templates_ready = bool(payload.get("ready"))
            self.dojo_template_summary_var.set(
                launcher._t(
                    self.lang,
                    "dojo_template_ready"
                    if self.dojo_templates_ready
                    else "dojo_template_required",
                )
            )
            storage = str(payload.get("storage") or "—")
            self.dojo_template_storage_var.set(
                launcher._t(self.lang, "dojo_template_storage", path=storage)
            )
            for mode in _TEMPLATE_MODES:
                record = templates.get(mode)
                if not isinstance(record, dict):
                    record = {}
                if bool(record.get("configured")):
                    self.dojo_template_status_vars[mode].set(
                        launcher._t(
                            self.lang,
                            "dojo_template_configured",
                            width=int(record.get("width", 0) or 0),
                            height=int(record.get("height", 0) or 0),
                        )
                    )
                    digest = str(record.get("sha256") or "")
                    if digest and self._dojo_template_hashes.get(mode) != digest:
                        self._refresh_template_preview(mode, digest)
                else:
                    self.dojo_template_status_vars[mode].set(
                        launcher._t(self.lang, "dojo_template_missing")
                    )
                    self._reset_template_preview(mode)
            self._update_dojo_buttons()

        def _refresh_template_preview(self, mode: str, digest: str) -> None:
            try:
                payload = self._api_json(
                    "GET",
                    f"/api/dojo/templates/{mode}/image",
                    timeout=5,
                )
                image_base64 = str(payload.get("image_base64") or "")
                image = _fit_preview_image(PhotoImage(data=image_base64))
                self._dojo_template_images[mode] = image
                self._dojo_template_hashes[mode] = digest
                label = self._dojo_template_preview_labels.get(mode)
                if label is not None:
                    label.configure(image=image, text="")
            except Exception:
                self._reset_template_preview(mode)

        def _refresh_dojo_templates(self) -> None:
            if self.stopping:
                return
            try:
                if self._server_is_healthy():
                    payload = self._api_json("GET", "/api/dojo/templates", timeout=3)
                    self._apply_template_status(payload)
            except Exception:
                pass

        def choose_dojo_template(self, mode: str) -> None:
            selected = filedialog.askopenfilename(
                parent=self.root,
                title=launcher._t(self.lang, "dojo_template_mode", mode=mode),
                filetypes=(
                    ("Images", "*.png *.jpg *.jpeg *.webp *.bmp"),
                    ("PNG", "*.png"),
                    ("All files", "*.*"),
                ),
            )
            if not selected:
                return
            path = Path(selected)
            try:
                raw = path.read_bytes()
            except OSError as error:
                messagebox.showerror(
                    "KageLink Dojo",
                    launcher._t(
                        self.lang,
                        "dojo_template_upload_failed",
                        error=_detail_from_error(error),
                    ),
                    parent=self.root,
                )
                return
            if len(raw) > _MAX_DESKTOP_UPLOAD_BYTES:
                messagebox.showerror(
                    "KageLink Dojo",
                    launcher._t(self.lang, "dojo_template_file_too_large"),
                    parent=self.root,
                )
                return
            self._dojo_busy = True
            self._update_dojo_buttons()

            def worker() -> None:
                try:
                    payload = self._api_json(
                        "POST",
                        f"/api/dojo/templates/{mode}",
                        {
                            "filename": path.name,
                            "image_base64": base64.b64encode(raw).decode("ascii"),
                        },
                        timeout=20,
                    )
                    self.ui(lambda value=payload: self._apply_template_status(value))
                    self.ui(
                        lambda: self.message_var.set(
                            launcher._t(
                                self.lang,
                                "dojo_template_upload_success",
                                mode=mode,
                            )
                        )
                    )
                except Exception as error:
                    self.ui(
                        lambda value=error: messagebox.showerror(
                            "KageLink Dojo",
                            launcher._t(
                                self.lang,
                                "dojo_template_upload_failed",
                                error=_detail_from_error(value),
                            ),
                            parent=self.root,
                        )
                    )
                finally:
                    self._dojo_busy = False
                    self.ui(self._update_dojo_buttons)

            threading.Thread(
                target=worker,
                name=f"DojoTemplateUpload{mode}",
                daemon=True,
            ).start()

        def remove_dojo_template(self, mode: str) -> None:
            if not messagebox.askyesno(
                "KageLink Dojo",
                launcher._t(self.lang, "dojo_template_remove_confirm", mode=mode),
                parent=self.root,
            ):
                return
            self._dojo_busy = True
            self._update_dojo_buttons()

            def worker() -> None:
                try:
                    payload = self._api_json(
                        "DELETE",
                        f"/api/dojo/templates/{mode}",
                        timeout=10,
                    )
                    self.ui(lambda value=payload: self._apply_template_status(value))
                except Exception as error:
                    self.ui(
                        lambda value=error: messagebox.showerror(
                            "KageLink Dojo",
                            launcher._t(
                                self.lang,
                                "dojo_template_remove_failed",
                                error=_detail_from_error(value),
                            ),
                            parent=self.root,
                        )
                    )
                finally:
                    self._dojo_busy = False
                    self.ui(self._update_dojo_buttons)

            threading.Thread(
                target=worker,
                name=f"DojoTemplateDelete{mode}",
                daemon=True,
            ).start()

        def _refresh_dojo_status(self) -> None:
            super()._refresh_dojo_status()
            self._refresh_dojo_templates()

    return DojoTemplateEnabledUI


__all__ = [
    "CANONICAL_SIDEBAR_ORDER",
    "install_dojo_templates_desktop",
    "preview_scale_steps",
]
