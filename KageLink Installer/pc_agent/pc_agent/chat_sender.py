from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

import win32api
import win32con
import win32gui

from .config import InputControlPreference
from .windows import (
    GA_ROOT,
    WindowCandidate,
    choose_input_candidate,
    ensure_game_window_foreground,
    input_candidates,
    select_input_control,
)


VALID_CHANNELS = {"ooc", "ic"}

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t


class ChatSender:
    def __init__(
        self,
        game_title: str,
        input_class: str,
        preferences: dict[str, InputControlPreference],
        min_interval_seconds: float,
    ) -> None:
        self.game_title = game_title
        self.input_class = input_class
        self.preferences = preferences
        self.min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._last_send_at = 0.0

    @staticmethod
    def _channel(channel: str) -> str:
        normalized = str(channel or "ooc").strip().lower()
        if normalized not in VALID_CHANNELS:
            raise ValueError("INVALID_CHANNEL")
        return normalized

    def preference(self, channel: str) -> InputControlPreference:
        return self.preferences[self._channel(channel)]

    def update_preference(self, channel: str, preference: InputControlPreference) -> None:
        self.preferences[self._channel(channel)] = preference

    def locate(self, channel: str = "ooc") -> tuple[int | None, WindowCandidate | None]:
        preference = self.preference(channel)
        return select_input_control(
            self.game_title,
            self.input_class,
            preference.preferred_width,
            preference.preferred_height,
            preference.relative_left,
            preference.relative_top,
            preference.candidate_index,
            preference.parent_class,
        )

    def locate_channels(self) -> tuple[int | None, dict[str, WindowCandidate | None]]:
        game_hwnd, candidates = input_candidates(self.game_title, self.input_class)
        located: dict[str, WindowCandidate | None] = {}
        for channel in ("ooc", "ic"):
            preference = self.preference(channel)
            located[channel] = choose_input_candidate(
                candidates,
                preference.preferred_width,
                preference.preferred_height,
                preference.relative_left,
                preference.relative_top,
                preference.candidate_index,
                preference.parent_class,
            )

        # A single Edit control can never represent both destinations safely.
        # Preserve the already validated OOC route and require IC calibration.
        ooc_control = located.get("ooc")
        ic_control = located.get("ic")
        if ooc_control and ic_control and ooc_control.hwnd == ic_control.hwnd:
            located["ic"] = None

        return game_hwnd, located

    def send(self, message: str, channel: str = "ooc") -> dict:
        safe_channel = self._channel(channel)
        cleaned = message.replace("\r", " ").replace("\n", " ").strip()
        if not cleaned:
            raise ValueError("EMPTY_MESSAGE")

        with self._lock:
            elapsed = time.monotonic() - self._last_send_at
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)

            focus = ensure_game_window_foreground(self.game_title)
            if not focus.window_found:
                raise RuntimeError("GAME_NOT_FOUND")
            if not focus.foreground_confirmed:
                raise RuntimeError("FOREGROUND_FAILED")

            # Locate again after restore/focus because BYOND can recreate controls.
            # The shared scan also prevents OOC and IC from resolving to the
            # same HWND when a legacy preference is ambiguous.
            game_hwnd, located_inputs = self.locate_channels()
            input_control = located_inputs.get(safe_channel)
            if game_hwnd is None:
                raise RuntimeError("GAME_NOT_FOUND")
            if input_control is None:
                raise RuntimeError(f"{safe_channel.upper()}_INPUT_NOT_FOUND")

            self._write_text(input_control.hwnd, cleaned)
            self._click_and_press_enter(game_hwnd, input_control.hwnd)
            self._last_send_at = time.monotonic()

            return {
                "ok": True,
                "message": cleaned,
                "channel": safe_channel,
                "input": input_control.to_dict(),
                "focus": focus.to_dict(),
            }

    @staticmethod
    def _write_text(input_hwnd: int, message: str) -> None:
        buffer = ctypes.create_unicode_buffer(message)
        user32.SendMessageW(input_hwnd, win32con.WM_SETTEXT, 0, ctypes.addressof(buffer))
        time.sleep(0.15)

    @staticmethod
    def _click_and_press_enter(game_hwnd: int, input_hwnd: int) -> None:
        if not win32gui.IsWindow(input_hwnd):
            raise RuntimeError("INPUT_NOT_FOUND")
        root_hwnd = int(user32.GetAncestor(input_hwnd, GA_ROOT) or 0) or game_hwnd
        if not win32gui.IsWindow(root_hwnd):
            raise RuntimeError("GAME_NOT_FOUND")

        old_mouse_position = win32api.GetCursorPos()
        try:
            left, top, right, bottom = win32gui.GetWindowRect(input_hwnd)
            if right <= left or bottom <= top:
                raise RuntimeError("INPUT_INVALID_RECT")
            center = ((left + right) // 2, (top + bottom) // 2)
            win32api.SetCursorPos(center)
            time.sleep(0.10)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.20)
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            time.sleep(0.08)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.30)
        finally:
            try:
                win32api.SetCursorPos(old_mouse_position)
            except Exception:
                pass
