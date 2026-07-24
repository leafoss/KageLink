from __future__ import annotations

import ctypes
import io
import threading
import time
from dataclasses import dataclass

from pc_agent.game_protocol import GAME_WINDOW_TITLE
from pc_agent.stats_window import StatsTarget, locate_stats_target


@dataclass(frozen=True, slots=True)
class CapturedStatsFrame:
    jpeg: bytes
    source_width: int
    source_height: int
    output_width: int
    output_height: int
    target: StatsTarget


class StatsCaptureError(RuntimeError):
    pass


class StatsWindowMissing(StatsCaptureError):
    pass


class StatsWindowMinimized(StatsCaptureError):
    pass


class StatsCapture:
    def __init__(
        self,
        game_title: str = GAME_WINDOW_TITLE,
        *,
        max_output_size: tuple[int, int] = (960, 1080),
        jpeg_quality: int = 74,
    ) -> None:
        self.game_title = game_title
        self.max_output_size = max_output_size
        self.jpeg_quality = max(40, min(90, int(jpeg_quality)))
        self._lock = threading.Lock()

    def _print_window_capture(self, target: StatsTarget):
        from PIL import Image
        import win32gui
        import win32ui

        hwnd_dc = win32gui.GetDC(target.hwnd)
        source_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        memory_dc = source_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(source_dc, target.width, target.height)
        memory_dc.SelectObject(bitmap)
        try:
            rendered = ctypes.windll.user32.PrintWindow(
                target.hwnd,
                memory_dc.GetSafeHdc(),
                0x00000003,  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
            )
            if rendered != 1:
                raise StatsCaptureError("STATS_PRINT_WINDOW_FAILED")
            bitmap_info = bitmap.GetInfo()
            bitmap_bytes = bitmap.GetBitmapBits(True)
            image = Image.frombuffer(
                "RGB",
                (bitmap_info["bmWidth"], bitmap_info["bmHeight"]),
                bitmap_bytes,
                "raw",
                "BGRX",
                0,
                1,
            ).copy()
            extrema = image.convert("L").getextrema()
            if extrema == (0, 0):
                raise StatsCaptureError("STATS_PRINT_WINDOW_BLACK_FRAME")
            return image
        finally:
            try:
                win32gui.DeleteObject(bitmap.GetHandle())
            except Exception:
                pass
            memory_dc.DeleteDC()
            source_dc.DeleteDC()
            win32gui.ReleaseDC(target.hwnd, hwnd_dc)

    @staticmethod
    def _foreground_window(hwnd: int) -> None:
        import win32api
        import win32con
        import win32gui

        if not win32gui.IsWindow(hwnd):
            raise StatsWindowMissing("STATS_NOT_FOUND")
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.18)
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.12)
        except win32gui.error:
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

    def _foreground_screen_capture(self, target: StatsTarget):
        from PIL import Image
        import mss

        self._foreground_window(target.hwnd)
        refreshed = locate_stats_target(self.game_title)
        if refreshed is None:
            raise StatsWindowMissing("STATS_NOT_FOUND")
        if refreshed.minimized:
            raise StatsWindowMinimized("STATS_MINIMIZED")
        with mss.mss() as screen:
            shot = screen.grab(
                {
                    "left": refreshed.left,
                    "top": refreshed.top,
                    "width": refreshed.width,
                    "height": refreshed.height,
                }
            )
            return Image.frombytes("RGB", shot.size, shot.rgb), refreshed

    def _capture_source(self, target: StatsTarget):
        try:
            return self._print_window_capture(target), target
        except Exception:
            return self._foreground_screen_capture(target)

    def capture(self) -> CapturedStatsFrame:
        from PIL import Image

        with self._lock:
            target = locate_stats_target(self.game_title)
            if target is None:
                raise StatsWindowMissing("STATS_NOT_FOUND")
            if target.minimized:
                raise StatsWindowMinimized("STATS_MINIMIZED")

            image, target = self._capture_source(target)
            source_width, source_height = image.size
            processed = image.copy()
            processed.thumbnail(self.max_output_size, Image.Resampling.BILINEAR)
            output_width, output_height = processed.size
            if output_width <= 0 or output_height <= 0:
                raise StatsCaptureError("STATS_INVALID_FRAME_SIZE")

            output = io.BytesIO()
            processed.save(
                output,
                format="JPEG",
                quality=self.jpeg_quality,
                optimize=False,
                progressive=False,
                subsampling=2,
            )
            return CapturedStatsFrame(
                jpeg=output.getvalue(),
                source_width=source_width,
                source_height=source_height,
                output_width=output_width,
                output_height=output_height,
                target=target,
            )

    def close(self) -> None:
        return None
