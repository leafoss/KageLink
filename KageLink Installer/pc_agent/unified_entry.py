from __future__ import annotations

import sys
import threading
from pathlib import Path
from tkinter import messagebox
from typing import Any, Iterable

import unified_launcher as launcher
from pc_agent.config import load_config
from pc_agent.history import HistoryStore
from pc_agent.leafos_interpreter_v321 import LeafOSInterpreter, OllamaInterpreterProvider
from pc_agent.leafos_ollama import OllamaManager
from pc_agent.primary_character import resolve_primary_character
from unified_dojo_debug_v351 import install_dojo_debug_desktop
from unified_dojo_responsive_v351 import install_dojo_responsive_order
from unified_dojo_stop_v351 import install_dojo_stop_desktop
from unified_dojo_templates_ui_v35 import install_dojo_templates_desktop
from unified_dojo_ui import install_dojo_desktop
from unified_dojo_ui_v351 import install_dojo_reliability_desktop


# unified_launcher remains source-compatible, but every Interpreter path reached
# through the packaged unified entry uses the v3.2.1 durable-revelation layer.
launcher.LeafOSInterpreter = LeafOSInterpreter
launcher.OllamaInterpreterProvider = OllamaInterpreterProvider


class UnifiedKageLinkAgentUI(launcher.UnifiedKageLinkAgentUI):
    """Production entry UI with session-targeted Interpreter diagnostics."""

    def _finalize_review_worker(self) -> None:
        try:
            finalized = self._api_json(
                "POST",
                "/api/leafos/finalize-session",
                {"reason": "manual", "restart_monitor": True},
                timeout=30,
            )
            self.ui(lambda: self.message_var.set(launcher._t(self.lang, "finalized")))

            session_id = str(finalized.get("session_id") or "").strip()
            session_ids = [session_id] if finalized.get("closed") and session_id else None
            self._interpret_pending_worker(
                open_reviewer=True,
                session_ids=session_ids,
            )
        except Exception as error:
            self.ui(
                lambda value=error: messagebox.showerror(
                    "LeafOS",
                    launcher._t(self.lang, "operation_failed", error=value),
                    parent=self.root,
                )
            )
        finally:
            self._clear_busy()

    def _interpreter_progress(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        event = str(payload.get("event") or "")
        if event not in {"session_start", "chunk_start", "chunk_reused", "chunk_complete"}:
            return

        session_id = str(payload.get("session_id") or "?")
        try:
            chunk_number = max(0, int(payload.get("chunk_number", 0) or 0))
        except (TypeError, ValueError):
            chunk_number = 0
        try:
            total_chunks = max(1, int(payload.get("total_chunks", 1) or 1))
        except (TypeError, ValueError):
            total_chunks = 1

        if event == "session_start":
            try:
                completed = max(0, int(payload.get("completed_chunks", 0) or 0))
            except (TypeError, ValueError):
                completed = 0
            progress = f"{completed}/{total_chunks}"
        else:
            progress = f"{chunk_number}/{total_chunks}"

        marker = " ✓" if event in {"chunk_reused", "chunk_complete"} else ""
        text = f"{launcher._t(self.lang, 'working')} · {session_id} · {progress}{marker}"
        self.ui(lambda value=text: self.message_var.set(value))

    def _failure_message(self, failures: Iterable[dict[str, Any]]) -> str:
        lines: list[str] = []
        for item in failures:
            if not isinstance(item, dict):
                continue
            session_id = str(item.get("session_id") or "?")
            error = str(item.get("error") or "UNKNOWN_INTERPRETER_ERROR")
            try:
                chunk_number = int(item.get("chunk_number", 0) or 0)
                total_chunks = int(item.get("total_chunks", 0) or 0)
                completed_chunks = int(item.get("completed_chunks", 0) or 0)
            except (TypeError, ValueError):
                chunk_number = total_chunks = completed_chunks = 0
            chunk_detail = ""
            if chunk_number > 0 and total_chunks > 0:
                chunk_detail = f" [{chunk_number}/{total_chunks}; {completed_chunks} ✓]"
            lines.append(f"{session_id}{chunk_detail}: {error}")
        details = "\n".join(lines[:8]) or "UNKNOWN_INTERPRETER_ERROR"
        if len(lines) > 8:
            details += f"\n... +{len(lines) - 8}"

        return (
            f"{launcher._t(self.lang, 'interpreter_failed')}\n\n"
            f"{details}\n\n"
            f"{launcher._t(self.lang, 'interpreter_preserved')}"
        )

    def _interpret_pending_worker(
        self,
        *,
        open_reviewer: bool,
        session_ids: Iterable[str] | None = None,
    ) -> None:
        config = load_config()
        if not config.leafos_enabled or config.leafos_vault_path is None:
            self.ui(lambda: self.message_var.set(launcher._t(self.lang, "leafos_disabled")))
            return

        manager = OllamaManager(base_url=launcher.OLLAMA_URL, model=launcher.MODEL)
        status = manager.status()
        if not status.server_online and status.cli_path:
            status = manager.start_server()
        if not status.server_online or not status.model_available:
            self.ui(lambda: self.message_var.set(launcher._t(self.lang, "ollama_required")))
            return

        history = HistoryStore(config.database_path)
        provider = OllamaInterpreterProvider(
            base_url=launcher.OLLAMA_URL,
            model=launcher.MODEL,
        )
        interpreter = LeafOSInterpreter(
            Path(config.leafos_vault_path),
            provider,
            primary_character_resolver=lambda session: resolve_primary_character(
                history,
                session.get("started_at"),
            ),
            progress_callback=self._interpreter_progress,
        )
        result = interpreter.run_once(
            session_ids=session_ids,
            include_details=True,
        )

        interpreted = int(result.get("interpreted", 0) or 0)
        failed = int(result.get("failed", 0) or 0)
        failures = result.get("failures", [])
        if not isinstance(failures, list):
            failures = []

        status_text = launcher._t(
            self.lang,
            "interpret_done",
            interpreted=interpreted,
            failed=failed,
        )
        if failures:
            first = failures[0] if isinstance(failures[0], dict) else {}
            first_session = str(first.get("session_id") or "?")
            first_error = str(first.get("error") or "UNKNOWN_INTERPRETER_ERROR")
            status_text += f" · {first_session}: {first_error}"[:500]
        self.ui(lambda text=status_text: self.message_var.set(text))
        self.ui(self._refresh_leafos_status)

        if failures:
            failure_message = self._failure_message(failures)
            self.ui(
                lambda text=failure_message: messagebox.showerror(
                    "LeafOS Interpreter",
                    text,
                    parent=self.root,
                )
            )
            return

        if open_reviewer:
            self.ui(self.open_reviewer)


# The established Dojo and template layers remain intact. The reliability layer
# replaces only the Dojo page; the debug layer adds protected meditation controls
# and snapshots; the outer wrappers preserve 64×64 then 32×32 during reflow and
# keep Stop available while a Start request is still in flight.
launcher.UnifiedKageLinkAgentUI = install_dojo_stop_desktop(
    install_dojo_responsive_order(
        install_dojo_debug_desktop(
            install_dojo_reliability_desktop(
                install_dojo_templates_desktop(
                    install_dojo_desktop(UnifiedKageLinkAgentUI)
                )
            )
        )
    )
)


def main() -> int:
    import unified_app  # noqa: F401
    import unified_app_v35

    sys.modules["unified_app"] = unified_app_v35
    return launcher.main()


if __name__ == "__main__":
    raise SystemExit(main())
