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
    capture_backend: str = "hwnd-client"


def _select_window_match(
    matches: list[tuple[int, str]],
    requested_title: str,
    previous_hwnd: int | None = None,
) -> tuple[int, str]:
    """Prefer the exact game title and keep a previously validated HWND stable."""
    if not matches:
        raise WindowNotFoundError(f"Window containing '{requested_title}' was not found")

    normalized = requested_title.strip().casefold()
    exact = [item for item in matches if item[1].strip().casefold() == normalized]
    if exact:
        if previous_hwnd is not None:
            retained = next((item for item in exact if item[0] == previous_hwnd), None)
            if retained is not None:
                return retained
        return exact[0]

    if previous_hwnd is not None:
        retained = next((item for item in matches if item[0] == previous_hwnd), None)
        if retained is not None:
            return retained

    # Debug consoles and helper windows commonly append text to the game title.
    # The shortest matching title is the safest fallback when no exact title exists.
    return min(matches, key=lambda item: (len(item[1]), item[1].casefold()))


def _load_win32() -> tuple[Any, Any, Any]:
    """Load pointer-safe Win32 declarations for both 32-bit and 64-bit Python."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.EnumWindows.argtypes = [enum_callback, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PrintWindow.restype = wintypes.BOOL
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.c_void_p,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    gdi32.CreateDIBSection.restype = wintypes.HANDLE
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL

    return user32, gdi32, enum_callback


class WindowsClientCapture:
    """Capture pixels owned by one Windows HWND client area, never the desktop.

    The old backend resolved the game rectangle and then asked MSS to screenshot
    those monitor coordinates. In fullscreen that could copy the whole monitor or
    any overlay covering the game. This backend never calls a monitor screenshot
    API. It renders only the selected HWND client into an in-memory bitmap.
    """

    PW_CLIENTONLY = 0x00000001
    PW_RENDERFULLCONTENT = 0x00000002
    SRCCOPY = 0x00CC0020
    CAPTUREBLT = 0x40000000
    BI_RGB = 0
    DIB_RGB_COLORS = 0

    def __init__(self, title_contains: str) -> None:
        if os.name != "nt":
            raise WindowCaptureError("Windows client capture is only available on Windows")
        if not title_contains.strip():
            raise ValueError("title_contains cannot be empty")
        self.title_contains = title_contains.strip()
        self._hwnd: int | None = None
        self._closed = False
        self._user32, self._gdi32, self._enum_callback = _load_win32()

    def locate(self) -> WindowBounds:
        import ctypes
        from ctypes import wintypes

        if self._closed:
            raise WindowCaptureError("Capture backend is closed")

        matches: list[tuple[int, str]] = []

        def callback(hwnd: int, _lparam: int) -> bool:
            if not self._user32.IsWindowVisible(hwnd):
                return True
            length = self._user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            self._user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if self.title_contains.casefold() in title.casefold():
                matches.append((int(hwnd), title))
            return True

        callback_pointer = self._enum_callback(callback)
        if not self._user32.EnumWindows(callback_pointer, 0):
            raise WindowCaptureError("EnumWindows failed while locating the game HWND")

        selected = _select_window_match(matches, self.title_contains, self._hwnd)
        self._hwnd = selected[0]
        hwnd = wintypes.HWND(self._hwnd)

        rect = wintypes.RECT()
        if not self._user32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise WindowCaptureError("GetClientRect failed for the selected game HWND")

        origin = wintypes.POINT(0, 0)
        if not self._user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            raise WindowCaptureError("ClientToScreen failed for the selected game HWND")

        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            raise WindowCaptureError("Game client area has invalid dimensions")

        foreground_hwnd = self._user32.GetForegroundWindow()
        return WindowBounds(
            hwnd=self._hwnd,
            title=selected[1],
            left=int(origin.x),
            top=int(origin.y),
            width=width,
            height=height,
            minimized=bool(self._user32.IsIconic(hwnd)),
            foreground=int(foreground_hwnd or 0) == self._hwnd,
        )

    def capture(self) -> tuple[Any, WindowBounds]:
        bounds = self.locate()
        if bounds.minimized:
            raise WindowCaptureError("The game window is minimized")

        frame = self._capture_print_window(bounds)
        backend = "PrintWindow(PW_CLIENTONLY)"
        if frame is None or self._looks_unrendered(frame):
            frame = self._capture_window_dc(bounds)
            backend = "BitBlt(GetDC(hwnd))"

        if frame is None or self._looks_unrendered(frame):
            raise WindowCaptureError(
                "The selected Shinobi Story Online HWND did not return usable client pixels. "
                "No desktop or monitor screenshot fallback was used. Keep the game visible and try again."
            )

        return frame, WindowBounds(
            hwnd=bounds.hwnd,
            title=bounds.title,
            left=bounds.left,
            top=bounds.top,
            width=bounds.width,
            height=bounds.height,
            minimized=bounds.minimized,
            foreground=bounds.foreground,
            capture_backend=backend,
        )

    def _capture_print_window(self, bounds: WindowBounds) -> Any | None:
        from ctypes import wintypes

        hwnd = wintypes.HWND(bounds.hwnd)
        return self._capture_into_dib(
            bounds,
            lambda memory_dc: bool(
                self._user32.PrintWindow(
                    hwnd,
                    memory_dc,
                    self.PW_CLIENTONLY | self.PW_RENDERFULLCONTENT,
                )
            ),
        )

    def _capture_window_dc(self, bounds: WindowBounds) -> Any | None:
        from ctypes import wintypes

        hwnd = wintypes.HWND(bounds.hwnd)
        source_dc = self._user32.GetDC(hwnd)
        if not source_dc:
            return None
        try:
            return self._capture_into_dib(
                bounds,
                lambda memory_dc: bool(
                    self._gdi32.BitBlt(
                        memory_dc,
                        0,
                        0,
                        bounds.width,
                        bounds.height,
                        source_dc,
                        0,
                        0,
                        self.SRCCOPY | self.CAPTUREBLT,
                    )
                ),
            )
        finally:
            self._user32.ReleaseDC(hwnd, source_dc)

    def _capture_into_dib(self, bounds: WindowBounds, render: Any) -> Any | None:
        import ctypes
        from ctypes import wintypes

        import numpy as np

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [
                ("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3),
            ]

        memory_dc = self._gdi32.CreateCompatibleDC(None)
        if not memory_dc:
            return None

        bits = ctypes.c_void_p()
        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = bounds.width
        # Negative height creates a top-down DIB matching NumPy row order.
        bitmap_info.bmiHeader.biHeight = -bounds.height
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = self.BI_RGB
        bitmap_info.bmiHeader.biSizeImage = bounds.width * bounds.height * 4

        bitmap = self._gdi32.CreateDIBSection(
            memory_dc,
            ctypes.byref(bitmap_info),
            self.DIB_RGB_COLORS,
            ctypes.byref(bits),
            None,
            0,
        )
        if not bitmap or not bits.value:
            self._gdi32.DeleteDC(memory_dc)
            return None

        previous = self._gdi32.SelectObject(memory_dc, bitmap)
        try:
            if not render(memory_dc):
                return None
            byte_count = bounds.width * bounds.height * 4
            raw = ctypes.string_at(bits.value, byte_count)
            bgra = np.frombuffer(raw, dtype=np.uint8).reshape((bounds.height, bounds.width, 4))
            return bgra[:, :, :3].copy()
        finally:
            if previous:
                self._gdi32.SelectObject(memory_dc, previous)
            self._gdi32.DeleteObject(bitmap)
            self._gdi32.DeleteDC(memory_dc)

    @staticmethod
    def _looks_unrendered(frame: Any) -> bool:
        import numpy as np

        if frame is None or not hasattr(frame, "shape") or frame.size == 0:
            return True
        sample = frame[:: max(1, frame.shape[0] // 64), :: max(1, frame.shape[1] // 64)]
        if sample.size == 0:
            return True
        # PrintWindow commonly returns a fully black DIB for unsupported renderers.
        # A real dark game frame still contains HUD/text variation.
        channel_range = float(np.ptp(sample.astype(np.int16)))
        mean = float(sample.mean())
        return channel_range < 2.0 and mean < 2.0

    def close(self) -> None:
        self._closed = True
