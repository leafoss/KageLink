from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class CombatTargetConfig:
    contact_radius: float = 48.0
    local_rebind_radius: float = 96.0
    contact_hold_seconds: float = 2.0
    local_rebind_seconds: float = 1.0
    hard_lost_timeout: float = 3.0
    target_switch_confirm_frames: int = 3
    direction_confirm_frames: int = 3
    horizontal_dead_zone: float = 12.0
    vertical_dead_zone: float = 12.0
    distance_weight: float = 0.45
    size_weight: float = 0.25
    appearance_weight: float = 0.15
    movement_weight: float = 0.15
    minimum_rebind_score: float = 0.48
    camera_flow_compensation: bool = True
    effect_horizontal_aspect: float = 5.0
    effect_horizontal_min_width: float = 52.0
    effect_vertical_aspect: float = 7.0
    effect_vertical_min_height: float = 110.0
    effect_border_margin: float = 5.0
    effect_border_long_ratio: float = 0.24
    structured_logging_enabled: bool = True

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object] | None) -> "CombatTargetConfig":
        values = dict(mapping or {})
        defaults = cls()

        def number(name: str, default: float, low: float, high: float) -> float:
            try:
                value = float(values.get(name, default))
            except (TypeError, ValueError):
                value = default
            return max(low, min(high, value))

        def integer(name: str, default: int, low: int, high: int) -> int:
            try:
                value = int(values.get(name, default))
            except (TypeError, ValueError):
                value = default
            return max(low, min(high, value))

        weights = {
            "distance_weight": number("distance_weight", defaults.distance_weight, 0.0, 1.0),
            "size_weight": number("size_weight", defaults.size_weight, 0.0, 1.0),
            "appearance_weight": number("appearance_weight", defaults.appearance_weight, 0.0, 1.0),
            "movement_weight": number("movement_weight", defaults.movement_weight, 0.0, 1.0),
        }
        total = sum(weights.values()) or 1.0
        weights = {name: value / total for name, value in weights.items()}

        return cls(
            contact_radius=number("contact_radius", defaults.contact_radius, 24.0, 128.0),
            local_rebind_radius=number("local_rebind_radius", defaults.local_rebind_radius, 48.0, 260.0),
            contact_hold_seconds=number("contact_hold_seconds", defaults.contact_hold_seconds, 0.35, 6.0),
            local_rebind_seconds=number("local_rebind_seconds", defaults.local_rebind_seconds, 0.50, 5.0),
            hard_lost_timeout=number("hard_lost_timeout", defaults.hard_lost_timeout, 1.25, 8.0),
            target_switch_confirm_frames=integer(
                "target_switch_confirm_frames", defaults.target_switch_confirm_frames, 2, 8
            ),
            direction_confirm_frames=integer(
                "direction_confirm_frames", defaults.direction_confirm_frames, 2, 8
            ),
            horizontal_dead_zone=number(
                "horizontal_dead_zone", defaults.horizontal_dead_zone, 4.0, 40.0
            ),
            vertical_dead_zone=number("vertical_dead_zone", defaults.vertical_dead_zone, 4.0, 40.0),
            minimum_rebind_score=number(
                "minimum_rebind_score", defaults.minimum_rebind_score, 0.20, 0.90
            ),
            camera_flow_compensation=bool(
                values.get("camera_flow_compensation", defaults.camera_flow_compensation)
            ),
            effect_horizontal_aspect=number(
                "effect_horizontal_aspect", defaults.effect_horizontal_aspect, 2.5, 14.0
            ),
            effect_horizontal_min_width=number(
                "effect_horizontal_min_width", defaults.effect_horizontal_min_width, 24.0, 240.0
            ),
            effect_vertical_aspect=number(
                "effect_vertical_aspect", defaults.effect_vertical_aspect, 3.5, 16.0
            ),
            effect_vertical_min_height=number(
                "effect_vertical_min_height", defaults.effect_vertical_min_height, 48.0, 280.0
            ),
            effect_border_margin=number(
                "effect_border_margin", defaults.effect_border_margin, 1.0, 24.0
            ),
            effect_border_long_ratio=number(
                "effect_border_long_ratio", defaults.effect_border_long_ratio, 0.10, 0.75
            ),
            structured_logging_enabled=bool(
                values.get("structured_logging_enabled", defaults.structured_logging_enabled)
            ),
            **weights,
        )


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "kage_pilot_dojo.json"


def load_combat_target_config(path: str | Path | None = None) -> CombatTargetConfig:
    source = Path(path) if path is not None else _default_config_path()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        payload = {}
    section = payload.get("combat_target", {}) if isinstance(payload, dict) else {}
    return CombatTargetConfig.from_mapping(section if isinstance(section, dict) else {})


__all__ = ["CombatTargetConfig", "load_combat_target_config"]
