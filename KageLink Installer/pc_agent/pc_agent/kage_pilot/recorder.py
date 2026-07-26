from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Protocol, Iterable, Any

from .dataset import SessionWriter


@dataclass(frozen=True, slots=True)
class InputSnapshot:
    keys: tuple[str, ...] = ()
    mouse_buttons: tuple[str, ...] = ()
    mouse_x: float | None = None
    mouse_y: float | None = None


class FrameSource(Protocol):
    def capture(self) -> Any: ...


class InputSource(Protocol):
    def snapshot(self, target: Any | None = None) -> InputSnapshot: ...


class Recorder:
    def __init__(
        self,
        frame_source: FrameSource,
        input_source: InputSource,
        *,
        fps: float = 10.0,
        time_fn=time.time,
        sleep_fn=time.sleep,
    ) -> None:
        self.frame_source = frame_source
        self.input_source = input_source
        self.fps = max(1.0, min(30.0, float(fps)))
        self.time_fn = time_fn
        self.sleep_fn = sleep_fn

    def record(
        self,
        writer: SessionWriter,
        *,
        stop_event: threading.Event | None = None,
        max_samples: int | None = None,
        max_seconds: float | None = None,
    ) -> int:
        stop = stop_event or threading.Event()
        interval = 1.0 / self.fps
        started = self.time_fn()
        count = 0
        deadline = started
        while not stop.is_set():
            now = self.time_fn()
            if max_seconds is not None and now - started >= float(max_seconds):
                break
            frame = self.frame_source.capture()
            target = getattr(frame, "target", None)
            snapshot = self.input_source.snapshot(target)
            writer.append(
                bytes(frame.jpeg),
                timestamp=now,
                keys=snapshot.keys,
                mouse_buttons=snapshot.mouse_buttons,
                mouse_x=snapshot.mouse_x,
                mouse_y=snapshot.mouse_y,
            )
            count += 1
            if max_samples is not None and count >= int(max_samples):
                break
            deadline += interval
            self.sleep_fn(max(0.0, deadline - self.time_fn()))
        return count


class WindowsGameFrameSource:
    def __init__(self, *, output_size: tuple[int, int] = (960, 540), jpeg_quality: int = 70) -> None:
        from pc_agent.game_capture import GameCapture

        self.capture_engine = GameCapture(output_size=output_size, jpeg_quality=jpeg_quality)

    def capture(self):
        return self.capture_engine.capture("full")

    def close(self) -> None:
        self.capture_engine.close()


class WindowsAsyncInputSource:
    """Polls physical keyboard/mouse state without adding a new dependency."""

    def __init__(self, *, excluded_keys: Iterable[str] = ()) -> None:
        import ctypes
        from ctypes import wintypes
        from pc_agent.game_control import KEYS

        self._ctypes = ctypes
        excluded = set(excluded_keys)
        self._keys = {name: definition.vk for name, definition in KEYS.items() if name not in excluded}
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.GetAsyncKeyState.argtypes = (wintypes.INT,)
        self._user32.GetAsyncKeyState.restype = wintypes.SHORT
        self._user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
        self._user32.GetCursorPos.restype = wintypes.BOOL
        self._point_type = wintypes.POINT

    def key_down(self, name: str) -> bool:
        from pc_agent.game_control import KEYS

        definition = KEYS.get(str(name).strip().lower())
        return False if definition is None else bool(self._user32.GetAsyncKeyState(definition.vk) & 0x8000)

    def snapshot(self, target=None) -> InputSnapshot:
        keys = tuple(sorted(name for name, vk in self._keys.items() if self._user32.GetAsyncKeyState(vk) & 0x8000))
        mouse_buttons = tuple(
            name
            for name, vk in (("left", 0x01), ("right", 0x02), ("middle", 0x04))
            if self._user32.GetAsyncKeyState(vk) & 0x8000
        )
        mouse_x = mouse_y = None
        if target is not None:
            point = self._point_type()
            if self._user32.GetCursorPos(self._ctypes.byref(point)):
                left = float(getattr(target, "left", 0))
                top = float(getattr(target, "top", 0))
                width = float(getattr(target, "width", 0))
                height = float(getattr(target, "height", 0))
                if width > 1 and height > 1 and left <= point.x < left + width and top <= point.y < top + height:
                    mouse_x = min(1.0, max(0.0, (point.x - left) / (width - 1)))
                    mouse_y = min(1.0, max(0.0, (point.y - top) / (height - 1)))
        return InputSnapshot(keys=keys, mouse_buttons=mouse_buttons, mouse_x=mouse_x, mouse_y=mouse_y)
