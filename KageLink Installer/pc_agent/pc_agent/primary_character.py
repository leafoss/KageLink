from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pc_agent.history import HistoryStore


PRIMARY_CHARACTER_STATE_KEY = "primary_character"
PRIMARY_CHARACTER_HISTORY_STATE_KEY = "primary_character_history"
MAX_CHARACTER_NAME_LENGTH = 160


def normalize_character_name(value: Any) -> str:
    name = str(value or "").strip()
    if "\r" in name or "\n" in name:
        raise ValueError("INVALID_PRIMARY_CHARACTER")
    if len(name) > MAX_CHARACTER_NAME_LENGTH:
        raise ValueError("PRIMARY_CHARACTER_TOO_LONG")
    return name


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_character_history(history: HistoryStore) -> list[dict[str, str]]:
    raw = history.get_runtime_state(PRIMARY_CHARACTER_HISTORY_STATE_KEY, "[]")
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(values, list):
        return []

    result: list[dict[str, str]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = normalize_character_name(item.get("name", ""))
        changed_at = _parse_timestamp(item.get("changed_at"))
        if changed_at is None:
            continue
        result.append(
            {
                "name": name,
                "changed_at": changed_at.isoformat(),
            }
        )
    result.sort(key=lambda item: item["changed_at"])
    return result


def get_primary_character(history: HistoryStore) -> str:
    return normalize_character_name(
        history.get_runtime_state(PRIMARY_CHARACTER_STATE_KEY, "")
    )


def saved_characters(history: HistoryStore) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in reversed(load_character_history(history)):
        name = item["name"]
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    current = get_primary_character(history)
    if current and current not in seen:
        result.insert(0, current)
    return result


def set_primary_character(
    history: HistoryStore,
    value: Any,
    *,
    changed_at: datetime | None = None,
) -> dict[str, Any]:
    name = normalize_character_name(value)
    current = get_primary_character(history)
    if current != name:
        timestamp = changed_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp = timestamp.astimezone(timezone.utc)
        events = load_character_history(history)
        events.append({"name": name, "changed_at": timestamp.isoformat()})
        history.set_runtime_state(
            PRIMARY_CHARACTER_HISTORY_STATE_KEY,
            json.dumps(events, ensure_ascii=False, separators=(",", ":")),
        )
        history.set_runtime_state(PRIMARY_CHARACTER_STATE_KEY, name)

    return {
        "primary_character": name,
        "saved_characters": saved_characters(history),
    }


def resolve_primary_character(history: HistoryStore, at_timestamp: Any) -> str:
    target = _parse_timestamp(at_timestamp)
    if target is None:
        return get_primary_character(history)

    selected: str | None = None
    for item in load_character_history(history):
        changed_at = _parse_timestamp(item["changed_at"])
        if changed_at is None or changed_at > target:
            break
        selected = item["name"]
    if selected is not None:
        return selected
    return get_primary_character(history)
