from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import unified_entry


class _MessageVar:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class UnifiedInterpreterFlowTests(unittest.TestCase):
    def _ui(self):
        ui = unified_entry.UnifiedKageLinkAgentUI.__new__(
            unified_entry.UnifiedKageLinkAgentUI
        )
        ui.lang = "pt-BR"
        ui.root = MagicMock()
        ui.message_var = _MessageVar()
        ui._leafos_busy = True
        ui.ui = lambda callback: callback()
        ui._refresh_leafos_status = MagicMock()
        ui.open_reviewer = MagicMock()
        return ui

    def test_finalize_targets_only_the_session_just_closed(self) -> None:
        ui = self._ui()
        ui._api_json = MagicMock(
            return_value={"closed": True, "session_id": "2026-07-26_004"}
        )
        ui._interpret_pending_worker = MagicMock()

        ui._finalize_review_worker()

        ui._interpret_pending_worker.assert_called_once_with(
            open_reviewer=True,
            session_ids=["2026-07-26_004"],
        )
        self.assertFalse(ui._leafos_busy)

    @patch.object(unified_entry, "resolve_primary_character", return_value="Uchiha, Leafos")
    @patch.object(unified_entry, "HistoryStore")
    @patch.object(unified_entry, "OllamaInterpreterProvider")
    @patch.object(unified_entry, "OllamaManager")
    @patch.object(unified_entry, "LeafOSInterpreter")
    @patch.object(unified_entry, "load_config")
    @patch.object(unified_entry.messagebox, "showerror")
    def test_failed_target_is_reported_and_reviewer_stays_closed(
        self,
        showerror,
        load_config,
        interpreter_type,
        ollama_manager_type,
        _provider_type,
        _history_type,
        _resolve,
    ) -> None:
        ui = self._ui()
        load_config.return_value = SimpleNamespace(
            leafos_enabled=True,
            leafos_vault_path="C:/LeafOS-Vault",
            database_path="C:/chat.db",
        )
        ollama_manager_type.return_value.status.return_value = SimpleNamespace(
            server_online=True,
            cli_path="ollama.exe",
            model_available=True,
        )
        interpreter_type.return_value.run_once.return_value = {
            "interpreted": 0,
            "skipped": 0,
            "failed": 1,
            "failures": [
                {
                    "session_id": "2026-07-26_004",
                    "error": "OLLAMA_TIMEOUT: 600s",
                }
            ],
        }

        ui._interpret_pending_worker(
            open_reviewer=True,
            session_ids=["2026-07-26_004"],
        )

        interpreter_type.return_value.run_once.assert_called_once_with(
            session_ids=["2026-07-26_004"],
            include_details=True,
        )
        ui.open_reviewer.assert_not_called()
        showerror.assert_called_once()
        self.assertIn("2026-07-26_004", ui.message_var.values[-1])
        self.assertIn("OLLAMA_TIMEOUT", ui.message_var.values[-1])

    @patch.object(unified_entry, "resolve_primary_character", return_value="Uchiha, Leafos")
    @patch.object(unified_entry, "HistoryStore")
    @patch.object(unified_entry, "OllamaInterpreterProvider")
    @patch.object(unified_entry, "OllamaManager")
    @patch.object(unified_entry, "LeafOSInterpreter")
    @patch.object(unified_entry, "load_config")
    def test_successful_target_opens_reviewer(
        self,
        load_config,
        interpreter_type,
        ollama_manager_type,
        _provider_type,
        _history_type,
        _resolve,
    ) -> None:
        ui = self._ui()
        load_config.return_value = SimpleNamespace(
            leafos_enabled=True,
            leafos_vault_path="C:/LeafOS-Vault",
            database_path="C:/chat.db",
        )
        ollama_manager_type.return_value.status.return_value = SimpleNamespace(
            server_online=True,
            cli_path="ollama.exe",
            model_available=True,
        )
        interpreter_type.return_value.run_once.return_value = {
            "interpreted": 1,
            "skipped": 0,
            "failed": 0,
            "failures": [],
        }

        ui._interpret_pending_worker(
            open_reviewer=True,
            session_ids=["2026-07-26_004"],
        )

        ui.open_reviewer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
