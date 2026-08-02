from __future__ import annotations

import math
from typing import Any, Iterable

import cv2
import numpy as np

from .domain import CandidateObservation, GridCell
from .hostility_gate import EntityState, HostilityState
from .occupancy_model import (
    CellOccupancy,
    DiffSource,
    OccupancyCluster,
    OccupancyState,
)


_INSTALLED = False


def player_capsule_mask(
    shape: tuple[int, int],
    *,
    cell_left: int,
    cell_top: int,
    player_rect: tuple[int, int, int, int],
) -> np.ndarray:
    """Return a narrow player-core capsule in cell-local coordinates.

    The old rectangular exclusion erased both sprites when the enemy approached
    from the left, right or above. This capsule removes only the stable center of
    the player while leaving lateral and upper overlap pixels available to the
    per-cell difference detector.
    """

    height, width = int(shape[0]), int(shape[1])
    result = np.zeros((height, width), dtype=np.uint8)
    player_left, player_top, player_width, player_height = (
        int(value) for value in player_rect
    )
    center_x = player_left + player_width / 2.0 - float(cell_left)
    center_y = player_top + player_height / 2.0 - float(cell_top)
    core_width = max(8, min(16, player_width - 4))
    core_height = max(18, min(34, player_height - 6))
    axes = (max(3, core_width // 2), max(7, core_height // 2))
    cv2.ellipse(
        result,
        (int(round(center_x)), int(round(center_y))),
        axes,
        0.0,
        0.0,
        360.0,
        255,
        -1,
    )
    return result


def _component_bbox(item: CellOccupancy) -> tuple[int, int, int, int]:
    cell_left, cell_top, cell_width, cell_height = (
        int(value) for value in item.evidence.bbox
    )
    if item.blob_bbox is None:
        return cell_left, cell_top, cell_width, cell_height
    left, top, width, height = (int(value) for value in item.blob_bbox)
    return cell_left + left, cell_top + top, width, height


def _component_foot(item: CellOccupancy) -> tuple[float, float]:
    left, top, width, height = _component_bbox(item)
    if item.mask is None or not np.any(item.mask):
        return float(left + width / 2.0), float(top + height)
    ys, xs = np.where(item.mask > 0)
    bottom = int(ys.max())
    near_bottom = xs[ys >= bottom - 2]
    x_value = int(np.median(near_bottom)) if near_bottom.size else int(np.median(xs))
    cell_left, cell_top, _, _ = (int(value) for value in item.evidence.bbox)
    return float(cell_left + x_value), float(cell_top + bottom)


def _bbox_iou(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> float:
    ax, ay, aw, ah = (int(value) for value in first)
    bx, by, bw, bh = (int(value) for value in second)
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    intersection = max(0, right - left) * max(0, bottom - top)
    if intersection <= 0:
        return 0.0
    union = max(1, aw * ah + bw * bh - intersection)
    return float(intersection) / float(union)


def _candidate_foot(candidate: CandidateObservation) -> tuple[float, float] | None:
    if candidate.foot_point is not None:
        return float(candidate.foot_point[0]), float(candidate.foot_point[1])
    if candidate.bbox is None:
        return None
    left, top, width, height = candidate.bbox
    return float(left + width / 2.0), float(top + height)


def candidate_matches_cell_change(
    candidate: CandidateObservation,
    item: CellOccupancy,
) -> bool:
    """Bind a raw/Target-Capsule body to one changed 64px cell component."""

    if (
        candidate.track_id < 0
        or not candidate.visible
        or not candidate.body_like
        or candidate.bbox is None
    ):
        return False
    component_bbox = _component_bbox(item)
    iou = _bbox_iou(candidate.bbox, component_bbox)
    foot = _candidate_foot(candidate)
    component_foot = _component_foot(item)
    foot_distance = math.inf if foot is None else math.dist(foot, component_foot)
    anchor_matches = candidate.anchor_cell == item.cell or item.cell in candidate.cells_touched
    return bool(iou >= 0.08 or foot_distance <= 30.0 or anchor_matches)


def _individual_artifact_reason(item: CellOccupancy) -> str | None:
    _, _, width, height = _component_bbox(item)
    aspect = float(width) / float(max(1, height))
    if (
        item.true_changed_ratio >= 0.85
        and item.largest_blob_area >= 2200
        and width >= 56
        and height >= 56
    ):
        return "CELL_SATURATED_FIELD"
    if height <= 20 and width >= 42 and aspect >= 1.8:
        return "CELL_HORIZONTAL_STRIP"
    if width <= 6 and height >= 52:
        return "CELL_VERTICAL_EDGE_STRIP"
    return None


def build_cell_change_components(
    cells: dict[GridCell, CellOccupancy],
    candidates: Iterable[CandidateObservation],
    *,
    weak_ratio: float = 0.04,
    blob_area_min: int = 180,
) -> tuple[OccupancyCluster, ...]:
    """Create one authority component per changed 64x64 cell.

    Adjacent cells are deliberately never merged here. A search cluster may
    direct attention to multiple cells, but every pixel ratio, mask, bbox and
    body association remains owned by the original cell.
    """

    current_candidates = tuple(candidates)
    result: list[OccupancyCluster] = []
    local_id = 1
    for cell in sorted(cells, key=lambda value: (value.y, value.x)):
        item = cells[cell]
        if (
            item.diff_source is not DiffSource.EXACT_CELL_BASELINE
            or item.mask is None
            or not np.any(item.mask)
            or item.state is OccupancyState.EMPTY
            or _individual_artifact_reason(item) is not None
        ):
            continue

        provisional = OccupancyCluster(
            local_id=local_id,
            cells=frozenset({cell}),
            bbox=_component_bbox(item),
            foot_point=_component_foot(item),
            foot_cell=cell,
            occupancy_score=float(item.occupancy_score),
            danger_prior=float(item.danger_prior),
            true_changed_ratio=float(item.true_changed_ratio),
            largest_blob_area=int(item.largest_blob_area),
            raw_track_ids=frozenset(),
            cell_observations=(item,),
            mask_contact_edges=0,
            authoritative_cells=1,
        )
        matched = frozenset(
            candidate.track_id
            for candidate in current_candidates
            if candidate_matches_cell_change(candidate, item)
        )

        occupied = item.state is OccupancyState.OCCUPIED
        fragmented_body = bool(
            matched
            and item.state is OccupancyState.WEAK
            and float(item.true_changed_ratio) >= max(0.025, float(weak_ratio) * 0.60)
            and int(item.largest_blob_area) >= max(60, int(blob_area_min) // 3)
            and int(item.blob_width) >= 5
            and int(item.blob_height) >= 8
        )
        if not occupied and not fragmented_body:
            continue

        provisional.raw_track_ids = matched
        result.append(provisional)
        local_id += 1
    return tuple(result)


def _candidate_quality(candidate: CandidateObservation) -> float:
    return (
        float(candidate.identity_score) * 1.6
        + float(candidate.appearance_score) * 1.2
        + float(candidate.position_score) * 0.8
        + float(candidate.confidence) * 0.5
        - float(candidate.background_probability) * 1.5
    )


def install_cell_change_authority() -> None:
    """Make 64x64 cell changes authoritative and clusters search-only."""

    global _INSTALLED
    if _INSTALLED:
        return

    from .occupancy_tracking import PR26OccupancyTracker
    from .pixel_occupancy import PixelOccupancyMap

    original_observe = PixelOccupancyMap.observe

    def cell_context_observe(self, *, candidates, state, **kwargs):
        self._pr26_cell_candidates = tuple(candidates)
        self._pr26_player_center = (
            float(state.player_center[0]),
            float(state.player_center[1]),
        )
        return original_observe(
            self,
            candidates=candidates,
            state=state,
            **kwargs,
        )

    PixelOccupancyMap.observe = cell_context_observe

    def capsule_player_mask(self, mask, item, player_rect):
        if mask is None or player_rect is None:
            return mask, 0
        cell_left, cell_top, _, _ = (int(value) for value in item.bbox)
        capsule = player_capsule_mask(
            mask.shape[:2],
            cell_left=cell_left,
            cell_top=cell_top,
            player_rect=player_rect,
        )
        result = mask.copy()
        selected = capsule > 0
        removed = int(np.count_nonzero(result[selected]))
        result[selected] = 0
        return result, removed

    PixelOccupancyMap._mask_player = capsule_player_mask

    original_clusters = PixelOccupancyMap.clusters

    def search_cluster_then_cell_components(self, cells, candidates):
        search_clusters = tuple(original_clusters(self, cells, candidates))
        self.last_search_clusters = search_clusters
        self._pr26_candidate_by_id = {
            candidate.track_id: candidate
            for candidate in tuple(candidates)
            if candidate.track_id >= 0
        }
        components = build_cell_change_components(
            cells,
            candidates,
            weak_ratio=self.config.weak_ratio,
            blob_area_min=self.config.blob_area_min,
        )
        self.last_cell_components = components
        self.last_clusters = components
        return components

    PixelOccupancyMap.clusters = search_cluster_then_cell_components

    original_update = PR26OccupancyTracker._update_track

    def cell_bound_update(self, track, component, now, player_center, player_cell):
        original_update(self, track, component, now, player_center, player_cell)
        support_by_id = getattr(self, "_pr26_cell_support_by_track", None)
        if support_by_id is None:
            support_by_id = {}
            self._pr26_cell_support_by_track = support_by_id
        support_by_id[track.track_id] = component.foot_cell

        raw_ids = frozenset(component.raw_track_ids)
        candidates_by_id = getattr(self.map, "_pr26_candidate_by_id", {})
        matched_candidates = [
            candidates_by_id[track_id]
            for track_id in raw_ids
            if track_id in candidates_by_id
        ]
        matched_candidates.sort(key=_candidate_quality, reverse=True)
        matched = matched_candidates[0] if matched_candidates else None

        # Near-body visual evidence may create attention/face authority, but it
        # cannot create hostile contact without a raw/Target-Capsule body bound
        # to the same cell component.
        near_votes = getattr(self, "_pr26_visual_contact_votes", {}).get(
            track.track_id
        )
        if near_votes:
            near_votes[-1] = bool(raw_ids)
        camera_votes = getattr(self, "_pr26_contact_votes", {}).get(track.track_id)
        if camera_votes:
            camera_votes[-1] = bool(raw_ids and camera_votes[-1])

        if matched is not None:
            foot = _candidate_foot(matched)
            if foot is not None:
                track.foot_point = foot
            track.foot_cell = matched.anchor_cell
            track.cells = frozenset(matched.cells_touched)
            track.bbox = tuple(int(value) for value in matched.bbox)
            track.raw_track_ids = raw_ids
            track.entity_state = EntityState.ENTITY_CONFIRMED
            track.attention_lock = True
            track.reason = "raw body and changed 64px cell are geometrically bound"
        else:
            memory = getattr(self, "_pr26_round_target_memory", None)
            if memory is None:
                track.combat_lock = False
                if track.hostility_state is HostilityState.HOSTILE_CONFIRMED:
                    track.hostility_state = HostilityState.OBSERVE_HOSTILITY
                track.reason = (
                    "cell change confirmed; body association required for COMBAT_LOCK"
                )

    PR26OccupancyTracker._update_track = cell_bound_update

    original_active = PR26OccupancyTracker._active

    def body_consistent_active(self):
        selected = original_active(self)
        memory = getattr(self, "_pr26_round_target_memory", None)

        # Before a round target is latched, a raw-supported body always outranks
        # a raw-less sprite change. This prevents an animated NPC above the
        # player from lending its identity to the real enemy on the right.
        if memory is None:
            metadata = getattr(self, "_pr26_hardening_meta", {})
            candidates_by_id = getattr(self.map, "_pr26_candidate_by_id", {})
            supported = [
                track
                for track in self._tracks.values()
                if track.visible
                and track.entity_state is EntityState.ENTITY_CONFIRMED
                and track.raw_track_ids
            ]

            def track_score(track) -> float:
                candidate_score = max(
                    (
                        _candidate_quality(candidates_by_id[raw_id])
                        for raw_id in track.raw_track_ids
                        if raw_id in candidates_by_id
                    ),
                    default=0.0,
                )
                hardening_quality = float(
                    getattr(metadata.get(track.track_id), "quality", 0.0)
                )
                return candidate_score * 3.0 + hardening_quality + track.occupancy_score

            if supported:
                supported.sort(key=track_score, reverse=True)
                preferred = supported[0]
                if selected is None or selected.track_id != preferred.track_id:
                    if selected is not None:
                        selected.face_only_lock = False
                        selected.combat_lock = False
                    preferred.attention_lock = True
                    preferred.face_only_lock = True
                    preferred.ambiguous = False
                    self._pr26_selected_track_id = preferred.track_id
                    self._emit(
                        f"PR26_CELL_BODY_SELECTION id={preferred.track_id} "
                        f"raw_ids={sorted(preferred.raw_track_ids)} "
                        "reason=SAME_CELL_BODY_ASSOCIATION"
                    )
                    selected = preferred

        memory = getattr(self, "_pr26_round_target_memory", None)
        if selected is not None and memory is None and not selected.raw_track_ids:
            selected.combat_lock = False
            if selected.hostility_state is HostilityState.HOSTILE_CONFIRMED:
                selected.hostility_state = HostilityState.OBSERVE_HOSTILITY

        # Undo an initial latch created only by raw-less vertical geometry. Once
        # a valid raw-supported latch exists, normal PR26.9 continuity remains.
        memory = getattr(self, "_pr26_round_target_memory", None)
        if memory is not None and getattr(memory, "last_raw_track_id", None) is None:
            bad_track = self._tracks.get(memory.track_id)
            if bad_track is not None:
                bad_track.combat_lock = False
                bad_track.hostility_state = HostilityState.OBSERVE_HOSTILITY
            self._pr26_round_target_memory = None
            self._emit(
                f"PR26_RAWLESS_LATCH_REJECTED id={memory.track_id} "
                "reason=CELL_CHANGE_WITHOUT_BODY_ASSOCIATION"
            )
            if selected is not None and selected.track_id == memory.track_id:
                selected.combat_lock = False
        return selected

    PR26OccupancyTracker._active = body_consistent_active

    original_overlay = PR26OccupancyTracker._overlay

    def cell_authority_overlay(self, frame, state, active):
        result = original_overlay(self, frame, state, active)
        arena_x, arena_y, _, _ = (int(value) for value in state.arena_rect)
        for index, search_cluster in enumerate(
            getattr(self.map, "last_search_clusters", ()),
            start=1,
        ):
            left, top, width, height = search_cluster.bbox
            cv2.rectangle(
                result,
                (arena_x + left, arena_y + top),
                (arena_x + left + width, arena_y + top + height),
                (255, 255, 0),
                1,
            )
            cv2.putText(
                result,
                f"SEARCH{index}",
                (arena_x + left, max(82, arena_y + top - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.28,
                (255, 255, 0),
                1,
                cv2.LINE_AA,
            )
        cv2.putText(
            result,
            (
                "CELL AUTHORITY: comparisons=64x64 "
                f"components={len(getattr(self.map, 'last_cell_components', ()))} "
                f"search_clusters={len(getattr(self.map, 'last_search_clusters', ()))} "
                "cluster_lock=OFF"
            ),
            (10, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        return result

    PR26OccupancyTracker._overlay = cell_authority_overlay

    _INSTALLED = True
    print(
        "PR26.13 CELL CHANGE AUTHORITY: every 64x64 cell is compared independently; "
        "clusters are search hints only; raw/Target-Capsule body must overlap the same "
        "cell change before COMBAT_LOCK"
    )


__all__ = [
    "build_cell_change_components",
    "candidate_matches_cell_change",
    "install_cell_change_authority",
    "player_capsule_mask",
]
