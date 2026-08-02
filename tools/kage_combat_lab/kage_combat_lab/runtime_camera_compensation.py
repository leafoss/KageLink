from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import replace
from typing import Any, Iterable

import cv2
import numpy as np

from .domain import CELL_SIZE_PX, CandidateObservation, GridCell
from .hostility_gate import EntityState, HostilityState
from .occupancy_model import OccupancyCluster, OccupancyState


_INSTALLED = False
_CAMERA_RESPONSE_MIN = 0.075
_CAMERA_MAX_SHIFT_PX = 96.0
_DANGER_MARGIN_MIN = 0.04
_LOCK_SWITCH_ADVANTAGE = 0.65
_LOCK_SWITCH_VOTES = 3
_CONTACT_VOTES = 2


def _feature_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray = cv2.GaussianBlur(gray, (0, 0), 1.1)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)


def estimate_camera_translation(
    reference: np.ndarray,
    current: np.ndarray,
    valid_mask: np.ndarray,
    *,
    max_shift_px: float = _CAMERA_MAX_SHIFT_PX,
) -> tuple[float, float, float, bool]:
    """Estimate absolute baseline->screen translation using stable floor edges."""

    if reference.size == 0 or current.size == 0 or valid_mask.size == 0:
        return 0.0, 0.0, 0.0, False
    if current.shape[:2] != reference.shape[:2]:
        current = cv2.resize(
            current,
            (reference.shape[1], reference.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
    if valid_mask.shape[:2] != reference.shape[:2]:
        valid_mask = cv2.resize(
            valid_mask,
            (reference.shape[1], reference.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )

    scale = 0.5 if min(reference.shape[:2]) >= 192 else 1.0
    target_size = (
        max(32, int(round(reference.shape[1] * scale))),
        max(32, int(round(reference.shape[0] * scale))),
    )
    reference_small = cv2.resize(reference, target_size, interpolation=cv2.INTER_AREA)
    current_small = cv2.resize(current, target_size, interpolation=cv2.INTER_AREA)
    mask_small = cv2.resize(valid_mask, target_size, interpolation=cv2.INTER_NEAREST)
    mask_small = cv2.erode(
        np.where(mask_small > 0, 255, 0).astype(np.uint8),
        np.ones((5, 5), np.uint8),
        iterations=1,
    )
    usable = mask_small > 0
    if float(np.count_nonzero(usable)) / float(usable.size) < 0.20:
        return 0.0, 0.0, 0.0, False

    reference_feature = _feature_image(reference_small)
    current_feature = _feature_image(current_small)
    weights = cv2.GaussianBlur(mask_small.astype(np.float32) / 255.0, (0, 0), 2.0)
    hanning = cv2.createHanningWindow(target_size, cv2.CV_32F)
    window = hanning * weights
    reference_feature = reference_feature * weights
    current_feature = current_feature * weights

    reference_mean = float(reference_feature[usable].mean())
    current_mean = float(current_feature[usable].mean())
    reference_feature = (reference_feature - reference_mean) * weights
    current_feature = (current_feature - current_mean) * weights
    try:
        (dx_small, dy_small), response = cv2.phaseCorrelate(
            reference_feature,
            current_feature,
            window,
        )
    except cv2.error:
        return 0.0, 0.0, 0.0, False

    dx = float(dx_small) / scale
    dy = float(dy_small) / scale
    response = float(response)
    finite = all(math.isfinite(value) for value in (dx, dy, response))
    within_limit = abs(dx) <= max_shift_px and abs(dy) <= max_shift_px
    authoritative = finite and within_limit and response >= _CAMERA_RESPONSE_MIN
    return dx, dy, response, authoritative


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


def _point_in_cluster_mask(
    point: tuple[float, float],
    cluster: OccupancyCluster,
    *,
    radius: int = 4,
) -> bool:
    px, py = point
    for item in cluster.cell_observations:
        if item.mask is None:
            continue
        left, top, width, height = item.evidence.bbox
        local_x = int(round(px - left))
        local_y = int(round(py - top))
        if not (0 <= local_x < width and 0 <= local_y < height):
            continue
        x0 = max(0, local_x - radius)
        y0 = max(0, local_y - radius)
        x1 = min(width, local_x + radius + 1)
        y1 = min(height, local_y + radius + 1)
        if np.any(item.mask[y0:y1, x0:x1] > 0):
            return True
    return False


def candidate_matches_cluster(
    candidate: CandidateObservation,
    cluster: OccupancyCluster,
) -> bool:
    """Raw tracks support a cluster only through real component overlap."""

    if candidate.track_id < 0 or not candidate.visible or not candidate.body_like:
        return False
    foot = _candidate_foot(candidate)
    iou = _bbox_iou(candidate.bbox, cluster.bbox) if candidate.bbox is not None else 0.0
    foot_distance = math.inf if foot is None else math.dist(foot, cluster.foot_point)
    foot_on_mask = False if foot is None else _point_in_cluster_mask(foot, cluster)
    return bool(iou >= 0.20 or foot_on_mask or foot_distance <= 24.0)


def proportional_artifact_reason(
    cluster: OccupancyCluster,
    *,
    min_x: int,
    max_x: int,
    min_y: int,
    max_y: int,
) -> str | None:
    """Reject the exact 128x44 and 48/64x192 physical-log artifacts."""

    _, _, width, height = (int(value) for value in cluster.bbox)
    xs = [cell.x for cell in cluster.cells]
    ys = [cell.y for cell in cluster.cells]
    touches_left = min(xs) <= min_x
    touches_right = max(xs) >= max_x
    touches_top = min(ys) <= min_y
    touches_bottom = max(ys) >= max_y
    rows = max(ys) - min(ys) + 1
    aspect = float(width) / float(max(1, height))

    if width >= 96 and height <= 56 and aspect >= 1.80:
        return "PROPORTIONAL_HORIZONTAL_BAND"
    if touches_top and width >= 80 and height <= 56:
        return "TOP_CAMERA_BAND"
    if (touches_left or touches_right) and rows >= 2 and height >= 96:
        return "EDGE_MULTI_CELL_COLUMN"
    if (touches_left or touches_right) and width <= 52 and height >= 80:
        return "EDGE_VERTICAL_FIELD"
    if touches_bottom and width >= 96 and height <= 48:
        return "BOTTOM_CAMERA_BAND"
    return None


def _reference_mosaic(
    baselines: dict[GridCell, np.ndarray],
    evidence: dict[GridCell, Any],
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray]:
    mosaic = np.zeros((height, width, 3), dtype=np.uint8)
    mask = np.zeros((height, width), dtype=np.uint8)
    for cell, baseline in baselines.items():
        item = evidence.get(cell)
        if item is None or baseline.shape[:2] != (CELL_SIZE_PX, CELL_SIZE_PX):
            continue
        left, top, cell_width, cell_height = (int(value) for value in item.bbox)
        if cell_width != CELL_SIZE_PX or cell_height != CELL_SIZE_PX:
            continue
        if left < 0 or top < 0 or left + cell_width > width or top + cell_height > height:
            continue
        mosaic[top : top + cell_height, left : left + cell_width] = baseline
        mask[top : top + cell_height, left : left + cell_width] = 255
    return mosaic, mask


def install_runtime_camera_compensation() -> None:
    """Install PR26.7 camera registration, frozen baselines and sticky authority."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import runtime_entity_hardening as hardening_module
    from . import runtime_semantic_entity as semantic_module
    from .occupancy_tracking import PR26OccupancyTracker
    from .pixel_occupancy import PixelOccupancyMap

    # Final DANGER authority requires semantic separation from non-danger.
    def margin_aware_prior(affinity) -> float:
        margin = float(getattr(affinity, "danger_margin", -1.0))
        similarity = float(getattr(affinity, "danger_similarity", 0.0))
        level = str(getattr(affinity, "level", "NONE"))
        if level in {"DANGER_CONFIRMED", "DANGER_LIKELY"} and margin >= _DANGER_MARGIN_MIN:
            return similarity
        if level == "DANGER_WEAK_PRIOR":
            return min(0.12, similarity * 0.15)
        return 0.0

    semantic_module._prior = margin_aware_prior

    # Camera registration replaces destructive screen-fixed scene-shift resets.
    hardening_module.global_scene_change_cells = lambda cells: set()
    PixelOccupancyMap._detect_boundary_scene_shift = lambda self, observed: set()

    original_learn = PixelOccupancyMap._learn_baseline
    original_recovery = PixelOccupancyMap._learn_scene_recovery_baseline

    def frozen_learn(self, *args, **kwargs):
        if bool(getattr(self, "baseline_frozen", False)):
            return False
        return original_learn(self, *args, **kwargs)

    def frozen_recovery(self, *args, **kwargs):
        if bool(getattr(self, "baseline_frozen", False)):
            return False
        return original_recovery(self, *args, **kwargs)

    PixelOccupancyMap._learn_baseline = frozen_learn
    PixelOccupancyMap._learn_scene_recovery_baseline = frozen_recovery

    original_observe = PixelOccupancyMap.observe

    def camera_registered_observe(
        self,
        *,
        frame,
        state,
        candidates,
        evidence,
        **kwargs,
    ):
        arena_x, arena_y, arena_width, arena_height = (
            int(value) for value in state.arena_rect
        )
        current_arena = frame[
            arena_y : arena_y + arena_height,
            arena_x : arena_x + arena_width,
        ]
        world_baselines = getattr(self, "_pr26_world_baselines", None)
        if world_baselines is None:
            world_baselines = {
                cell: image.copy() for cell, image in self.exact_baselines.items()
            }
            self._pr26_world_baselines = world_baselines
        reference = getattr(self, "camera_reference", None)
        valid_mask = getattr(self, "camera_reference_mask", None)
        if (
            reference is None
            or valid_mask is None
            or reference.shape[:2] != (arena_height, arena_width)
        ):
            reference, valid_mask = _reference_mosaic(
                world_baselines,
                evidence,
                arena_width,
                arena_height,
            )
            self.camera_reference = reference
            self.camera_reference_mask = valid_mask

        dx, dy, response, authoritative = estimate_camera_translation(
            reference,
            current_arena,
            valid_mask,
        )
        previous = getattr(self, "last_camera_translation", (0.0, 0.0))
        if authoritative and math.dist(previous, (dx, dy)) > 72.0 and response < 0.16:
            authoritative = False
        if authoritative:
            dx = float(round(dx))
            dy = float(round(dy))
            self.last_camera_translation = (dx, dy)
            self._camera_uncertain_frames = 0
        else:
            self._camera_uncertain_frames = int(
                getattr(self, "_camera_uncertain_frames", 0)
            ) + 1
            dx, dy = previous

        self.camera_dx = float(dx)
        self.camera_dy = float(dy)
        self.camera_response = float(response)
        self.camera_alignment_authoritative = bool(authoritative)
        self.baseline_frozen = True

        matrix = np.float32([[1.0, 0.0, dx], [0.0, 1.0, dy]])
        shifted_reference = cv2.warpAffine(
            reference,
            matrix,
            (arena_width, arena_height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        shifted_mask = cv2.warpAffine(
            valid_mask,
            matrix,
            (arena_width, arena_height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        current_baselines: dict[GridCell, np.ndarray] = {}
        for cell, item in evidence.items():
            left, top, width, height = (int(value) for value in item.bbox)
            crop = shifted_reference[top : top + height, left : left + width]
            coverage = shifted_mask[top : top + height, left : left + width]
            if crop.shape[:2] != (CELL_SIZE_PX, CELL_SIZE_PX):
                continue
            if coverage.shape[:2] != crop.shape[:2] or np.mean(coverage > 0) < 0.88:
                continue
            current_baselines[cell] = crop.copy()
        self.exact_baselines = current_baselines if authoritative else {}

        observed, ready = original_observe(
            self,
            frame=frame,
            state=state,
            candidates=candidates,
            evidence=evidence,
            **kwargs,
        )
        if authoritative:
            return observed, ()

        for item in observed.values():
            item.state = OccupancyState.EMPTY
            item.occupancy_score = 0.0
            item.danger_prior = 0.0
            item.persistence = 0
            item.mask = np.zeros((CELL_SIZE_PX, CELL_SIZE_PX), dtype=np.uint8)
            item.blob_bbox = None
        self.last_camera_block_reason = (
            f"CAMERA_ALIGNMENT_UNCERTAIN response={response:.3f} "
            f"candidate_shift=({dx:.0f},{dy:.0f})"
        )
        return observed, ()

    PixelOccupancyMap.observe = camera_registered_observe

    original_clusters = PixelOccupancyMap.clusters

    def camera_safe_clusters(self, cells, candidates):
        if not bool(getattr(self, "camera_alignment_authoritative", False)):
            self.last_clusters = ()
            rejected = list(self.last_rejected_clusters)
            rejected.append(
                {
                    "reason": "CAMERA_ALIGNMENT_UNCERTAIN",
                    "cells": (),
                    "bbox": None,
                }
            )
            self.last_rejected_clusters = tuple(rejected)
            return ()

        clusters = original_clusters(self, cells, candidates)
        if not cells:
            return clusters
        min_x = min(cell.x for cell in cells)
        max_x = max(cell.x for cell in cells)
        min_y = min(cell.y for cell in cells)
        max_y = max(cell.y for cell in cells)
        accepted: list[OccupancyCluster] = []
        rejected = list(self.last_rejected_clusters)
        current_candidates = tuple(candidates)
        for cluster in clusters:
            reason = proportional_artifact_reason(
                cluster,
                min_x=min_x,
                max_x=max_x,
                min_y=min_y,
                max_y=max_y,
            )
            if reason is not None:
                rejected.append(
                    {
                        "reason": reason,
                        "cells": tuple(
                            sorted(cluster.cells, key=lambda cell: (cell.y, cell.x))
                        ),
                        "bbox": cluster.bbox,
                    }
                )
                continue
            matched = {
                candidate.track_id
                for candidate in current_candidates
                if candidate_matches_cluster(candidate, cluster)
            }
            cluster.raw_track_ids = frozenset(matched)
            accepted.append(cluster)
        self.last_rejected_clusters = tuple(rejected)
        self.last_clusters = tuple(accepted)
        return self.last_clusters

    PixelOccupancyMap.clusters = camera_safe_clusters

    original_update = PR26OccupancyTracker._update_track

    def contact_aware_update(self, track, cluster, now, player_center, player_cell):
        original_update(self, track, cluster, now, player_center, player_cell)
        votes_by_id = getattr(self, "_pr26_contact_votes", None)
        if votes_by_id is None:
            votes_by_id = {}
            self._pr26_contact_votes = votes_by_id
        votes = votes_by_id.setdefault(track.track_id, deque(maxlen=3))
        width, height = int(cluster.bbox[2]), int(cluster.bbox[3])
        vertical = height >= 24 and height >= width * 0.75 and width <= 80
        distance = math.dist(player_center, cluster.foot_point)
        grid_distance = player_cell.chebyshev_distance(cluster.foot_cell)
        contact = bool(
            track.entity_state is EntityState.ENTITY_CONFIRMED
            and cluster.raw_track_ids
            and vertical
            and (distance <= self.config.contact_distance_px or grid_distance <= 1)
        )
        votes.append(contact)

    PR26OccupancyTracker._update_track = contact_aware_update

    def sticky_active(self):
        metadata = getattr(self, "_pr26_hardening_meta", {})
        for track in self._tracks.values():
            track.face_only_lock = False
            track.ambiguous = False
        candidates = [
            track
            for track in self._tracks.values()
            if track.visible and track.entity_state is EntityState.ENTITY_CONFIRMED
        ]
        if not candidates:
            self._pr26_selected_track_id = None
            return None

        def quality(track) -> float:
            return float(getattr(metadata.get(track.track_id), "quality", 0.0))

        candidates.sort(
            key=lambda track: (-quality(track), -track.occupancy_score, track.track_id)
        )
        best = candidates[0]
        selected_id = getattr(self, "_pr26_selected_track_id", None)
        selected = next((track for track in candidates if track.track_id == selected_id), None)
        if selected is None:
            selected = best
            self._pr26_challenger_id = None
            self._pr26_challenger_votes = 0
        elif best.track_id != selected.track_id:
            advantage = quality(best) - quality(selected)
            if advantage >= _LOCK_SWITCH_ADVANTAGE:
                if getattr(self, "_pr26_challenger_id", None) == best.track_id:
                    self._pr26_challenger_votes = int(
                        getattr(self, "_pr26_challenger_votes", 0)
                    ) + 1
                else:
                    self._pr26_challenger_id = best.track_id
                    self._pr26_challenger_votes = 1
                if self._pr26_challenger_votes >= _LOCK_SWITCH_VOTES:
                    selected = best
                    self._pr26_challenger_id = None
                    self._pr26_challenger_votes = 0
            else:
                self._pr26_challenger_id = None
                self._pr26_challenger_votes = 0

        selected.face_only_lock = True
        selected.attention_lock = True
        previous_selected = getattr(self, "_pr26_selected_track_id", None)
        self._pr26_selected_track_id = selected.track_id

        contact_votes = getattr(self, "_pr26_contact_votes", {}).get(
            selected.track_id,
            (),
        )
        if sum(contact_votes) >= _CONTACT_VOTES and not selected.combat_lock:
            selected.hostility_state = HostilityState.HOSTILE_CONFIRMED
            selected.combat_lock = True
            selected.reason = "selected body sustained raw-confirmed contact in 2-of-3 frames"
            self._emit(
                f"PR26_CONTACT_HOSTILITY id={selected.track_id} votes={sum(contact_votes)}/3 "
                f"raw_ids={sorted(selected.raw_track_ids)}"
            )
            self._emit(
                f"PR26_COMBAT_LOCK id={selected.track_id} active=True "
                "reason=RAW_CONFIRMED_CONTACT_2_OF_3",
                "COMBAT_LOCK_CHANGED",
            )

        if previous_selected != selected.track_id:
            label = (
                "DANGER_LOCK"
                if hardening_module.danger_has_authority(selected.danger_score)
                else "ENTITY_LOCK"
            )
            self._emit(
                f"PR26_SELECTED_VISUAL_LOCK id={selected.track_id} lock={label} "
                f"quality={quality(selected):.2f} cells={self._cells_text(selected.cells)} "
                "hysteresis=3frames",
                "FACE_ONLY_LOCK_CHANGED",
            )
        if selected.hostility_state is not HostilityState.HOSTILE_CONFIRMED:
            selected.reason = "sticky selected visual lock; waiting for approach/contact"
        return selected

    PR26OccupancyTracker._active = sticky_active

    original_filter = PR26OccupancyTracker.filter_candidates

    def camera_telemetry_filter(self, *args, **kwargs):
        result = original_filter(self, *args, **kwargs)
        state = (
            round(float(getattr(self.map, "camera_dx", 0.0)), 1),
            round(float(getattr(self.map, "camera_dy", 0.0)), 1),
            round(float(getattr(self.map, "camera_response", 0.0)), 3),
            bool(getattr(self.map, "camera_alignment_authoritative", False)),
        )
        previous = getattr(self, "_pr26_last_camera_telemetry", None)
        if previous != state:
            self._pr26_last_camera_telemetry = state
            self._emit(
                "PR26_CAMERA_ALIGNMENT "
                f"dx={state[0]:.1f} dy={state[1]:.1f} response={state[2]:.3f} "
                f"authoritative={state[3]} baselines_frozen=true"
            )
        seen_rejections = getattr(self, "_pr26_seen_rejections", set())
        for rejected in getattr(self.map, "last_rejected_clusters", ()):
            key = (str(rejected.get("reason")), tuple(rejected.get("cells", ())))
            if key in seen_rejections:
                continue
            seen_rejections.add(key)
            self._emit(
                f"PR26_CLUSTER_REJECTED reason={key[0]} cells={key[1]} "
                f"bbox={rejected.get('bbox')}"
            )
        self._pr26_seen_rejections = seen_rejections
        if not state[3]:
            for track in self._tracks.values():
                track.attention_lock = False
                track.face_only_lock = False
                track.combat_lock = False
            return ()
        return result

    PR26OccupancyTracker.filter_candidates = camera_telemetry_filter

    original_overlay = PR26OccupancyTracker._overlay

    def camera_overlay(self, frame, state, active):
        result = original_overlay(self, frame, state, active)
        cv2.putText(
            result,
            (
                f"CAM dx={float(getattr(self.map, 'camera_dx', 0.0)):.0f} "
                f"dy={float(getattr(self.map, 'camera_dy', 0.0)):.0f} "
                f"r={float(getattr(self.map, 'camera_response', 0.0)):.2f} "
                f"ok={bool(getattr(self.map, 'camera_alignment_authoritative', False))}"
            ),
            (10, 57),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        return result

    PR26OccupancyTracker._overlay = camera_overlay

    _INSTALLED = True
    print(
        "PR26.7 CAMERA COMPENSATION: frozen world baseline -> phase registration -> "
        "screen-aligned pixel truth; strict raw-mask overlap; sticky selected lock; "
        "2-of-3 raw-confirmed contact may authorize COMBAT_LOCK"
    )


__all__ = [
    "candidate_matches_cluster",
    "estimate_camera_translation",
    "install_runtime_camera_compensation",
    "proportional_artifact_reason",
]
