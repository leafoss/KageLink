from __future__ import annotations

import math
from typing import Any

import numpy as np

from .hostility_gate import HostilityState


_INSTALLED = False



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



def _candidate_foot(candidate: Any) -> tuple[float, float] | None:
    foot = getattr(candidate, "foot_point", None)
    if foot is not None:
        return float(foot[0]), float(foot[1])
    bbox = getattr(candidate, "bbox", None)
    if bbox is None:
        return None
    left, top, width, height = bbox
    return float(left + width / 2.0), float(top + height)



def dominant_terrain_component(item: Any) -> bool:
    """Return True for wall/floor fields that cannot represent one body.

    The PR26.14 physical replay transferred the latched identity to components
    measured as 43x64 and 64x23 with changed ratio around 0.66 and blob area
    around 2700. These are cell fields/terrain boundaries, not humanoids.
    """

    from . import runtime_cell_change_authority as cell_module

    _, _, width, height = cell_module._component_bbox(item)
    ratio = float(getattr(item, "true_changed_ratio", 0.0))
    blob = int(getattr(item, "largest_blob_area", 0))
    aspect = float(width) / float(max(1, height))
    return bool(
        (
            ratio >= 0.52
            and blob >= 1700
            and width >= 40
            and height >= 40
        )
        or (
            width >= 48
            and height <= 28
            and aspect >= 1.70
            and ratio >= 0.30
        )
    )



def strict_candidate_matches_cell_change(candidate: Any, item: Any) -> bool:
    """Require real body/component overlap; sharing a 64px cell is insufficient.

    A 64px cell is the comparison unit, not proof that every object inside that
    cell is the same object. The body bbox or its foot must overlap changed
    pixels belonging to the component itself.
    """

    from . import runtime_cell_change_authority as cell_module

    if (
        int(getattr(candidate, "track_id", -1)) < 0
        or not bool(getattr(candidate, "visible", False))
        or not bool(getattr(candidate, "body_like", False))
        or getattr(candidate, "bbox", None) is None
        or dominant_terrain_component(item)
    ):
        return False

    candidate_bbox = tuple(int(value) for value in candidate.bbox)
    component_bbox = cell_module._component_bbox(item)
    _, _, intersection_width, intersection_height = _bbox_intersection(
        candidate_bbox,
        component_bbox,
    )
    intersection = intersection_width * intersection_height
    candidate_area = max(1, candidate_bbox[2] * candidate_bbox[3])
    component_area = max(1, component_bbox[2] * component_bbox[3])
    candidate_overlap = float(intersection) / float(candidate_area)
    component_overlap = float(intersection) / float(component_area)

    foot = _candidate_foot(candidate)
    foot_on_mask = False
    if foot is not None and getattr(item, "mask", None) is not None:
        cell_left, cell_top, cell_width, cell_height = (
            int(value) for value in item.evidence.bbox
        )
        local_x = int(round(foot[0] - cell_left))
        local_y = int(round(foot[1] - cell_top))
        if 0 <= local_x < cell_width and 0 <= local_y < cell_height:
            radius = 4
            x0 = max(0, local_x - radius)
            x1 = min(cell_width, local_x + radius + 1)
            y0 = max(0, local_y - radius)
            y1 = min(cell_height, local_y + radius + 1)
            foot_on_mask = bool(np.any(item.mask[y0:y1, x0:x1] > 0))

    component_foot = cell_module._component_foot(item)
    foot_distance = math.inf if foot is None else math.dist(foot, component_foot)
    close_foot_with_overlap = bool(
        foot_distance <= 18.0
        and intersection > 0
        and candidate_overlap >= 0.08
    )

    return bool(
        candidate_overlap >= 0.18
        or component_overlap >= 0.22
        or foot_on_mask
        or close_foot_with_overlap
    )



def latched_cluster_has_current_body(cluster: Any) -> bool:
    """A visible latched target must have body support in this exact frame."""

    if cluster is None or dominant_cluster_geometry(cluster):
        return False
    return bool(getattr(cluster, "raw_track_ids", ()))



def dominant_cluster_geometry(cluster: Any) -> bool:
    _, _, width, height = (int(value) for value in cluster.bbox)
    ratio = float(getattr(cluster, "true_changed_ratio", 0.0))
    blob = int(getattr(cluster, "largest_blob_area", 0))
    aspect = float(width) / float(max(1, height))
    return bool(
        (
            ratio >= 0.52
            and blob >= 1700
            and width >= 40
            and height >= 40
        )
        or (
            width >= 48
            and height <= 28
            and aspect >= 1.70
            and ratio >= 0.30
        )
    )



