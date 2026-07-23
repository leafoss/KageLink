from __future__ import annotations

import ctypes
from ctypes import wintypes

import win32gui

from .windows import select_chat_control


WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
SMTO_ABORTIFHUNG = 0x0002

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_size_t),
]
user32.SendMessageTimeoutW.restype = wintypes.LPARAM


class ChatReader:
    def __init__(self, game_title: str, chat_class: str) -> None:
        self.game_title = game_title
        self.chat_class = chat_class
        self._chat_hwnd: int | None = None

    @property
    def hwnd(self) -> int | None:
        return self._chat_hwnd

    def locate(self) -> int | None:
        candidate = select_chat_control(self.game_title, self.chat_class)
        self._chat_hwnd = candidate.hwnd if candidate else None
        return self._chat_hwnd

    def _send_timeout(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        result = ctypes.c_size_t(0)
        ok = user32.SendMessageTimeoutW(
            hwnd,
            message,
            wparam,
            lparam,
            SMTO_ABORTIFHUNG,
            1200,
            ctypes.byref(result),
        )
        if not ok:
            return 0
        return int(result.value)

    def read_current(self) -> str:
        hwnd = self._chat_hwnd
        if hwnd is None or not win32gui.IsWindow(hwnd):
            hwnd = self.locate()
        if hwnd is None:
            return ""

        text_length = self._send_timeout(hwnd, WM_GETTEXTLENGTH, 0, 0)
        if text_length <= 0:
            return ""

        buffer = ctypes.create_unicode_buffer(text_length + 1)
        copied = self._send_timeout(
            hwnd,
            WM_GETTEXT,
            text_length + 1,
            ctypes.addressof(buffer),
        )
        if copied <= 0:
            return ""

        return normalize_text(buffer.value)


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\x00")


def find_new_lines(previous: str, current: str) -> tuple[list[str], bool]:
    if not current or current == previous:
        return [], False

    if not previous:
        return [line for line in current.splitlines() if line.strip()], False

    if current.startswith(previous):
        addition = current[len(previous):].lstrip("\n")
        return [line for line in addition.splitlines() if line.strip()], False

    previous_lines = previous.splitlines()
    current_lines = current.splitlines()
    maximum_overlap = min(len(previous_lines), len(current_lines), 800)

    for overlap in range(maximum_overlap, 0, -1):
        if previous_lines[-overlap:] == current_lines[:overlap]:
            return [line for line in current_lines[overlap:] if line.strip()], False

    return [line for line in current_lines if line.strip()], True
