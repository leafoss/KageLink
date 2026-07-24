from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

STATS_WINDOW_TITLE = "Status | Inventory"
STATS_WINDOW_CLASS = "#32770"

# Center of the Status/Inventory icon marked in the supplied 961x833 game
# capture. Normalized coordinates keep the click tied to the current game
# playfield instead of an absolute desktop position.
STATS_OPEN_X = 145.0 / 961.0
STATS_OPEN_Y = 623.0 / 833.0
CLICK_BUTTONS = frozenset({"left", "right"})


@dataclass(frozen=True, slots=True)
class StatsControlMessage:
    kind: str
    active: bool | None = None
    x: float | None = None
    y: float | None = None
    button: str | None = None
    window_id: int | None = None
    timestamp: float | None = None


def normalize_coordinate(value: Any, name: str) -> float:
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"INVALID_STATS_{name.upper()}") from error
    if not math.isfinite(coordinate) or not 0.0 <= coordinate <= 1.0:
        raise ValueError(f"INVALID_STATS_{name.upper()}")
    return coordinate




def normalized_client_point(
    left: int,
    top: int,
    width: int,
    height: int,
    x: Any,
    y: Any,
) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise ValueError("INVALID_STATS_CLIENT_SIZE")
    normalized_x = normalize_coordinate(x, "x")
    normalized_y = normalize_coordinate(y, "y")
    client_x = min(width - 1, max(0, round(normalized_x * (width - 1))))
    client_y = min(height - 1, max(0, round(normalized_y * (height - 1))))
    return int(left + client_x), int(top + client_y)

def parse_stats_control_message(payload: Any) -> StatsControlMessage:
    if not isinstance(payload, dict):
        raise ValueError("INVALID_STATS_COMMAND")

    kind = str(payload.get("type", "")).strip().lower()
    if kind == "active":
        return StatsControlMessage(kind=kind, active=bool(payload.get("value")))
    if kind == "open_stats":
        return StatsControlMessage(kind=kind)
    if kind == "click":
        button = str(payload.get("button", "")).strip().lower()
        if button not in CLICK_BUTTONS:
            raise ValueError("INVALID_STATS_MOUSE_BUTTON")
        try:
            window_id = int(payload.get("window_id"))
        except (TypeError, ValueError) as error:
            raise ValueError("INVALID_STATS_WINDOW_ID") from error
        if window_id <= 0:
            raise ValueError("INVALID_STATS_WINDOW_ID")
        return StatsControlMessage(
            kind=kind,
            x=normalize_coordinate(payload.get("x"), "x"),
            y=normalize_coordinate(payload.get("y"), "y"),
            button=button,
            window_id=window_id,
        )
    if kind == "heartbeat":
        timestamp_value = payload.get("timestamp")
        try:
            timestamp = float(timestamp_value) if timestamp_value is not None else None
        except (TypeError, ValueError):
            timestamp = None
        return StatsControlMessage(kind=kind, timestamp=timestamp)
    raise ValueError("UNSUPPORTED_STATS_COMMAND")
