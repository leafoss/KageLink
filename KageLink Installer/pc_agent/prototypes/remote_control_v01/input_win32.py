from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from typing import Callable

import win32con
import win32gui

from pc_agent.game_window import find_exact_game_window
from pc_agent.windows import ensure_game_window_foreground, is_game_window_foreground


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

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
_user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_user32.GetAsyncKeyState.restype = wintypes.SHORT


class InputError(RuntimeError):
    pass


def _key(vk: int, extended: bool = False) -> tuple[int, bool]:
    return int(vk), bool(extended)


KEYS: dict[str, tuple[int, bool]] = {
    **{chr(code).lower(): _key(code) for code in range(ord("A"), ord("Z") + 1)},
    **{str(number): _key(ord(str(number))) for number in range(10)},
    "space": _key(win32con.VK_SPACE),
    "enter": _key(win32con.VK_RETURN),
    "escape": _key(win32con.VK_ESCAPE),
    "tab": _key(win32con.VK_TAB),
    "shift": _key(win32con.VK_SHIFT),
    "ctrl": _key(win32con.VK_CONTROL),
    "alt": _key(win32con.VK_MENU),
    "win": _key(win32con.VK_LWIN, True),
    "backspace": _key(win32con.VK_BACK),
    "insert": _key(win32con.VK_INSERT, True),
    "delete": _key(win32con.VK_DELETE, True),
    "home": _key(win32con.VK_HOME, True),
    "end": _key(win32con.VK_END, True),
    "pageup": _key(win32con.VK_PRIOR, True),
    "pagedown": _key(win32con.VK_NEXT, True),
    "up": _key(win32con.VK_UP, True),
    "down": _key(win32con.VK_DOWN, True),
    "left": _key(win32con.VK_LEFT, True),
    "right": _key(win32con.VK_RIGHT, True),
    **{f"f{number}": _key(win32con.VK_F1 + number - 1) for number in range(1, 13)},
}


_MOUSE_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def _send_keyboard_vk(vk: int, *, extended: bool, down: bool) -> None:
    flags = KEYEVENTF_EXTENDEDKEY if extended else 0
    if not down:
        flags |= KEYEVENTF_KEYUP
    event = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(
            ki=KEYBDINPUT(
                wVk=int(vk),
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


def _send_unicode_unit(unit: int, *, down: bool) -> None:
    flags = KEYEVENTF_UNICODE | (0 if down else KEYEVENTF_KEYUP)
    event = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(
            ki=KEYBDINPUT(
                wVk=0,
                wScan=int(unit),
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            )
        ),
    )
    sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def _send_mouse_flag(flag: int) -> None:
    event = INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=0,
                dwFlags=int(flag),
                time=0,
                dwExtraInfo=0,
            )
        ),
    )
    sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


