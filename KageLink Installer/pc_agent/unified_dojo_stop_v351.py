from __future__ import annotations

import threading
from tkinter import messagebox

import unified_launcher as launcher


def install_dojo_stop_desktop(base_class):
    """Keep Stop independent from the in-flight Start request."""

    class StartupSafeStopDojoDesktopUI(base_class):
        def __init__(self, root) -> None:
            self._dojo_stop_busy = False
            super().__init__(root)

        def _update_dojo_buttons(self) -> None:
            super()._update_dojo_buttons()
            start_button = getattr(self, "_dojo_start_button", None)
            stop_button = getattr(self, "_dojo_stop_button", None)
            if start_button is None or stop_button is None:
                return

            # Start keeps its existing single-flight protection. Stop is deliberately
            # available while Start is waiting for the backend, because that is exactly
            # when template initialization or process creation can fail.
            start_state = "disabled" if self._dojo_running or self._dojo_busy else "normal"
            cancellation_possible = bool(self._dojo_running or self._dojo_busy)
            stop_state = "normal" if cancellation_possible and not self._dojo_stop_busy else "disabled"
            start_button.configure(state=start_state)
            stop_button.configure(state=stop_state)

        def stop_dojo(self) -> None:
            if self._dojo_stop_busy:
                return
            self._dojo_stop_busy = True
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
                    self._dojo_stop_busy = False
                    self.ui(self._update_dojo_buttons)

            threading.Thread(target=worker, name="DojoStopStartupSafe", daemon=True).start()

    return StartupSafeStopDojoDesktopUI


__all__ = ["install_dojo_stop_desktop"]