def install_visual_target_authority() -> None:
    """Prevent a latched enemy identity from migrating to terrain components."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import runtime_cell_change_authority as cell_module
    from . import runtime_combat_target_memory as continuity_module
    from .occupancy_tracking import PR26OccupancyTracker

    # Same 64px cell is only a search location. It is not body identity.
    cell_module.candidate_matches_cell_change = strict_candidate_matches_cell_change

    original_artifact_reason = cell_module._individual_artifact_reason

    def strict_artifact_reason(item):
        reason = original_artifact_reason(item)
        if reason is not None:
            return reason
        if dominant_terrain_component(item):
            return "CELL_DOMINANT_TERRAIN_FIELD"
        return None

    cell_module._individual_artifact_reason = strict_artifact_reason

    # Clusters may point to cells to search, but may never restore identity.
    continuity_module.cluster_reid_matches = lambda *args, **kwargs: False

    original_association = PR26OccupancyTracker._association

    def body_current_association(self, track, cluster, now):
        memory = getattr(self, "_pr26_round_target_memory", None)
        if memory is not None and int(track.track_id) == int(memory.track_id):
            if not latched_cluster_has_current_body(cluster):
                key = (
                    "RAWLESS_VISUAL_ASSOCIATION_REJECTED",
                    int(cluster.foot_cell.x),
                    int(cluster.foot_cell.y),
                    tuple(int(value) for value in cluster.bbox),
                )
                if getattr(self, "_pr26_last_visual_reject", None) != key:
                    self._pr26_last_visual_reject = key
                    self._emit(
                        f"PR26_LATCHED_TERRAIN_REJECTED id={track.track_id} "
                        f"cell=({cluster.foot_cell.x},{cluster.foot_cell.y}) "
                        f"bbox={cluster.bbox[2]}x{cluster.bbox[3]} "
                        f"ratio={cluster.true_changed_ratio:.3f} "
                        f"blob={cluster.largest_blob_area} "
                        "reason=CURRENT_FRAME_BODY_REQUIRED"
                    )
                return None
        return original_association(self, track, cluster, now)

    PR26OccupancyTracker._association = body_current_association

    original_filter = PR26OccupancyTracker.filter_candidates

    def body_current_filter(self, *args, **kwargs):
        result = tuple(original_filter(self, *args, **kwargs))
        memory = getattr(self, "_pr26_round_target_memory", None)
        if memory is None:
            return result

        authority = str(getattr(self, "_pr26_continuity_authority", "NONE"))
        if authority == "PIXEL_REID":
            track = self._tracks.get(memory.track_id, memory.track)
            track.visible = False
            track.combat_lock = False
            track.hostility_state = HostilityState.HOSTILE_CONFIRMED
            track.reason = (
                "pixel cluster is a search hint only; current body confirmation required"
            )
            self._pr26_continuity_authority = "CONTACT_MEMORY"
            memory.authority = "CONTACT_MEMORY"
            self.last_snapshot = self._snapshot(track)
            self._emit(
                f"PR26_PIXEL_REID_REJECTED id={track.track_id} "
                "reason=CLUSTER_SEARCH_HINT_ONLY"
            )
            return ()

        track = self._tracks.get(memory.track_id, memory.track)
        if result and track.visible and track.combat_lock:
            current_body = bool(track.raw_track_ids) or authority == "CAPSULE_REID"
            if not current_body:
                track.visible = False
                track.combat_lock = False
                track.reason = (
                    "latched identity retained, but current visual is not body-bound"
                )
                self._pr26_continuity_authority = "CONTACT_MEMORY"
                memory.authority = "CONTACT_MEMORY"
                self.last_snapshot = self._snapshot(track)
                self._emit(
                    f"PR26_CURRENT_BODY_GATE_BLOCKED id={track.track_id} "
                    "MOVE=BLOCKED H=BLOCKED reason=NO_CURRENT_BODY"
                )
                return ()
        return result

    PR26OccupancyTracker.filter_candidates = body_current_filter

    _INSTALLED = True
    print(
        "PR26.15 VISUAL TARGET AUTHORITY: a 64px cell is only a comparison/search "
        "location; same-cell alone cannot bind identity; latched targets require a "
        "current raw/Target-Capsule body; pixel clusters cannot perform combat ReID"
    )


__all__ = [
    "dominant_cluster_geometry",
    "dominant_terrain_component",
    "install_visual_target_authority",
    "latched_cluster_has_current_body",
    "strict_candidate_matches_cell_change",
]