class SafeInputController:
    """Visible, local-consent-gated Win32 input controller.

    Game mode refuses to type/click unless the exact configured game window is
    available and foreground. Desktop mode exists only when the host process was
    explicitly started with desktop_authorized=True.
    """

    def __init__(
        self,
        *,
        mode: str,
        game_title: str,
        pointer_mapper: Callable[[float, float], tuple[int, int] | None],
        desktop_authorized: bool = False,
    ) -> None:
        normalized = str(mode).strip().casefold()
        if normalized not in {"game", "desktop"}:
            raise ValueError("mode must be game or desktop")
        if normalized == "desktop" and not desktop_authorized:
            raise ValueError("desktop mode requires explicit local authorization")
        self.mode = normalized
        self.game_title = game_title
        self.pointer_mapper = pointer_mapper
        self.desktop_authorized = bool(desktop_authorized)
        self._lock = threading.RLock()
        self._pressed_keys: set[str] = set()
        self._pressed_buttons: set[str] = set()
        self._enabled = False
        self._last_input_at = time.monotonic()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    @property
    def last_input_at(self) -> float:
        with self._lock:
            return self._last_input_at

    def activate(self) -> None:
        with self._lock:
            if self.mode == "game":
                hwnd = find_exact_game_window(self.game_title)
                if hwnd is None:
                    raise InputError("GAME_NOT_FOUND")
                if win32gui.IsIconic(hwnd):
                    raise InputError("GAME_MINIMIZED")
            self._enabled = True

    def deactivate(self) -> None:
        with self._lock:
            self._release_all_locked()
            self._enabled = False

    def _ensure_game_ready(self, *, focus: bool) -> None:
        if self.mode != "game":
            return
        hwnd = find_exact_game_window(self.game_title)
        if hwnd is None:
            self._release_all_locked()
            raise InputError("GAME_NOT_FOUND")
        if win32gui.IsIconic(hwnd):
            self._release_all_locked()
            raise InputError("GAME_MINIMIZED")
        if focus:
            result = ensure_game_window_foreground(self.game_title)
            if not result.ok:
                self._release_all_locked()
                raise InputError(result.error or "FOREGROUND_FAILED")
        if not is_game_window_foreground(hwnd):
            self._release_all_locked()
            raise InputError("FOREGROUND_LOST")

    def _assert_enabled(self) -> None:
        if not self._enabled:
            raise InputError("REMOTE_INPUT_DISABLED")

    def send_key(self, key_name: str, down: bool) -> None:
        key = str(key_name).strip().casefold()
        definition = KEYS.get(key)
        if definition is None:
            raise InputError("KEY_NOT_ALLOWED")
        if self.mode == "game" and key == "win":
            raise InputError("KEY_NOT_ALLOWED_IN_GAME_MODE")
        with self._lock:
            self._assert_enabled()
            self._ensure_game_ready(focus=bool(down))
            if down and key in self._pressed_keys:
                return
            if not down and key not in self._pressed_keys:
                return
            vk, extended = definition
            _send_keyboard_vk(vk, extended=extended, down=bool(down))
            if down:
                self._pressed_keys.add(key)
            else:
                self._pressed_keys.discard(key)
            self._last_input_at = time.monotonic()

    def send_text(self, text: str) -> int:
        value = str(text or "")
        if len(value) > 256:
            raise InputError("TEXT_TOO_LONG")
        # Text messages are text only. Enter/Tab/Backspace travel through the
        # explicit key path and cannot be smuggled through Unicode input.
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
            raise InputError("CONTROL_CHARACTERS_NOT_ALLOWED")
        encoded = value.encode("utf-16-le", errors="strict")
        units = [int.from_bytes(encoded[i : i + 2], "little") for i in range(0, len(encoded), 2)]
        with self._lock:
            self._assert_enabled()
            self._ensure_game_ready(focus=True)
            for unit in units:
                _send_unicode_unit(unit, down=True)
                _send_unicode_unit(unit, down=False)
            self._last_input_at = time.monotonic()
        return len(value)

    def pointer(self, *, x: float, y: float, action: str, button: str = "left") -> None:
        normalized_action = str(action).strip().casefold()
        normalized_button = str(button).strip().casefold()
        if normalized_action not in {"move", "down", "up"}:
            raise InputError("INVALID_POINTER_ACTION")
        if normalized_button not in _MOUSE_FLAGS:
            raise InputError("INVALID_POINTER_BUTTON")
        try:
            nx = float(x)
            ny = float(y)
        except (TypeError, ValueError):
            raise InputError("INVALID_POINTER_COORDINATES") from None
        if not (0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0):
            raise InputError("POINTER_OUT_OF_RANGE")

        with self._lock:
            self._assert_enabled()
            self._ensure_game_ready(focus=normalized_action != "move")
            point = self.pointer_mapper(nx, ny)
            if point is None:
                raise InputError("POINTER_OUTSIDE_CAPTURE")
            sx, sy = point
            if not _user32.SetCursorPos(int(sx), int(sy)):
                raise ctypes.WinError(ctypes.get_last_error())
            if normalized_action == "down":
                if normalized_button not in self._pressed_buttons:
                    _send_mouse_flag(_MOUSE_FLAGS[normalized_button][0])
                    self._pressed_buttons.add(normalized_button)
            elif normalized_action == "up":
                if normalized_button in self._pressed_buttons:
                    _send_mouse_flag(_MOUSE_FLAGS[normalized_button][1])
                    self._pressed_buttons.discard(normalized_button)
            self._last_input_at = time.monotonic()

    def release_all(self) -> None:
        with self._lock:
            self._release_all_locked()

    def _release_all_locked(self) -> None:
        for key in list(self._pressed_keys):
            definition = KEYS.get(key)
            if definition is None:
                continue
            try:
                _send_keyboard_vk(definition[0], extended=definition[1], down=False)
            except Exception:
                pass
        self._pressed_keys.clear()
        for button in list(self._pressed_buttons):
            try:
                _send_mouse_flag(_MOUSE_FLAGS[button][1])
            except Exception:
                pass
        self._pressed_buttons.clear()


def start_kill_switch(
    callback: Callable[[], None],
    *,
    stop_event: threading.Event,
    poll_seconds: float = 0.08,
) -> threading.Thread:
    """Monitor local CTRL+ALT+F12 and invoke callback once per key press."""

    def worker() -> None:
        latched = False
        while not stop_event.is_set():
            ctrl = bool(_user32.GetAsyncKeyState(win32con.VK_CONTROL) & 0x8000)
            alt = bool(_user32.GetAsyncKeyState(win32con.VK_MENU) & 0x8000)
            f12 = bool(_user32.GetAsyncKeyState(win32con.VK_F12) & 0x8000)
            active = ctrl and alt and f12
            if active and not latched:
                latched = True
                try:
                    callback()
                except Exception:
                    pass
            elif not active:
                latched = False
            stop_event.wait(max(0.03, float(poll_seconds)))

    thread = threading.Thread(target=worker, name="KageLinkRemoteKillSwitch", daemon=True)
    thread.start()
    return thread
