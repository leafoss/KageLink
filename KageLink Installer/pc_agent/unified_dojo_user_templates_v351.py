from __future__ import annotations

import base64
import json
from pathlib import Path
import threading
from tkinter import LEFT, Button, filedialog, messagebox
import urllib.error

import unified_dojo_templates_ui_v35 as templates_ui
import unified_launcher as launcher


launcher.TEXT["pt-BR"].update(
    {
        "dojo_template_restore": "Restaurar imagem padrão",
        "dojo_template_restore_confirm": "Restaurar a imagem padrão do modo {mode}×{mode}?",
        "dojo_template_restore_success": "Imagem padrão do modo {mode}×{mode} restaurada.",
        "dojo_template_restore_failed": "Não foi possível restaurar a imagem padrão:\n\n{error}",
        "dojo_template_source_user": "Usuário",
        "dojo_template_source_default": "Padrão",
        "dojo_template_source_none": "Nenhuma",
        "dojo_template_used_by_detector": "Usada pelo detector",
        "dojo_template_detail": (
            "{width}×{height} px · origem: {source}\n"
            "{filename} · SHA-256 {sha}…\n{detector}"
        ),
        "dojo_template_invalid_png": "A imagem selecionada não é um PNG válido.",
        "dojo_template_training_active": "O treinamento está em execução. Pare o treino antes de alterar as imagens.",
        "dojo_template_api_error": "A operação não pôde ser concluída ({detail}).",
    }
)
launcher.TEXT["en-US"].update(
    {
        "dojo_template_restore": "Restore default image",
        "dojo_template_restore_confirm": "Restore the default {mode}×{mode} image?",
        "dojo_template_restore_success": "The default {mode}×{mode} image was restored.",
        "dojo_template_restore_failed": "The default image could not be restored:\n\n{error}",
        "dojo_template_source_user": "User",
        "dojo_template_source_default": "Default",
        "dojo_template_source_none": "None",
        "dojo_template_used_by_detector": "Used by the detector",
        "dojo_template_detail": (
            "{width}×{height} px · source: {source}\n"
            "{filename} · SHA-256 {sha}…\n{detector}"
        ),
        "dojo_template_invalid_png": "The selected image is not a valid PNG file.",
        "dojo_template_training_active": "Training is running. Stop training before changing images.",
        "dojo_template_api_error": "The operation could not be completed ({detail}).",
    }
)


def _detail_code(error: BaseException) -> str:
    if isinstance(error, urllib.error.HTTPError):
        try:
            payload = json.loads(error.read().decode("utf-8", errors="replace"))
            if isinstance(payload, dict):
                return str(payload.get("detail") or error.reason or error.code)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return str(error.reason or error.code)
    return str(error) or type(error).__name__


