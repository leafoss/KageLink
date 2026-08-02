from __future__ import annotations

from collections.abc import Callable
from typing import Any


class GlobalMovementKeyListener:
    """Passive global listener for movement intent.

    It never sends or suppresses input. Repeated key-down events are ignored until
    the matching key-up so one physical tap produces one logical mapping attempt.
    """

    def __init__(self, on_direction: Callable[[str], None]) -> None:
        self.on_direction = on_direction
        self._listener: Any | None = None
        self._pressed: set[str] = set()

    def start(self) -> None:
        if self._listener is not None:
            return
        try:
            from pynput import keyboard
        except ImportError as exc:
            raise RuntimeError("Missing dependency 'pynput'. Run setup_navigation.ps1 again.") from exc

        def on_press(key: Any) -> None:
            direction = self._normalize(key, keyboard)
            if direction is None or direction in self._pressed:
                return
            self._pressed.add(direction)
            self.on_direction(direction)

        def on_release(key: Any) -> None:
            direction = self._normalize(key, keyboard)
            if direction is not None:
                self._pressed.discard(direction)

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        self._pressed.clear()
        if listener is not None:
            listener.stop()

    @staticmethod
    def _normalize(key: Any, keyboard: Any) -> str | None:
        special = {
            keyboard.Key.left: "left",
            keyboard.Key.right: "right",
            keyboard.Key.up: "up",
            keyboard.Key.down: "down",
        }
        if key in special:
            return special[key]
        char = getattr(key, "char", None)
        if not isinstance(char, str):
            return None
        return {
            "a": "left",
            "d": "right",
            "w": "up",
            "s": "down",
        }.get(char.casefold())
