from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageDraw

from pc_agent.game_capture import GameCapture, GameCaptureError, GameWindowMinimized, GameWindowMissing


CaptureMode = Literal["game", "desktop"]


@dataclass(frozen=True, slots=True)
class MappingState:
    mode: CaptureMode
    output_width: int
    output_height: int
    screen_left: int
    screen_top: int
    screen_width: int
    screen_height: int
    content_left: float = 0.0
    content_top: float = 0.0
    content_width: float | None = None
    content_height: float | None = None

    def map_normalized(self, x: float, y: float) -> tuple[int, int] | None:
        px = float(x) * self.output_width
        py = float(y) * self.output_height
        content_width = self.content_width if self.content_width is not None else float(self.output_width)
        content_height = self.content_height if self.content_height is not None else float(self.output_height)
        left = float(self.content_left)
        top = float(self.content_top)
        if px < left or py < top or px > left + content_width or py > top + content_height:
            return None
        if content_width <= 0 or content_height <= 0:
            return None
        ux = min(1.0, max(0.0, (px - left) / content_width))
        uy = min(1.0, max(0.0, (py - top) / content_height))
        sx = self.screen_left + int(round(ux * max(0, self.screen_width - 1)))
        sy = self.screen_top + int(round(uy * max(0, self.screen_height - 1)))
        return sx, sy


@dataclass(frozen=True, slots=True)
class LatestFrame:
    sequence: int
    captured_at: float
    image: Image.Image
    mapping: MappingState | None
    state: str
    capture_ms: float


class FrameSource:
    def capture(self) -> tuple[Image.Image, MappingState, str]:
        raise NotImplementedError

    def close(self) -> None:
        return None


class GameFrameSource(FrameSource):
    def __init__(
        self,
        *,
        game_title: str,
        output_width: int,
        output_height: int,
        jpeg_quality: int = 82,
    ) -> None:
        self.output_width = max(640, int(output_width))
        self.output_height = max(360, int(output_height))
        self.capture_engine = GameCapture(
            game_title,
            output_size=(self.output_width, self.output_height),
            jpeg_quality=max(50, min(90, int(jpeg_quality))),
        )

    def capture(self) -> tuple[Image.Image, MappingState, str]:
        frame = self.capture_engine.capture("full")
        image = Image.open(io.BytesIO(frame.jpeg)).convert("RGB")
        scale = min(
            self.output_width / max(1, frame.source_width),
            self.output_height / max(1, frame.source_height),
        )
        content_width = max(1.0, frame.source_width * scale)
        content_height = max(1.0, frame.source_height * scale)
        content_left = (self.output_width - content_width) / 2.0
        content_top = (self.output_height - content_height) / 2.0
        mapping = MappingState(
            mode="game",
            output_width=self.output_width,
            output_height=self.output_height,
            screen_left=frame.target.left,
            screen_top=frame.target.top,
            screen_width=frame.target.width,
            screen_height=frame.target.height,
            content_left=content_left,
            content_top=content_top,
            content_width=content_width,
            content_height=content_height,
        )
        return image, mapping, frame.window_state

    def close(self) -> None:
        self.capture_engine.close()


class DesktopFrameSource(FrameSource):
    def __init__(self, *, monitor: int = 1, max_width: int = 1600) -> None:
        self.monitor = max(0, int(monitor))
        self.max_width = max(640, int(max_width))

    def capture(self) -> tuple[Image.Image, MappingState, str]:
        import mss

        with mss.mss() as screen:
            if self.monitor >= len(screen.monitors):
                raise RuntimeError("MONITOR_NOT_FOUND")
            monitor = screen.monitors[self.monitor]
            shot = screen.grab(monitor)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
        source_width, source_height = image.size
        if source_width > self.max_width:
            ratio = self.max_width / source_width
            output_size = (self.max_width, max(1, int(round(source_height * ratio))))
            image = image.resize(output_size, Image.Resampling.BILINEAR)
        output_width, output_height = image.size
        mapping = MappingState(
            mode="desktop",
            output_width=output_width,
            output_height=output_height,
            screen_left=int(monitor["left"]),
            screen_top=int(monitor["top"]),
            screen_width=int(monitor["width"]),
            screen_height=int(monitor["height"]),
        )
        return image, mapping, "desktop"


