from __future__ import annotations

import threading
from pathlib import Path
from tkinter import messagebox
from typing import Any, Iterable

import unified_launcher as launcher
from pc_agent.config import load_config
from pc_agent.history import HistoryStore
from pc_agent.leafos_interpreter import LeafOSInterpreter, OllamaInterpreterProvider
from pc_agent.leafos_ollama import OllamaManager
from pc_agent.primary_character import resolve_primary_character


class UnifiedKageLinkAgentUI(launcher.UnifiedKageLinkAgentUI):
    """Production entry UI with session-targeted Interpreter diagnostics.

    The base unified launcher remains source-compatible while the packaged EXE uses
    this class to make Finalize + Review deterministic: the freshly closed session
    is interpreted by itself, historical failures remain retryable, and a failed
    interpretation never opens an empty Reviewer as though it had succeeded.
    """

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
                lambda value=str(error): messagebox.showerror(
                    "LeafOS",
                    value,
                    parent=self.root,
                )
            )
        finally:
            self._clear_busy()

    def _failure_message(self, failures: Iterable[dict[str, Any]]) -> str:
        lines: list[str] = []
        for item in failures:
            if not isinstance(item, dict):
                continue
            session_id = str(item.get("session_id") or "?")
            error = str(item.get("error") or "UNKNOWN_INTERPRETER_ERROR")
            lines.append(f"{session_id}: {error}")
        details = "\n".join(lines[:8]) or "UNKNOWN_INTERPRETER_ERROR"
        if len(lines) > 8:
            details += f"\n... +{len(lines) - 8}"

        if self.lang == "pt-BR":
            return (
                "O Interpreter não conseguiu concluir uma ou mais sessões:\n\n"
                f"{details}\n\n"
                "A sessão, o Processor e o RAW foram preservados. "
                "Use 'Interpretar pendentes' para tentar novamente."
            )
        return (
            "The Interpreter could not complete one or more sessions:\n\n"
            f"{details}\n\n"
            "The session, Processor data and RAW were preserved. "
            "Use 'Interpret pending' to retry."
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


# unified_launcher.main() resolves this global when it creates the Desktop window.
launcher.UnifiedKageLinkAgentUI = UnifiedKageLinkAgentUI


def main() -> int:
    return launcher.main()


if __name__ == "__main__":
    raise SystemExit(main())
