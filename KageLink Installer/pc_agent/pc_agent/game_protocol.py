from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

GAME_WINDOW_TITLE = "Shinobi Story Online"
MOVEMENT_KEYS = frozenset({"up", "down", "left", "right"})
ACTION_KEYS = frozenset(
    {
        *(chr(code) for code in range(ord("a"), ord("z") + 1)),
        *(str(number) for number in range(10)),
        "space",
        "enter",
        "escape",
        "tab",
        "shift",
        "ctrl",
        "alt",
        "backspace",
        "insert",
        "delete",
        "home",
        "end",
        "pageup",
        "pagedown",
        *(f"f{number}" for number in range(1, 13)),
    }
)
ALLOWED_KEYS = frozenset(MOVEMENT_KEYS | ACTION_KEYS)
VIEW_MODES = frozenset({"full", "zoom"})


@dataclass(frozen=True, slots=True)
class GameControlMessage:
    kind: str
    active: bool | None = None
    pressed: frozenset[str] = frozenset()
    timestamp: float | None = None


def normalize_pressed(values: Iterable[Any]) -> frozenset[str]:
    normalized = {str(value).strip().lower() for value in values}
    invalid = normalized.difference(ALLOWED_KEYS)
    if invalid:
        raise ValueError(f"INVALID_GAME_KEYS: {', '.join(sorted(invalid))}")
    return frozenset(normalized)


def parse_control_message(payload: Any) -> GameControlMessage:
    if not isinstance(payload, dict):
        raise ValueError("INVALID_GAME_COMMAND")

    kind = str(payload.get("type", "")).strip().lower()
    if kind == "active":
        return GameControlMessage(kind=kind, active=bool(payload.get("value")))
    if kind == "focus_click":
        return GameControlMessage(kind=kind)
    if kind in {"keys", "heartbeat"}:
        raw_pressed = payload.get("pressed", [])
        if not isinstance(raw_pressed, list):
            raise ValueError("INVALID_PRESSED_KEYS")
        timestamp_value = payload.get("timestamp")
        try:
            timestamp = float(timestamp_value) if timestamp_value is not None else None
        except (TypeError, ValueError):
            timestamp = None
        return GameControlMessage(
            kind=kind,
            pressed=normalize_pressed(raw_pressed),
            timestamp=timestamp,
        )
    raise ValueError("UNSUPPORTED_GAME_COMMAND")


def normalize_view_mode(value: str | None) -> str:
    mode = str(value or "full").strip().lower()
    return mode if mode in VIEW_MODES else "full"
