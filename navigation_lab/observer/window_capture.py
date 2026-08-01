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

    # A shorter title is normally the real game window; consoles/debug windows
    # often append extra text around the requested title.
    return min(matches, key=lambda item: (len(item[1]), item[1].casefold()))


class WindowsClientCapture:
    """Capture pixels owned by one Windows HWND client area, never the desktop.

    The previous implementation used MSS after resolving the window rectangle.
    That copied whatever happened to be visible at those monitor coordinates and
    could therefore include the desktop, overlays or another foreground window.

    This implementation renders the selected HWND client directly into an
    in-memory DIB with PrintWindow(PW_CLIENTONLY). If the application does not
    support PrintWindow, it falls back to BitBlt from GetDC(hwnd), which is still
    scoped to the selected window client and never calls a monitor screenshot API.
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

    def locate(self) -> WindowBounds:
        import ctypes
        from ctypes import wintypes

        if self._closed:
            raise WindowCaptureError("Capture backend is closed")

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
            title = buffer.value.strip()
            if self.title_contains.casefold() in title.casefold():
                matches.append((int(hwnd), title))
            return True

        user32.EnumWindows(callback_type(callback), 0)
        selected = _select_window_match(matches, self.title_contains, self._hwnd)
        self._hwnd = selected[0]

        rect = wintypes.RECT()
        if not user32.GetClientRect(self._hwnd, ctypes.byref(rect)):
            raise WindowCaptureError("GetClientRect failed for the selected game HWND")

        origin = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(self._hwnd, ctypes.byref(origin)):
            raise WindowCaptureError("ClientToScreen failed for the selected game HWND")

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
                "No desktop screenshot fallback was used. Keep the game visible and try again."
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
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        return self._capture_into_dib(
            bounds,
            lambda memory_dc: bool(
                user32.PrintWindow(
                    wintypes.HWND(bounds.hwnd),
                    memory_dc,
                    self.PW_CLIENTONLY | self.PW_RENDERFULLCONTENT,
                )
            ),
        )

    def _capture_window_dc(self, bounds: WindowBounds) -> Any | None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        source_dc = user32.GetDC(wintypes.HWND(bounds.hwnd))
        if not source_dc:
            return None
        try:
            return self._capture_into_dib(
                bounds,
                lambda memory_dc: bool(
                    gdi32.BitBlt(
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
            user32.ReleaseDC(wintypes.HWND(bounds.hwnd), source_dc)

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

        gdi32 = ctypes.windll.gdi32
        screen_dc = gdi32.CreateCompatibleDC(0)
        if not screen_dc:
            return None

        bits = ctypes.c_void_p()
        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = bounds.width
        # Negative height creates a top-down DIB, matching NumPy row order.
        bitmap_info.bmiHeader.biHeight = -bounds.height
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = self.BI_RGB
        bitmap_info.bmiHeader.biSizeImage = bounds.width * bounds.height * 4

        bitmap = gdi32.CreateDIBSection(
            screen_dc,
            ctypes.byref(bitmap_info),
            self.DIB_RGB_COLORS,
            ctypes.byref(bits),
            None,
            0,
        )
        if not bitmap or not bits.value:
            gdi32.DeleteDC(screen_dc)
            return None

        previous = gdi32.SelectObject(screen_dc, bitmap)
        try:
            if not render(screen_dc):
                return None
            byte_count = bounds.width * bounds.height * 4
            raw = ctypes.string_at(bits.value, byte_count)
            bgra = np.frombuffer(raw, dtype=np.uint8).reshape((bounds.height, bounds.width, 4))
            return bgra[:, :, :3].copy()
        finally:
            if previous:
                gdi32.SelectObject(screen_dc, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(screen_dc)

    @staticmethod
    def _looks_unrendered(frame: Any) -> bool:
        import numpy as np

        if frame is None or not hasattr(frame, "shape") or frame.size == 0:
            return True
        sample = frame[:: max(1, frame.shape[0] // 64), :: max(1, frame.shape[1] // 64)]
        if sample.size == 0:
            return True
        # PrintWindow commonly returns a completely black or transparent DIB
        # when a renderer does not support it. A genuinely dark game frame still
        # has UI/text variation, so both near-zero range and mean are required.
        channel_range = float(np.ptp(sample.astype(np.int16)))
        mean = float(sample.mean())
        return channel_range < 2.0 and mean < 2.0

    def close(self) -> None:
        self._closed = True
