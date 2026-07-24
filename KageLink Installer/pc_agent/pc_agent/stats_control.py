from __future__ import annotations

import threading
import time

import win32api
import win32con
import win32gui

from pc_agent.game_protocol import GAME_WINDOW_TITLE
from pc_agent.game_window import locate_capture_target
from pc_agent.stats_protocol import (
    STATS_OPEN_X,
    STATS_OPEN_Y,
    normalized_client_point,
)
from pc_agent.stats_window import is_valid_stats_target, locate_stats_target
from pc_agent.windows import ensure_game_window_foreground


class StatsControlError(RuntimeError):
    pass


def _foreground_window(hwnd: int) -> None:
    if not hwnd or not win32gui.IsWindow(hwnd):
        raise StatsControlError("STATS_NOT_FOUND")
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.18)
    try:
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.12)
    except win32gui.error:
        try:
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(
                win32con.VK_MENU,
                0,
                win32con.KEYEVENTF_KEYUP,
                0,
            )
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.12)
        except win32gui.error as error:
            raise StatsControlError(f"STATS_FOREGROUND_FAILED: {error}") from error


def _mouse_click(x: int, y: int, button: str) -> None:
    win32api.SetCursorPos((int(x), int(y)))
    if button == "left":
        down = win32con.MOUSEEVENTF_LEFTDOWN
        up = win32con.MOUSEEVENTF_LEFTUP
    elif button == "right":
        down = win32con.MOUSEEVENTF_RIGHTDOWN
        up = win32con.MOUSEEVENTF_RIGHTUP
    else:
        raise StatsControlError("INVALID_STATS_MOUSE_BUTTON")
    win32api.mouse_event(down, 0, 0, 0, 0)
    win32api.mouse_event(up, 0, 0, 0, 0)


class StatsInputController:
    def __init__(self, game_title: str = GAME_WINDOW_TITLE) -> None:
        self.game_title = game_title
        self._active = False
        self._lock = threading.RLock()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def activate(self) -> None:
        with self._lock:
            self._active = True

    def deactivate(self) -> None:
        with self._lock:
            self._active = False

    def open_stats(self, timeout_seconds: float = 5.0) -> tuple[int, bool]:
        with self._lock:
            if not self._active:
                raise StatsControlError("STATS_CONTROL_INACTIVE")

            existing = locate_stats_target(self.game_title)
            if existing is not None:
                _foreground_window(existing.hwnd)
                return existing.hwnd, False

            game_target = locate_capture_target(self.game_title)
            if game_target is None:
                raise StatsControlError("GAME_NOT_FOUND")
            if game_target.minimized:
                raise StatsControlError("GAME_MINIMIZED")

            focus = ensure_game_window_foreground(self.game_title)
            if not focus.ok:
                raise StatsControlError(focus.error or "FOREGROUND_FAILED")

            refreshed = locate_capture_target(self.game_title)
            if refreshed is None:
                raise StatsControlError("GAME_NOT_FOUND")
            click_x, click_y = normalized_client_point(
                refreshed.left,
                refreshed.top,
                refreshed.width,
                refreshed.height,
                STATS_OPEN_X,
                STATS_OPEN_Y,
            )
            if not (
                refreshed.left <= click_x < refreshed.left + refreshed.width
                and refreshed.top <= click_y < refreshed.top + refreshed.height
            ):
                raise StatsControlError("STATS_OPEN_POINT_OUTSIDE_GAME")
            _mouse_click(click_x, click_y, "left")

            deadline = time.monotonic() + max(0.5, timeout_seconds)
            while time.monotonic() < deadline:
                target = locate_stats_target(self.game_title)
                if target is not None:
                    _foreground_window(target.hwnd)
                    return target.hwnd, True
                time.sleep(0.10)
            raise StatsControlError("STATS_NOT_FOUND_AFTER_OPEN_CLICK")

    def click(
        self,
        x: float,
        y: float,
        button: str,
        *,
        expected_hwnd: int | None,
    ) -> int:
        with self._lock:
            if not self._active:
                raise StatsControlError("STATS_CONTROL_INACTIVE")
            if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
                raise StatsControlError("INVALID_STATS_COORDINATES")
            if button not in {"left", "right"}:
                raise StatsControlError("INVALID_STATS_MOUSE_BUTTON")
            if not expected_hwnd:
                raise StatsControlError("STATS_FRAME_NOT_READY")

            target = locate_stats_target(self.game_title)
            if target is None:
                raise StatsControlError("STATS_NOT_FOUND")
            if target.hwnd != expected_hwnd:
                raise StatsControlError("STATS_WINDOW_CHANGED")
            if target.minimized:
                raise StatsControlError("STATS_MINIMIZED")
            if not is_valid_stats_target(target.hwnd, target.process_id):
                raise StatsControlError("INVALID_STATS_WINDOW")

            _foreground_window(target.hwnd)
            refreshed = locate_stats_target(self.game_title)
            if refreshed is None or refreshed.hwnd != expected_hwnd:
                raise StatsControlError("STATS_WINDOW_CHANGED")
            if not is_valid_stats_target(refreshed.hwnd, refreshed.process_id):
                raise StatsControlError("INVALID_STATS_WINDOW")

            screen_x, screen_y = normalized_client_point(
                refreshed.left,
                refreshed.top,
                refreshed.width,
                refreshed.height,
                x,
                y,
            )
            if not (
                refreshed.left <= screen_x < refreshed.left + refreshed.width
                and refreshed.top <= screen_y < refreshed.top + refreshed.height
            ):
                raise StatsControlError("STATS_CLICK_OUTSIDE_CLIENT")

            _mouse_click(screen_x, screen_y, button)
            return refreshed.hwnd
