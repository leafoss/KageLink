from __future__ import annotations

import math
from typing import Any

import numpy as np

from .domain import ObservationKind


_CAMERA_INSTALLED = False
_ACQUISITION_INSTALLED = False


def camera_static_hold_allowed(
    accepted: tuple[float, float],
    candidate: tuple[float, float],
    response: float,
) -> bool:
    """Low phase response must not blind a camera that is still stationary."""

    values = (*accepted, *candidate, float(response))
    if not all(math.isfinite(float(value)) for value in values):
        return False
    return bool(
        float(response) >= 0.035
        and math.dist(
            (float(accepted[0]), float(accepted[1])),
            (float(candidate[0]), float(candidate[1])),
        ) <= 2.5
    )


def install_static_camera_liveness() -> None:
    """Keep exact baselines alive when raw camera shift remains near accepted.

    PR26.15 treated response=0.144 with raw=(0.1,0.2) as camera failure,
    replaced all 72 exact baselines with an empty dict, and stayed blind for the
    rest of the physical round. Low response now means "hold last transform"
    when the measured displacement itself says the viewport is stationary.
    """

    global _CAMERA_INSTALLED
    if _CAMERA_INSTALLED:
        return

    from . import runtime_target_integrity as integrity_module

    CurrentGate = integrity_module.CameraStabilityGate
    original_evaluate = CurrentGate.evaluate

    def liveness_evaluate(self, dx, dy, response, raw_authoritative):
        candidate = (float(round(dx)), float(round(dy)))
        if camera_static_hold_allowed(self.accepted, candidate, float(response)):
            self.pending = None
            self.pending_votes = 0
            self.initialized = True
            self.reason = "LOW_RESPONSE_STATIC_VIEWPORT_HOLD"
            # Preserve the accepted transform rather than following subpixel
            # noise. The baseline remains usable and offensive authority still
            # depends on a real current body in the changed cell.
            return self.accepted[0], self.accepted[1], float(response), True
        return original_evaluate(self, dx, dy, response, raw_authoritative)

    CurrentGate.evaluate = liveness_evaluate
    _CAMERA_INSTALLED = True
    print(
        "PR26.16 CAMERA LIVENESS: low phase response no longer deletes exact baselines "
        "when measured displacement remains within 2.5px of the accepted viewport"
    )


def _bbox_intersection(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    ax, ay, aw, ah = (int(value) for value in first)
    bx, by, bw, bh = (int(value) for value in second)
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    return left, top, max(0, right - left), max(0, bottom - top)


def _candidate_geometry(candidate: Any) -> bool:
    bbox = getattr(candidate, "bbox", None)
    if bbox is None:
        return False
    _, _, width, height = (int(value) for value in bbox)
    aspect = float(height) / float(max(1, width))
    cells = set(getattr(candidate, "cells_touched", ()))
    kind = getattr(candidate, "kind", None)
    return bool(
        6 <= width <= 58
        and 14 <= height <= 88
        and 0.55 <= aspect <= 6.0
        and len(cells) <= 3
        and kind is not ObservationKind.MULTI_CELL_BLOB
    )


def _candidate_is_player(candidate: Any) -> bool:
    offset = getattr(candidate, "relative_offset_px", None)
    if offset is None:
        return False
    return math.hypot(float(offset[0]), float(offset[1])) <= 12.0


def exact_cell_supports_weak_body(candidate: Any, item: Any) -> bool:
    """Let exact pixel evidence promote a weak raw track, never a cell alone.

    The generic observer may label a freshly spawned or overlapping enemy as
    contaminated before it accumulates two clean observations. A visible raw
    bbox can still become current-body evidence when it physically overlaps the
    changed component from that exact 64px baseline. Sharing the cell without
    pixel overlap remains insufficient.
    """

    from . import runtime_cell_change_authority as cell_module
    from . import runtime_visual_target_authority as visual_module
    from .occupancy_model import DiffSource

    if (
        int(getattr(candidate, "track_id", -1)) < 0
        or not bool(getattr(candidate, "visible", False))
        or not _candidate_geometry(candidate)
        or _candidate_is_player(candidate)
        or getattr(item, "diff_source", None) is not DiffSource.EXACT_CELL_BASELINE
        or visual_module.dominant_terrain_component(item)
        or getattr(item, "mask", None) is None
        or not np.any(item.mask)
    ):
        return False

    candidate_bbox = tuple(int(value) for value in candidate.bbox)
    component_bbox = cell_module._component_bbox(item)
    _, _, iw, ih = _bbox_intersection(candidate_bbox, component_bbox)
    intersection = iw * ih
    candidate_area = max(1, candidate_bbox[2] * candidate_bbox[3])
    component_area = max(1, component_bbox[2] * component_bbox[3])
    candidate_overlap = float(intersection) / float(candidate_area)
    component_overlap = float(intersection) / float(component_area)

    foot = getattr(candidate, "foot_point", None)
    if foot is None:
        foot = (
            float(candidate_bbox[0] + candidate_bbox[2] / 2.0),
            float(candidate_bbox[1] + candidate_bbox[3]),
        )
    cell_left, cell_top, cell_width, cell_height = (
        int(value) for value in item.evidence.bbox
    )
    local_x = int(round(float(foot[0]) - cell_left))
    local_y = int(round(float(foot[1]) - cell_top))
    foot_on_mask = False
    if 0 <= local_x < cell_width and 0 <= local_y < cell_height:
        radius = 5
        x0 = max(0, local_x - radius)
        x1 = min(cell_width, local_x + radius + 1)
        y0 = max(0, local_y - radius)
        y1 = min(cell_height, local_y + radius + 1)
        foot_on_mask = bool(np.any(item.mask[y0:y1, x0:x1] > 0))

    confidence = float(getattr(candidate, "confidence", 0.0))
    motion = float(getattr(candidate, "motion_score", 0.0))
    evidence_strength = bool(
        float(getattr(item, "true_changed_ratio", 0.0)) >= 0.025
        and int(getattr(item, "largest_blob_area", 0)) >= 60
    )
    overlap = bool(
        candidate_overlap >= 0.14
        or component_overlap >= 0.18
        or foot_on_mask
    )
    return bool(
        evidence_strength
        and overlap
        and (confidence >= 0.18 or motion >= 0.40)
    )


def install_exact_cell_acquisition_recovery() -> None:
    """Recover a newly spawned body without relaxing terrain/cluster safety."""

    global _ACQUISITION_INSTALLED
    if _ACQUISITION_INSTALLED:
        return

    from . import runtime_cell_change_authority as cell_module
    from . import runtime_visual_target_authority as visual_module

    strict_match = visual_module.strict_candidate_matches_cell_change

    def current_body_match(candidate, item):
        if strict_match(candidate, item):
            return True
        return exact_cell_supports_weak_body(candidate, item)

    # build_cell_change_components resolves this global at call time.
    cell_module.candidate_matches_cell_change = current_body_match
    visual_module.strict_candidate_matches_cell_change = current_body_match
    _ACQUISITION_INSTALLED = True
    print(
        "PR26.16 EXACT-CELL ACQUISITION: a fresh/overlapping raw track may be promoted "
        "only when its bbox or foot overlaps changed pixels from that cell's exact "
        "baseline; player-center tracks, same-cell-only matches and terrain fields remain blocked"
    )


__all__ = [
    "camera_static_hold_allowed",
    "exact_cell_supports_weak_body",
    "install_exact_cell_acquisition_recovery",
    "install_static_camera_liveness",
]
