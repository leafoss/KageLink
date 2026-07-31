from __future__ import annotations

import math
from typing import Any

from .combat_target_config_v351 import CombatTargetConfig


def _candidate_bbox(candidate: Any) -> tuple[int, int, int, int]:
    value = getattr(candidate, "bbox", (0, 0, 0, 0))
    return tuple(int(round(float(item))) for item in value)


def effect_rejection_reason(
    candidate: Any,
    *,
    frame_shape: tuple[int, int] | None,
    flow: Any,
    player_center: tuple[float, float],
    config: CombatTargetConfig,
) -> str | None:
    x, y, width, height = _candidate_bbox(candidate)
    width_f = max(1.0, float(width))
    height_f = max(1.0, float(height))
    distance_to_player = math.dist(
        (float(x) + width_f / 2.0, float(y) + height_f / 2.0),
        player_center,
    )
    protected_contact = distance_to_player <= config.contact_radius * 1.35
    horizontal_aspect = width_f / height_f
    vertical_aspect = height_f / width_f
    if (
        horizontal_aspect >= config.effect_horizontal_aspect
        and width_f >= config.effect_horizontal_min_width
    ):
        return "TOO_HORIZONTAL"
    if (
        vertical_aspect >= config.effect_vertical_aspect
        and height_f >= config.effect_vertical_min_height
    ):
        return "TOO_VERTICAL"
    if frame_shape is not None and not protected_contact:
        frame_height, frame_width = frame_shape
        margin = config.effect_border_margin
        touches_border = (
            x <= margin
            or y <= margin
            or x + width >= frame_width - margin
            or y + height >= frame_height - margin
        )
        long_ratio = max(width_f / max(1.0, frame_width), height_f / max(1.0, frame_height))
        if touches_border and long_ratio >= config.effect_border_long_ratio:
            return "MAP_BORDER"
        if y + height >= frame_height - margin and height_f <= 24.0 and width_f >= 40.0:
            return "HUD_REGION"
        flow_magnitude = math.hypot(
            float(getattr(flow, "dx", 0.0) or 0.0),
            float(getattr(flow, "dy", 0.0) or 0.0),
        )
        if flow_magnitude >= 4.0 and width_f / max(1.0, frame_width) >= 0.30:
            return "CAMERA_FLOW"
    return None


__all__ = ["effect_rejection_reason"]