class FrameHub:
    """Single latest-frame buffer.

    The producer overwrites the previous frame instead of building a latency
    queue. Slow consumers therefore skip old frames rather than falling behind.
    """

    def __init__(self, source: FrameSource, *, fps: int = 24) -> None:
        self.source = source
        self.fps = max(5, min(60, int(fps)))
        self._condition = threading.Condition()
        self._latest: LatestFrame | None = None
        self._sequence = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error = "starting"
        self._frames_last_second = 0
        self._fps_actual = 0.0
        self._fps_window_started = time.monotonic()

    @property
    def last_error(self) -> str:
        with self._condition:
            return self._last_error

    @property
    def fps_actual(self) -> float:
        with self._condition:
            return self._fps_actual

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="KageLinkRemoteCapture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        try:
            self.source.close()
        except Exception:
            pass

    def _placeholder(self, message: str) -> Image.Image:
        size = (1280, 720)
        image = Image.new("RGB", size, (7, 10, 15))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, size[0], 62), fill=(15, 24, 34))
        draw.text((24, 20), "KageLink Remote", fill=(65, 217, 232))
        draw.text((24, 96), message[:120], fill=(235, 238, 241))
        draw.text((24, 126), "Open/restore the target on the host PC.", fill=(160, 170, 180))
        return image

    def _publish(self, image: Image.Image, mapping: MappingState | None, state: str, capture_ms: float) -> None:
        now = time.monotonic()
        with self._condition:
            self._sequence += 1
            self._latest = LatestFrame(
                sequence=self._sequence,
                captured_at=now,
                image=image,
                mapping=mapping,
                state=state,
                capture_ms=float(capture_ms),
            )
            self._last_error = ""
            self._frames_last_second += 1
            elapsed = now - self._fps_window_started
            if elapsed >= 1.0:
                self._fps_actual = self._frames_last_second / elapsed
                self._frames_last_second = 0
                self._fps_window_started = now
            self._condition.notify_all()

    def _publish_error(self, code: str) -> None:
        now = time.monotonic()
        with self._condition:
            self._last_error = code
            # Publish a fresh status frame only when the visible error changes or
            # there is no frame yet. This avoids creating a hot-loop of identical
            # placeholders while the game is minimized.
            if self._latest is None or self._latest.state != code:
                self._sequence += 1
                self._latest = LatestFrame(
                    sequence=self._sequence,
                    captured_at=now,
                    image=self._placeholder(code.replace("_", " ").title()),
                    mapping=None,
                    state=code,
                    capture_ms=0.0,
                )
                self._condition.notify_all()

    def _worker(self) -> None:
        period = 1.0 / self.fps
        while not self._stop.is_set():
            started = time.perf_counter()
            try:
                image, mapping, state = self.source.capture()
                capture_ms = (time.perf_counter() - started) * 1000.0
                self._publish(image, mapping, state, capture_ms)
            except GameWindowMissing:
                self._publish_error("GAME_NOT_FOUND")
            except GameWindowMinimized:
                self._publish_error("GAME_MINIMIZED")
            except GameCaptureError as exc:
                self._publish_error(str(exc)[:80] or "CAPTURE_ERROR")
            except Exception as exc:
                self._publish_error(type(exc).__name__.upper())
            elapsed = time.perf_counter() - started
            self._stop.wait(max(0.001, period - elapsed))

    def get_latest(self) -> LatestFrame | None:
        with self._condition:
            return self._latest

    def wait_for_new(self, last_sequence: int, *, timeout: float = 1.0) -> LatestFrame | None:
        deadline = time.monotonic() + max(0.05, float(timeout))
        with self._condition:
            while not self._stop.is_set():
                latest = self._latest
                if latest is not None and latest.sequence != last_sequence:
                    return latest
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return latest
                self._condition.wait(timeout=remaining)
        return self._latest

    def map_pointer(self, x: float, y: float) -> tuple[int, int] | None:
        with self._condition:
            latest = self._latest
            mapping = latest.mapping if latest else None
        if mapping is None:
            return None
        return mapping.map_normalized(float(x), float(y))

    def diagnostics(self) -> dict:
        with self._condition:
            latest = self._latest
            return {
                "fps": round(self._fps_actual, 1),
                "state": latest.state if latest else self._last_error,
                "capture_ms": round(latest.capture_ms, 1) if latest else None,
                "frame_age_ms": round((time.monotonic() - latest.captured_at) * 1000.0, 1) if latest else None,
                "sequence": latest.sequence if latest else 0,
            }
