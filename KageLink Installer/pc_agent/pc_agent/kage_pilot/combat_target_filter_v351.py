from __future__ import annotations

import math
from typing import Any

from .combat_target_config_v351 import CombatTargetConfig


def candidate_bbox(candidate: Any) -> tuple[int, int, int, int]:
    value = getattr(candidate, "bbox", (0, 0, 0, 0))
    return tuple(int(round(float(item))) for item in value)


def _intersection_over_union(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = max(1.0, aw * ah + bw * bh - intersection)
    return intersection / union


def combat_body_rejection_reason(
    candidate: Any,
    *,
    context_state: str,
    grid_distance: int | None,
    player_center: tuple[float, float],
    player_box_size: tuple[float, float],
    tile_size: float,
    frame_shape: tuple[int, int] | None = None,
    for_acquire: bool = False,
) -> str | None:
    """Return why a contour must not own combat movement or identity.

    Motion is proposal evidence only. A candidate must also have a plausible
    body-sized vertical silhouette in the authoritative RAW 32/64 grid. This gate
    deliberately rejects floor patches and short attack fragments even when their
    movement score is high.
    """

    state = str(context_state or "").upper()
    if state != "VISIBLE":
        return "BODY_NOT_VISIBLE"

    x, y, width, height = candidate_bbox(candidate)
    width_f = max(1.0, float(width))
    height_f = max(1.0, float(height))
    tile = max(16.0, float(tile_size))
    horizontal_aspect = width_f / height_f
    vertical_aspect = height_f / width_f

    # A clean character body occupies a meaningful vertical fraction of one RAW
    # cell. The historical 12/14-pixel minimum admitted shadows and ground texture.
    minimum_width = max(6.0, tile * 0.16)
    minimum_height = max(16.0, tile * 0.50)
    if width_f < minimum_width:
        return "BODY_TOO_NARROW"
    if height_f < minimum_height:
        return "BODY_TOO_SHORT"

    if width_f > tile * 1.10:
        return "BODY_TOO_WIDE"
    if height_f > tile * 1.35:
        return "BODY_TOO_TALL"

    # Wide, low silhouettes are floor/effect evidence. Transitional combat frames
    # may be ignored temporarily; target memory provides the grace period.
    if horizontal_aspect > 1.55:
        return "BODY_FLOOR_OR_HORIZONTAL_EFFECT"
    if vertical_aspect > 3.00:
        return "BODY_VERTICAL_EFFECT"
    if width_f * height_f > tile * tile * 1.20:
        return "BODY_AREA_TOO_LARGE"

    shape_score = getattr(candidate, "shape_score", None)
    if shape_score is not None:
        try:
            minimum_shape = 0.42 if for_acquire else 0.32
            if float(shape_score) < minimum_shape:
                return "BODY_SHAPE_WEAK"
        except (TypeError, ValueError):
            return "BODY_SHAPE_INVALID"

    edge_density = getattr(candidate, "edge_density", None)
    if edge_density is not None:
        try:
            minimum_edges = 0.025 if for_acquire else 0.018
            if float(edge_density) < minimum_edges:
                return "BODY_EDGE_STRUCTURE_WEAK"
        except (TypeError, ValueError):
            return "BODY_EDGE_STRUCTURE_INVALID"

    contour_area = getattr(candidate, "contour_area", None)
    if contour_area is not None:
        try:
            fill = float(contour_area) / max(1.0, width_f * height_f)
            if fill < 0.14:
                return "BODY_CONTOUR_TOO_SPARSE"
            if fill > 0.94:
                return "BODY_CONTOUR_TOO_SOLID"
        except (TypeError, ValueError):
            return "BODY_CONTOUR_INVALID"

    distance = None if grid_distance is None else int(grid_distance)
    if for_acquire and distance == 0:
        return "BODY_SELF_CELL"

    if for_acquire and distance is not None and distance <= 1:
        player_width = max(8.0, float(player_box_size[0]))
        player_height = max(12.0, float(player_box_size[1]))
        player_box = (
            float(player_center[0]) - player_width * 0.50,
            float(player_center[1]) - player_height * 0.50,
            player_width,
            player_height,
        )
        candidate_box = (float(x), float(y), width_f, height_f)
        if _intersection_over_union(candidate_box, player_box) >= 0.62:
            return "BODY_PLAYER_OVERLAP"

    if frame_shape is not None:
        frame_height, frame_width = frame_shape
        margin = max(3.0, tile * 0.08)
        touches_border = (
            x <= margin
            or y <= margin
            or x + width >= frame_width - margin
            or y + height >= frame_height - margin
        )
        if touches_border and (
            width_f >= tile * 0.70 or height_f >= tile * 0.90
        ):
            return "BODY_MAP_BORDER"
    return None


def effect_rejection_reason(
    candidate: Any,
    *,
    frame_shape: tuple[int, int] | None,
    flow: Any,
    player_center: tuple[float, float],
    config: CombatTargetConfig,
) -> str | None:
    x, y, width, height = candidate_bbox(candidate)
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
    if frame_shape is not None:
        frame_height, frame_width = frame_shape
        margin = config.effect_border_margin
        touches_border = (
            x <= margin
            or y <= margin
            or x + width >= frame_width - margin
            or y + height >= frame_height - margin
        )
        long_ratio = max(width_f / max(1.0, frame_width), height_f / max(1.0, frame_height))
        # Contact proximity no longer grants immunity to a large border strip. The
        # failed physical round showed a map/effect blob becoming authoritative only
        # because it crossed the player circle.
        if touches_border and long_ratio >= config.effect_border_long_ratio:
            return "MAP_BORDER"
        if y + height >= frame_height - margin and height_f <= 24.0 and width_f >= 40.0:
            return "HUD_REGION"
        flow_magnitude = math.hypot(
            float(getattr(flow, "dx", 0.0) or 0.0),
            float(getattr(flow, "dy", 0.0) or 0.0),
        )
        if (
            not protected_contact
            and flow_magnitude >= 4.0
            and width_f / max(1.0, frame_width) >= 0.30
        ):
            return "CAMERA_FLOW"
    return None


__all__ = [
    "candidate_bbox",
    "combat_body_rejection_reason",
    "effect_rejection_reason",
]
