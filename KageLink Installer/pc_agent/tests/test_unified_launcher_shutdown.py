from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import unified_launcher


class _MessageVar:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class UnifiedLauncherShutdownTests(unittest.TestCase):
    def _ui(self):
        ui = unified_launcher.UnifiedKageLinkAgentUI.__new__(
            unified_launcher.UnifiedKageLinkAgentUI
        )
        ui._finalization_done = False
        ui.config = SimpleNamespace(leafos_enabled=True)
        ui.lang = "pt-BR"
        ui.message_var = _MessageVar()
        ui.root = MagicMock()
        ui.logger = MagicMock()
        ui.stopping = False
        return ui

    def test_shutdown_finalizer_calls_leafos_before_infrastructure_teardown(self) -> None:
        ui = self._ui()
        ui._server_is_healthy = MagicMock(return_value=True)
        ui._api_json = MagicMock(return_value={"closed": True})

        result = ui._finalize_for_shutdown()

        self.assertTrue(result)
        self.assertTrue(ui._finalization_done)
        ui._api_json.assert_called_once_with(
            "POST",
            "/api/leafos/finalize-session",
            {"reason": "agent_shutdown", "restart_monitor": False},
            timeout=30,
        )
        ui.root.update_idletasks.assert_called_once()

    @patch.object(unified_launcher.messagebox, "askyesno", return_value=True)
    def test_request_close_finalizes_before_legacy_shutdown(self, _askyesno) -> None:
        ui = self._ui()
        order: list[str] = []
        ui._finalize_for_shutdown = MagicMock(
            side_effect=lambda: order.append("leafos-finalized") or True
        )
        ui.root.destroy = MagicMock(side_effect=lambda: order.append("window-destroyed"))

        with patch.object(
            unified_launcher.legacy.KageLinkAgentUI,
            "shutdown",
            side_effect=lambda _self, prompt=False: order.append("infrastructure-stopped"),
        ):
            ui.request_close()

        self.assertEqual(
            order,
            ["leafos-finalized", "infrastructure-stopped", "window-destroyed"],
        )

    @patch.object(unified_launcher.subprocess, "Popen")
    def test_frozen_restart_resets_pyinstaller_environment(self, popen) -> None:
        ui = self._ui()
        ui._finalize_for_shutdown = MagicMock(return_value=True)

        with patch.object(unified_launcher.sys, "frozen", True, create=True), patch.object(
            unified_launcher.legacy.KageLinkAgentUI,
            "shutdown",
        ):
            ui._restart_application()

        popen.assert_called_once()
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [unified_launcher.sys.executable])
        self.assertEqual(kwargs["cwd"], unified_launcher.PROJECT_DIR)
        self.assertEqual(kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        ui.root.destroy.assert_called_once()

    def test_shutdown_failure_does_not_claim_finalization(self) -> None:
        ui = self._ui()
        ui._server_is_healthy = MagicMock(return_value=True)
        ui._api_json = MagicMock(side_effect=RuntimeError("backend failure"))

        result = ui._finalize_for_shutdown()

        self.assertFalse(result)
        self.assertFalse(ui._finalization_done)
        ui.logger.exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
