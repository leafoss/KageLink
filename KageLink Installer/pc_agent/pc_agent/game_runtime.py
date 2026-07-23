from __future__ import annotations

import logging
import threading
import time
from typing import Any, Iterable

from pc_agent.game_protocol import GAME_WINDOW_TITLE, normalize_view_mode


class GameRuntime:
    """Isolated facade for capture and input.

    Game-only dependencies are imported lazily. If they fail, the original
    chat service remains available and the Game endpoints report the error.
    """

    def __init__(self, title: str = GAME_WINDOW_TITLE) -> None:
        self.title = title
        self._capture = None
        self._control = None
        self._capture_init_error: str | None = None
        self._control_init_error: str | None = None
        self._last_error: str | None = None
        self._last_frame_at: float | None = None
        self._last_frame_size = 0
        self._lock = threading.RLock()
        self._logger = logging.getLogger("kagelink.game")

    def _ensure_capture(self):
        with self._lock:
            if self._capture is not None:
                return self._capture
            if self._capture_init_error:
                raise RuntimeError(self._capture_init_error)
            try:
                from pc_agent.game_capture import GameCapture

                self._capture = GameCapture(self.title)
                return self._capture
            except Exception as error:
                self._capture_init_error = f"GAME_CAPTURE_UNAVAILABLE: {error}"
                self._logger.exception("Unable to initialize game capture")
                raise RuntimeError(self._capture_init_error) from error

    def _ensure_control(self):
        with self._lock:
            if self._control is not None:
                return self._control
            if self._control_init_error:
                raise RuntimeError(self._control_init_error)
            try:
                from pc_agent.game_control import GameInputController

                self._control = GameInputController(self.title)
                return self._control
            except Exception as error:
                self._control_init_error = f"GAME_CONTROL_UNAVAILABLE: {error}"
                self._logger.exception("Unable to initialize game control")
                raise RuntimeError(self._control_init_error) from error

    def status(self) -> dict[str, Any]:
        try:
            from pc_agent.game_window import locate_capture_target, show_state

            target = locate_capture_target(self.title)
            online = target is not None
            minimized = bool(target and target.minimized)
            return {
                "available": self._capture_init_error is None,
                "capture_available": self._capture_init_error is None,
                "control_available": self._control_init_error is None,
                "game_online": online,
                "minimized": minimized,
                "window_state": show_state(target.game_hwnd) if target else "missing",
                "capture_source": target.source_kind if target else None,
                "source_width": target.width if target else None,
                "source_height": target.height if target else None,
                "output_width": 960,
                "output_height": 540,
                "target_fps": 10,
                "last_frame_at": self._last_frame_at,
                "last_frame_size": self._last_frame_size,
                "control_active": bool(self._control and self._control.active),
                "pressed": sorted(self._control.pressed) if self._control else [],
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
                "game_online": False,
                "minimized": False,
                "window_state": "error",
                "output_width": 960,
                "output_height": 540,
                "target_fps": 10,
                "last_error": self._last_error,
            }

    def capture_frame(self, mode: str) -> tuple[bytes, dict[str, Any]]:
        safe_mode = normalize_view_mode(mode)
        try:
            frame = self._ensure_capture().capture(safe_mode)
            self._last_error = None
            self._last_frame_at = time.time()
            self._last_frame_size = len(frame.jpeg)
            metadata = {
                "type": "stream_status",
                "state": "live",
                "mode": frame.view_mode,
                "source_width": frame.source_width,
                "source_height": frame.source_height,
                "output_width": 960,
                "output_height": 540,
                "window_state": frame.window_state,
                "capture_source": frame.target.source_kind,
                "timestamp": self._last_frame_at,
            }
            return frame.jpeg, metadata
        except Exception as error:
            self._last_error = str(error)
            self.release_all()
            raise

    def activate_control(self) -> None:
        self._ensure_control().activate()
        self._last_error = None

    def deactivate_control(self) -> None:
        if self._control is not None:
            self._control.deactivate()

    def click_game_center(self) -> None:
        try:
            self._ensure_control().click_center()
            self._last_error = None
        except Exception as error:
            self._last_error = str(error)
            raise

    def apply_keys(self, pressed: Iterable[str]) -> list[str]:
        try:
            result = self._ensure_control().apply_state(pressed)
            self._last_error = None
            return sorted(result)
        except Exception as error:
            self._last_error = str(error)
            self.release_all()
            raise

    def release_all(self) -> None:
        if self._control is not None:
            self._control.release_all()

    def close(self) -> None:
        self.release_all()
        if self._capture is not None:
            self._capture.close()
