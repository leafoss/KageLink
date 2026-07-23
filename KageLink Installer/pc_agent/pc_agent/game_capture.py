from __future__ import annotations

import ctypes
import io
import threading
from dataclasses import dataclass

from pc_agent.game_image import transform_frame
from pc_agent.game_protocol import GAME_WINDOW_TITLE, normalize_view_mode
from pc_agent.game_window import CaptureTarget, locate_capture_target, show_state
from pc_agent.windows import ensure_game_window_foreground, is_game_window_foreground


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    jpeg: bytes
    source_width: int
    source_height: int
    target: CaptureTarget
    view_mode: str
    window_state: str


class GameCaptureError(RuntimeError):
    pass


class GameWindowMissing(GameCaptureError):
    pass


class GameWindowMinimized(GameCaptureError):
    pass


class GameCapture:
    def __init__(
        self,
        title: str = GAME_WINDOW_TITLE,
        *,
        output_size: tuple[int, int] = (960, 540),
        jpeg_quality: int = 70,
    ) -> None:
        self.title = title
        self.output_size = output_size
        self.jpeg_quality = max(40, min(90, int(jpeg_quality)))
        self._lock = threading.Lock()

    def _print_window_capture(self, target: CaptureTarget):
        from PIL import Image
        import win32gui
        import win32ui

        hwnd_dc = win32gui.GetWindowDC(target.capture_hwnd)
        source_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        memory_dc = source_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(source_dc, target.width, target.height)
        memory_dc.SelectObject(bitmap)
        try:
            # PW_CLIENTONLY | PW_RENDERFULLCONTENT. BYOND normally renders its
            # client through GDI, so this path stays window-specific even if
            # another application overlaps the game.
            rendered = ctypes.windll.user32.PrintWindow(
                target.capture_hwnd,
                memory_dc.GetSafeHdc(),
                0x00000003,
            )
            if rendered != 1:
                raise GameCaptureError("PRINT_WINDOW_FAILED")
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
                raise GameCaptureError("PRINT_WINDOW_BLACK_FRAME")
            return image
        finally:
            try:
                win32gui.DeleteObject(bitmap.GetHandle())
            except Exception:
                pass
            memory_dc.DeleteDC()
            source_dc.DeleteDC()
            win32gui.ReleaseDC(target.capture_hwnd, hwnd_dc)

    def _foreground_screen_capture(self, target: CaptureTarget):
        from PIL import Image
        import mss

        focus = ensure_game_window_foreground(self.title)
        if not focus.ok:
            raise GameCaptureError(focus.error or "FOREGROUND_FAILED")
        refreshed = locate_capture_target(self.title)
        if refreshed is None:
            raise GameWindowMissing("GAME_NOT_FOUND")
        if refreshed.minimized:
            raise GameWindowMinimized("GAME_MINIMIZED")
        if not is_game_window_foreground(refreshed.game_hwnd):
            raise GameCaptureError("FOREGROUND_FAILED")
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

    def _capture_source(self, target: CaptureTarget):
        try:
            return self._print_window_capture(target), target
        except Exception:
            # Screen capture is allowed only after the exact game window has
            # been foregrounded, avoiding accidental capture of personal apps.
            return self._foreground_screen_capture(target)

    def capture(self, mode: str = "full") -> CapturedFrame:
        with self._lock:
            target = locate_capture_target(self.title)
            if target is None:
                raise GameWindowMissing("GAME_NOT_FOUND")
            if target.minimized:
                raise GameWindowMinimized("GAME_MINIMIZED")

            image, target = self._capture_source(target)
            source_width, source_height = image.size
            processed = transform_frame(image, mode, self.output_size)
            output = io.BytesIO()
            processed.save(
                output,
                format="JPEG",
                quality=self.jpeg_quality,
                optimize=False,
                progressive=False,
                subsampling=2,
            )
            return CapturedFrame(
                jpeg=output.getvalue(),
                source_width=source_width,
                source_height=source_height,
                target=target,
                view_mode=normalize_view_mode(mode),
                window_state=show_state(target.game_hwnd),
            )

    def close(self) -> None:
        return None
