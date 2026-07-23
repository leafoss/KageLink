from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Iterable

import win32con
import win32gui

from pc_agent.game_protocol import ALLOWED_KEYS, GAME_WINDOW_TITLE, normalize_pressed
from pc_agent.game_window import (
    find_exact_game_window,
    is_valid_game_target,
    locate_capture_target,
)
from pc_agent.windows import ensure_game_window_foreground, is_game_window_foreground


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
_user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
_user32.SetCursorPos.restype = wintypes.BOOL


@dataclass(frozen=True, slots=True)
class KeyDefinition:
    vk: int
    extended: bool = False


KEYS: dict[str, KeyDefinition] = {
    "up": KeyDefinition(win32con.VK_UP, True),
    "down": KeyDefinition(win32con.VK_DOWN, True),
    "left": KeyDefinition(win32con.VK_LEFT, True),
    "right": KeyDefinition(win32con.VK_RIGHT, True),
    "e": KeyDefinition(ord("E")),
    "space": KeyDefinition(win32con.VK_SPACE),
    "g": KeyDefinition(ord("G")),
    "v": KeyDefinition(ord("V")),
}


class GameControlError(RuntimeError):
    pass


def _send_keyboard(definition: KeyDefinition, down: bool) -> None:
    flags = KEYEVENTF_EXTENDEDKEY if definition.extended else 0
    if not down:
        flags |= KEYEVENTF_KEYUP
    event = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(
            ki=KEYBDINPUT(
                wVk=definition.vk,
                wScan=0,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            )
        ),
    )
    sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def _send_left_click(x: int, y: int) -> None:
    if not _user32.SetCursorPos(int(x), int(y)):
        raise ctypes.WinError(ctypes.get_last_error())

    down = INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=0,
                dwFlags=MOUSEEVENTF_LEFTDOWN,
                time=0,
                dwExtraInfo=0,
            )
        ),
    )
    up = INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=0,
                dwFlags=MOUSEEVENTF_LEFTUP,
                time=0,
                dwExtraInfo=0,
            )
        ),
    )
    for event in (down, up):
        sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())


class GameInputController:
    def __init__(self, title: str = GAME_WINDOW_TITLE) -> None:
        self.title = title
        self._pressed: set[str] = set()
        self._active = False
        self._lock = threading.RLock()
        self._last_hwnd: int | None = None

    @property
    def pressed(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._pressed)

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def activate(self) -> None:
        with self._lock:
            hwnd = find_exact_game_window(self.title)
            if hwnd is None:
                self._active = False
                raise GameControlError("GAME_NOT_FOUND")
            if win32gui.IsIconic(hwnd):
                self._active = False
                raise GameControlError("GAME_MINIMIZED")
            self._last_hwnd = hwnd
            self._active = True

    def deactivate(self) -> None:
        with self._lock:
            self._release_all_locked()
            self._active = False

    def click_center(self) -> None:
        with self._lock:
            if not self._active:
                raise GameControlError("GAME_CONTROL_INACTIVE")

            target = locate_capture_target(self.title)
            if target is None or not is_valid_game_target(target.game_hwnd, self.title):
                raise GameControlError("GAME_NOT_FOUND")
            if target.minimized:
                raise GameControlError("GAME_MINIMIZED")

            focus = ensure_game_window_foreground(self.title)
            if not focus.ok:
                raise GameControlError(focus.error or "FOREGROUND_FAILED")

            center_x = target.left + target.width // 2
            center_y = target.top + target.height // 2
            _send_left_click(center_x, center_y)
            self._last_hwnd = target.game_hwnd

    def apply_state(self, pressed: Iterable[str]) -> frozenset[str]:
        desired = set(normalize_pressed(pressed))
        with self._lock:
            if not self._active:
                raise GameControlError("GAME_CONTROL_INACTIVE")

            hwnd = find_exact_game_window(self.title)
            if hwnd is None or not is_valid_game_target(hwnd, self.title):
                self._release_all_locked()
                self._active = False
                raise GameControlError("GAME_NOT_FOUND")
            if win32gui.IsIconic(hwnd):
                self._release_all_locked()
                self._active = False
                raise GameControlError("GAME_MINIMIZED")

            self._last_hwnd = hwnd
            if desired.difference(ALLOWED_KEYS):
                raise GameControlError("INVALID_GAME_KEYS")
            if self._pressed and not is_game_window_foreground(hwnd):
                self._release_all_locked()
                self._active = False
                raise GameControlError("FOREGROUND_LOST")

            # Key-up must happen before key-down when changing diagonals.
            for key in sorted(self._pressed - desired):
                _send_keyboard(KEYS[key], False)
                self._pressed.discard(key)

            if desired - self._pressed:
                focus = ensure_game_window_foreground(self.title)
                if not focus.ok or not is_game_window_foreground(hwnd):
                    self._release_all_locked()
                    raise GameControlError(focus.error or "FOREGROUND_FAILED")

            for key in sorted(desired - self._pressed):
                _send_keyboard(KEYS[key], True)
                self._pressed.add(key)

            return frozenset(self._pressed)

    def release_all(self) -> None:
        with self._lock:
            self._release_all_locked()

    def _release_all_locked(self) -> None:
        # Releases are intentionally sent even after the game loses focus so
        # Windows cannot retain a globally pressed virtual key.
        for key in sorted(self._pressed):
            try:
                _send_keyboard(KEYS[key], False)
            except Exception:
                pass
        self._pressed.clear()
