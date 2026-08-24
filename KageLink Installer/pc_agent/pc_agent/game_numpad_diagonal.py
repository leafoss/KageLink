from __future__ import annotations

from typing import Iterable

import win32con
import win32gui

import pc_agent.game_control as base
from pc_agent.game_protocol import normalize_pressed
from pc_agent.game_window import find_exact_game_window, is_valid_game_target
from pc_agent.windows import ensure_game_window_foreground, is_game_window_foreground


_MOVEMENT_KEYS = frozenset({"up", "down", "left", "right"})
_DIAGONAL_KEYS = {
    frozenset({"down", "left"}): "numpad1",
    frozenset({"down", "right"}): "numpad3",
    frozenset({"up", "left"}): "numpad7",
    frozenset({"up", "right"}): "numpad9",
}
_NUMPAD_DEFINITIONS = {
    "numpad1": base.KeyDefinition(win32con.VK_NUMPAD1),
    "numpad3": base.KeyDefinition(win32con.VK_NUMPAD3),
    "numpad7": base.KeyDefinition(win32con.VK_NUMPAD7),
    "numpad9": base.KeyDefinition(win32con.VK_NUMPAD9),
}
_PHYSICAL_KEYS = {**base.KEYS, **_NUMPAD_DEFINITIONS}


def translate_shinobi_directions(pressed: Iterable[str]) -> frozenset[str]:
    """Translate a two-axis joystick diagonal into Shinobi's dedicated numpad key.

    Cardinal movement remains on arrow keys. Action keys are preserved unchanged.
    Opposing/invalid directional chords are left untouched and remain governed by
    the canonical input validation.
    """
    logical = set(normalize_pressed(pressed))
    movement = frozenset(logical.intersection(_MOVEMENT_KEYS))
    diagonal = _DIAGONAL_KEYS.get(movement)
    if diagonal is None:
        return frozenset(logical)
    return frozenset((logical.difference(_MOVEMENT_KEYS)) | {diagonal})


class NumpadDiagonalGameInputController(base.GameInputController):
    """KageLink GAME controller adapted to Shinobi Story's native diagonal keys."""

    def apply_state(self, pressed: Iterable[str]) -> frozenset[str]:
        desired = set(translate_shinobi_directions(pressed))
        with self._lock:
            if not self._active:
                raise base.GameControlError("GAME_CONTROL_INACTIVE")

            hwnd = find_exact_game_window(self.title)
            if hwnd is None or not is_valid_game_target(hwnd, self.title):
                self._release_all_locked()
                self._active = False
                raise base.GameControlError("GAME_NOT_FOUND")
            if win32gui.IsIconic(hwnd):
                self._release_all_locked()
                self._active = False
                raise base.GameControlError("GAME_MINIMIZED")

            self._last_hwnd = hwnd
            if desired.difference(_PHYSICAL_KEYS):
                raise base.GameControlError("INVALID_GAME_KEYS")
            if self._pressed and not is_game_window_foreground(hwnd):
                self._release_all_locked()
                self._active = False
                raise base.GameControlError("FOREGROUND_LOST")

            # Release the previous physical direction before asserting the next one.
            # Example: numpad9 -> numpad3 releases 9 before pressing 3, preventing
            # a transient cardinal or stuck diagonal in BYOND.
            for key in sorted(self._pressed - desired):
                base._send_keyboard(_PHYSICAL_KEYS[key], False)
                self._pressed.discard(key)

            if desired - self._pressed:
                focus = ensure_game_window_foreground(self.title)
                if not focus.ok or not is_game_window_foreground(hwnd):
                    self._release_all_locked()
                    raise base.GameControlError(focus.error or "FOREGROUND_FAILED")

            for key in sorted(desired - self._pressed):
                base._send_keyboard(_PHYSICAL_KEYS[key], True)
                self._pressed.add(key)

            return frozenset(self._pressed)

    def _release_all_locked(self) -> None:
        for key in sorted(self._pressed):
            try:
                definition = _PHYSICAL_KEYS.get(key)
                if definition is not None:
                    base._send_keyboard(definition, False)
            except Exception:
                pass
        self._pressed.clear()


def install_numpad_diagonal_controller(game_runtime) -> None:
    """Install before GAME control is first activated; preserve a live controller if needed."""
    base.GameInputController = NumpadDiagonalGameInputController
    current = getattr(game_runtime, "_control", None)
    if current is None or isinstance(current, NumpadDiagonalGameInputController):
        return

    was_active = bool(getattr(current, "active", False))
    try:
        current.release_all()
    finally:
        replacement = NumpadDiagonalGameInputController(getattr(game_runtime, "title", base.GAME_WINDOW_TITLE))
        if was_active:
            replacement.activate()
        game_runtime._control = replacement


__all__ = [
    "NumpadDiagonalGameInputController",
    "install_numpad_diagonal_controller",
    "translate_shinobi_directions",
]