def install_dojo_user_owned_desktop(base_class):
    """Make Images-tab replacement/removal/restoration explicit and localized."""

    class UserOwnedDojoTemplateUI(base_class):
        def _template_error_text(self, error: BaseException) -> str:
            detail = _detail_code(error)
            if detail == "DOJO_TRAINING_ACTIVE":
                return launcher._t(self.lang, "dojo_template_training_active")
            if detail in {
                "DOJO_TEMPLATE_BASE64_INVALID",
                "DOJO_RAW_TEMPLATE_NOT_PNG",
                "DOJO_RAW_TEMPLATE_DECODE_FAILED",
                "DOJO_RAW_TEMPLATE_FORMAT_INVALID",
            }:
                return launcher._t(self.lang, "dojo_template_invalid_png")
            return launcher._t(self.lang, "dojo_template_api_error", detail=detail)

        def _build_template_card(self, parent, mode):
            card = super()._build_template_card(parent, mode)
            children = card.winfo_children()
            buttons = children[-1] if children else card
            restore = Button(
                buttons,
                text=launcher._t(self.lang, "dojo_template_restore"),
                command=lambda value=mode: self.restore_default_dojo_template(value),
                bg=launcher.COLORS["button"],
                fg=launcher.COLORS["text"],
                relief="flat",
                padx=12,
                pady=8,
            )
            restore.pack(side=LEFT, padx=(6, 0))
            self._dojo_template_buttons.append(restore)
            return card

        def _apply_template_status(self, payload: dict) -> None:
            super()._apply_template_status(payload)
            templates = payload.get("templates")
            if not isinstance(templates, dict):
                return
            for mode in templates_ui._TEMPLATE_MODES:
                record = templates.get(mode)
                if not isinstance(record, dict) or not bool(record.get("configured")):
                    continue
                source_value = str(record.get("source") or "none").lower()
                source_key = {
                    "user": "dojo_template_source_user",
                    "default": "dojo_template_source_default",
                }.get(source_value, "dojo_template_source_none")
                digest = str(record.get("sha256") or "")
                filename = str(record.get("original_filename") or Path(str(record.get("path") or "")).name or "—")
                self.dojo_template_status_vars[mode].set(
                    launcher._t(
                        self.lang,
                        "dojo_template_detail",
                        width=int(record.get("width", 0) or 0),
                        height=int(record.get("height", 0) or 0),
                        source=launcher._t(self.lang, source_key),
                        filename=filename,
                        sha=(digest[:16] if digest else "—"),
                        detector=launcher._t(self.lang, "dojo_template_used_by_detector"),
                    )
                )

        def choose_dojo_template(self, mode: str) -> None:
            selected = filedialog.askopenfilename(
                parent=self.root,
                title=launcher._t(self.lang, "dojo_template_mode", mode=mode),
                filetypes=(("PNG", "*.png"), ("All files", "*.*")),
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
                        error=str(error),
                    ),
                    parent=self.root,
                )
                return
            if len(raw) > templates_ui._MAX_DESKTOP_UPLOAD_BYTES:
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
                            launcher._t(self.lang, "dojo_template_upload_success", mode=mode)
                        )
                    )
                except Exception as error:
                    text = self._template_error_text(error)
                    self.ui(
                        lambda value=text: messagebox.showerror(
                            "KageLink Dojo",
                            launcher._t(
                                self.lang,
                                "dojo_template_upload_failed",
                                error=value,
                            ),
                            parent=self.root,
                        )
                    )
                finally:
                    self._dojo_busy = False
                    self.ui(self._update_dojo_buttons)

            threading.Thread(
                target=worker,
                name=f"DojoUserTemplateUpload{mode}",
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
                    text = self._template_error_text(error)
                    self.ui(
                        lambda value=text: messagebox.showerror(
                            "KageLink Dojo",
                            launcher._t(
                                self.lang,
                                "dojo_template_remove_failed",
                                error=value,
                            ),
                            parent=self.root,
                        )
                    )
                finally:
                    self._dojo_busy = False
                    self.ui(self._update_dojo_buttons)

            threading.Thread(
                target=worker,
                name=f"DojoUserTemplateDelete{mode}",
                daemon=True,
            ).start()

        def restore_default_dojo_template(self, mode: str) -> None:
            if not messagebox.askyesno(
                "KageLink Dojo",
                launcher._t(self.lang, "dojo_template_restore_confirm", mode=mode),
                parent=self.root,
            ):
                return
            self._dojo_busy = True
            self._update_dojo_buttons()

            def worker() -> None:
                try:
                    payload = self._api_json(
                        "POST",
                        f"/api/dojo/templates/{mode}/restore-default",
                        timeout=10,
                    )
                    self.ui(lambda value=payload: self._apply_template_status(value))
                    self.ui(
                        lambda: self.message_var.set(
                            launcher._t(self.lang, "dojo_template_restore_success", mode=mode)
                        )
                    )
                except Exception as error:
                    text = self._template_error_text(error)
                    self.ui(
                        lambda value=text: messagebox.showerror(
                            "KageLink Dojo",
                            launcher._t(
                                self.lang,
                                "dojo_template_restore_failed",
                                error=value,
                            ),
                            parent=self.root,
                        )
                    )
                finally:
                    self._dojo_busy = False
                    self.ui(self._update_dojo_buttons)

            threading.Thread(
                target=worker,
                name=f"DojoDefaultTemplateRestore{mode}",
                daemon=True,
            ).start()

    return UserOwnedDojoTemplateUI


__all__ = ["install_dojo_user_owned_desktop"]
