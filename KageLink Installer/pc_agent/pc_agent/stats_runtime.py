from __future__ import annotations

import logging
import threading
import time
from typing import Any

from pc_agent.game_protocol import GAME_WINDOW_TITLE


class StatsRuntime:
    """Isolated capture and input facade for Status | Inventory."""

    def __init__(self, game_title: str = GAME_WINDOW_TITLE) -> None:
        self.game_title = game_title
        self._capture = None
        self._control = None
        self._capture_init_error: str | None = None
        self._control_init_error: str | None = None
        self._last_error: str | None = None
        self._last_frame_at: float | None = None
        self._last_frame_size = 0
        self._last_frame_hwnd: int | None = None
        self._lock = threading.RLock()
        self._logger = logging.getLogger("kagelink.stats")

    def _ensure_capture(self):
        with self._lock:
            if self._capture is not None:
                return self._capture
            if self._capture_init_error:
                raise RuntimeError(self._capture_init_error)
            try:
                from pc_agent.stats_capture import StatsCapture

                self._capture = StatsCapture(self.game_title)
                return self._capture
            except Exception as error:
                self._capture_init_error = f"STATS_CAPTURE_UNAVAILABLE: {error}"
                self._logger.exception("Unable to initialize Stats capture")
                raise RuntimeError(self._capture_init_error) from error

    def _ensure_control(self):
        with self._lock:
            if self._control is not None:
                return self._control
            if self._control_init_error:
                raise RuntimeError(self._control_init_error)
            try:
                from pc_agent.stats_control import StatsInputController

                self._control = StatsInputController(self.game_title)
                return self._control
            except Exception as error:
                self._control_init_error = f"STATS_CONTROL_UNAVAILABLE: {error}"
                self._logger.exception("Unable to initialize Stats control")
                raise RuntimeError(self._control_init_error) from error

    def status(self) -> dict[str, Any]:
        try:
            from pc_agent.stats_window import locate_stats_target

            target = locate_stats_target(self.game_title)
            return {
                "available": self._capture_init_error is None,
                "capture_available": self._capture_init_error is None,
                "control_available": self._control_init_error is None,
                "window_open": target is not None,
                "minimized": bool(target and target.minimized),
                "hwnd": target.hwnd if target else None,
                "source_width": target.width if target else None,
                "source_height": target.height if target else None,
                "target_fps": 5,
                "last_frame_at": self._last_frame_at,
                "last_frame_size": self._last_frame_size,
                "control_active": bool(self._control and self._control.active),
                "last_error": (
                    self._last_error
                    or self._capture_init_error
                    or self._control_init_error
                ),
            }
        except Exception as error:
            self._last_error = str(error)
            return {
                "available": False,
                "window_open": False,
                "minimized": False,
                "target_fps": 5,
                "last_error": self._last_error,
            }

    def capture_frame(self) -> tuple[bytes, dict[str, Any]]:
        try:
            frame = self._ensure_capture().capture()
            previous_hwnd = self._last_frame_hwnd
            self._last_error = None
            self._last_frame_at = time.time()
            self._last_frame_size = len(frame.jpeg)
            self._last_frame_hwnd = frame.target.hwnd
            if previous_hwnd != frame.target.hwnd:
                self._logger.info(
                    "Stats window detected: hwnd=%s size=%sx%s",
                    frame.target.hwnd,
                    frame.target.width,
                    frame.target.height,
                )
            metadata = {
                "type": "stats_stream_status",
                "state": "live",
                "source_width": frame.source_width,
                "source_height": frame.source_height,
                "output_width": frame.output_width,
                "output_height": frame.output_height,
                "window_hwnd": frame.target.hwnd,
                "timestamp": self._last_frame_at,
            }
            return frame.jpeg, metadata
        except Exception as error:
            self._last_error = str(error)
            if self._last_frame_hwnd is not None:
                self._logger.info(
                    "Stats window lost: previous_hwnd=%s reason=%s",
                    self._last_frame_hwnd,
                    error,
                )
            self._last_frame_hwnd = None
            raise

    def activate_control(self) -> None:
        self._ensure_control().activate()
        self._last_error = None

    def deactivate_control(self) -> None:
        if self._control is not None:
            self._control.deactivate()

    def open_stats(self) -> dict[str, Any]:
        try:
            hwnd, opened = self._ensure_control().open_stats()
            self._last_error = None
            self._logger.info(
                "Stats open request completed: hwnd=%s opened=%s",
                hwnd,
                opened,
            )
            return {"hwnd": hwnd, "opened": opened}
        except Exception as error:
            self._last_error = str(error)
            self._logger.warning("Stats open request rejected: %s", error)
            raise

    def click(self, x: float, y: float, button: str, window_id: int) -> int:
        try:
            if not self._last_frame_hwnd or window_id != self._last_frame_hwnd:
                raise RuntimeError("STATS_FRAME_WINDOW_MISMATCH")
            hwnd = self._ensure_control().click(
                x,
                y,
                button,
                expected_hwnd=window_id,
            )
            self._last_error = None
            return hwnd
        except Exception as error:
            self._last_error = str(error)
            self._logger.warning(
                "Stats click rejected: window_id=%s button=%s reason=%s",
                window_id,
                button,
                error,
            )
            raise

    def close(self) -> None:
        self.deactivate_control()
        if self._capture is not None:
            self._capture.close()
