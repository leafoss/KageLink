from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class WindowCaptureError(RuntimeError):
    pass


class WindowNotFoundError(WindowCaptureError):
    pass


@dataclass(frozen=True, slots=True)
class WindowBounds:
    hwnd: int
    title: str
    left: int
    top: int
    width: int
    height: int
    minimized: bool
    foreground: bool


class WindowsClientCapture:
    """Capture only the visible client rectangle associated with a Windows HWND."""

    def __init__(self, title_contains: str) -> None:
        if os.name != "nt":
            raise WindowCaptureError("Windows client capture is only available on Windows")
        self.title_contains = title_contains
        try:
            import mss
        except ImportError as exc:
            raise WindowCaptureError("Missing dependency 'mss'. Run setup_navigation.ps1 again.") from exc
        self._grabber = mss.mss()
        self._hwnd: int | None = None

    def locate(self) -> WindowBounds:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        matches: list[tuple[int, str]] = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value
            if self.title_contains.casefold() in title.casefold():
                matches.append((int(hwnd), title))
            return True

        user32.EnumWindows(callback_type(callback), 0)
        if not matches:
            raise WindowNotFoundError(f"Window containing '{self.title_contains}' was not found")
        selected = next((item for item in matches if item[0] == self._hwnd), matches[0])
        self._hwnd = selected[0]
        rect = wintypes.RECT()
        if not user32.GetClientRect(self._hwnd, ctypes.byref(rect)):
            raise WindowCaptureError("GetClientRect failed")
        origin = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(self._hwnd, ctypes.byref(origin)):
            raise WindowCaptureError("ClientToScreen failed")
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            raise WindowCaptureError("Game client area has invalid dimensions")
        return WindowBounds(
            hwnd=self._hwnd,
            title=selected[1],
            left=int(origin.x),
            top=int(origin.y),
            width=width,
            height=height,
            minimized=bool(user32.IsIconic(self._hwnd)),
            foreground=int(user32.GetForegroundWindow()) == self._hwnd,
        )

    def capture(self) -> tuple[Any, WindowBounds]:
        import numpy as np

        bounds = self.locate()
        if bounds.minimized:
            raise WindowCaptureError("The game window is minimized")
        shot = self._grabber.grab({
            "left": bounds.left,
            "top": bounds.top,
            "width": bounds.width,
            "height": bounds.height,
        })
        bgra = np.asarray(shot, dtype=np.uint8)
        return bgra[:, :, :3].copy(), bounds

    def close(self) -> None:
        self._grabber.close()
