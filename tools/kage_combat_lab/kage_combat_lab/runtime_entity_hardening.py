from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .domain import CELL_SIZE_PX, GridCell
from .hostility_gate import EntityState, HostilityState
from .occupancy_model import (
    DangerTrack,
    DiffSource,
    OccupancyCluster,
    OccupancyState,
)


_INSTALLED = False
_DANGER_AUTHORITY_MIN = 0.82


@dataclass(slots=True)
class _TrackEvidence:
    last_raw_ids: frozenset[int] = field(default_factory=frozenset)
    raw_consistency_hits: int = 0
    motion_votes: deque[bool] = field(default_factory=lambda: deque(maxlen=3))
    entity_votes: deque[bool] = field(default_factory=lambda: deque(maxlen=3))
    quality: float = 0.0


def danger_has_authority(value: float) -> bool:
    """Only confirmed/likely DANGER affinity can create DANGER authority."""

    return float(value) >= _DANGER_AUTHORITY_MIN


def cluster_artifact_reason(
    cluster: OccupancyCluster,
    *,
    min_x: int,
    max_x: int,
    min_y: int,
    max_y: int,
) -> str | None:
    """Reject UI/border strips proven by the PR26.5 physical log."""

    left, top, width, height = (int(value) for value in cluster.bbox)
    del left, top
    aspect = float(width) / float(max(1, height))
    xs = [cell.x for cell in cluster.cells]
    ys = [cell.y for cell in cluster.cells]
    touches_left = min(xs) <= min_x
    touches_right = max(xs) >= max_x
    touches_top = min(ys) <= min_y
    touches_bottom = max(ys) >= max_y

    if (
        cluster.true_changed_ratio >= 0.85
        and cluster.largest_blob_area >= 2200
        and width >= CELL_SIZE_PX - 4
        and height >= CELL_SIZE_PX - 4
    ):
        return "SATURATED_FIELD"
    if height <= 38 and width >= 48 and aspect >= 1.45:
        return "HORIZONTAL_UI_STRIP"
    if touches_top and height <= 40 and width >= 40:
        return "TOP_BORDER_STRIP"
    if touches_bottom and height <= 32 and width >= 48:
        return "BOTTOM_BORDER_STRIP"
    if (touches_left or touches_right) and width <= 20 and height >= 64:
        return "VERTICAL_BORDER_STRIP"
    if (touches_left or touches_right) and height <= 28 and width >= 72:
        return "EDGE_HORIZONTAL_STRIP"
    return None


def global_scene_change_cells(cells: dict[GridCell, Any]) -> set[GridCell]:
    """Detect distributed near-total baseline failure, not merely one edge column."""

    exact = {
        cell: item
        for cell, item in cells.items()
        if item.diff_source is DiffSource.EXACT_CELL_BASELINE
    }
    severe = {
        cell
        for cell, item in exact.items()
        if item.true_changed_ratio >= 0.82
        and item.largest_blob_area >= 1900
        and (item.blob_width >= 48 or item.blob_height >= 48)
    }
    if len(severe) < 5:
        return set()
    columns = {cell.x for cell in severe}
    rows = {cell.y for cell in severe}
    distributed = len(columns) >= 3 and (len(rows) >= 2 or len(severe) >= 8)
    broad = len(severe) >= max(7, int(math.ceil(len(exact) * 0.12)))
    return severe if distributed or broad else set()


def install_runtime_entity_hardening() -> None:
    """Install PR26.6 false-cluster rejection and strict identity continuity."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import runtime_semantic_entity as semantic_module
    from .occupancy_tracking import PR26OccupancyTracker
    from .pixel_occupancy import PixelOccupancyMap

    # DANGER_WEAK_PRIOR remains ranking telemetry only. It cannot seed or
    # preserve DANGER authority. Confirmed/likely affinity remains strong.
    def strict_prior(affinity) -> float:
        if affinity.level in {"DANGER_CONFIRMED", "DANGER_LIKELY"}:
            return float(affinity.danger_similarity)
        if affinity.level == "DANGER_WEAK_PRIOR":
            return min(0.18, float(affinity.danger_similarity) * 0.20)
        return 0.0

    semantic_module._prior = strict_prior

    original_observe = PixelOccupancyMap.observe

    def hardened_observe(self, *args, **kwargs):
        observed, ready = original_observe(self, *args, **kwargs)
        severe = global_scene_change_cells(observed)
        self.last_global_scene_shift = bool(severe)
        if not severe:
            return observed, ready

        affected = set(self.exact_baselines) | set(severe)
        self.scene_shift_generation += 1
        self.last_scene_shift_cells = tuple(
            sorted(affected, key=lambda cell: (cell.y, cell.x))
        )
        self.exact_baselines.clear()
        self._samples.clear()
        self._votes.clear()
        self._scene_recovery_cells.update(observed)
        for item in observed.values():
            item.state = OccupancyState.EMPTY
            item.occupancy_score = 0.0
            item.danger_prior = 0.0
            item.persistence = 0
            item.mask = np.zeros((CELL_SIZE_PX, CELL_SIZE_PX), dtype=np.uint8)
            item.blob_bbox = None
        return observed, ready

    PixelOccupancyMap.observe = hardened_observe

    original_clusters = PixelOccupancyMap.clusters

    def hardened_clusters(self, cells, candidates):
        clusters = original_clusters(self, cells, candidates)
        if not cells:
            return clusters
        min_x = min(cell.x for cell in cells)
        max_x = max(cell.x for cell in cells)
        min_y = min(cell.y for cell in cells)
        max_y = max(cell.y for cell in cells)
        accepted: list[OccupancyCluster] = []
        rejected = list(self.last_rejected_clusters)
        for cluster in clusters:
            reason = cluster_artifact_reason(
                cluster,
                min_x=min_x,
                max_x=max_x,
                min_y=min_y,
                max_y=max_y,
            )
            if reason is None:
                accepted.append(cluster)
                continue
            rejected.append(
                {
                    "reason": reason,
                    "cells": tuple(
                        sorted(cluster.cells, key=lambda cell: (cell.y, cell.x))
                    ),
                    "bbox": cluster.bbox,
                }
            )
        self.last_rejected_clusters = tuple(rejected)
        self.last_clusters = tuple(accepted)
        return self.last_clusters

    PixelOccupancyMap.clusters = hardened_clusters

    def metadata(self) -> dict[int, _TrackEvidence]:
        value = getattr(self, "_pr26_hardening_meta", None)
        if value is None:
            value = {}
            self._pr26_hardening_meta = value
        return value

    def hard_association(self, track: DangerTrack, cluster: OccupancyCluster, now: float):
        dt = max(0.01, float(now) - float(track.last_seen))
        maximum_cells = max(
            1,
            min(3, int(math.ceil(dt * self.config.max_speed_cells_per_second)) + 1),
        )
        maximum_pixels = max(
            96.0,
            dt * self.config.max_speed_cells_per_second * CELL_SIZE_PX + 40.0,
        )
        cell_distance = track.foot_cell.chebyshev_distance(cluster.foot_cell)
        pixel_distance = math.dist(track.foot_point, cluster.foot_point)

        # Raw-ID overlap is supporting evidence, never permission to teleport.
        if cell_distance > maximum_cells or pixel_distance > maximum_pixels:
            return None

        old_area = max(1, int(track.bbox[2]) * int(track.bbox[3]))
        new_area = max(1, int(cluster.bbox[2]) * int(cluster.bbox[3]))
        area_ratio = float(new_area) / float(old_area)
        shared_cells = len(track.cells & cluster.cells)
        shared_raw = len(track.raw_track_ids & cluster.raw_track_ids)
        if (area_ratio > 4.0 or area_ratio < 0.25) and not (shared_cells and shared_raw):
            return None
        return (
            shared_cells * 220.0
            + shared_raw * 180.0
            + cluster.danger_prior * 100.0
            + cluster.occupancy_score * 70.0
            - cell_distance * 42.0
            - pixel_distance * 0.35
        )

    PR26OccupancyTracker._association = hard_association

    def hard_new_track(self, cluster: OccupancyCluster, now: float):
        danger_authority = danger_has_authority(cluster.danger_prior)
        track = DangerTrack(
            track_id=self._next_id,
            first_seen=now,
            last_seen=now,
            last_seen_frame=self._frame,
            last_danger_time=now if danger_authority else -1e9,
            last_danger_frame=self._frame if danger_authority else -1_000_000,
            cells=cluster.cells,
            bbox=cluster.bbox,
            foot_point=cluster.foot_point,
            foot_cell=cluster.foot_cell,
            occupancy_score=cluster.occupancy_score,
            danger_score=cluster.danger_prior if danger_authority else 0.0,
            true_changed_ratio=cluster.true_changed_ratio,
            largest_blob_area=cluster.largest_blob_area,
            diff_source=self._cluster_source(cluster),
            raw_track_ids=cluster.raw_track_ids,
            entity_votes=deque(maxlen=self.config.evidence_window),
            attention_lock=danger_authority,
            face_only_lock=False,
            reason=(
                "authoritative DANGER seed; awaiting entity evidence"
                if danger_authority
                else "exact-baseline cluster; awaiting motion/raw body evidence"
            ),
        )
        self._next_id += 1
        self._tracks[track.track_id] = track
        metadata(self)[track.track_id] = _TrackEvidence(
            last_raw_ids=cluster.raw_track_ids
        )
        event = "PR26_DANGER_SEED" if danger_authority else "PR26_ENTITY_SEED"
        self._emit(
            f"{event} id={track.track_id} cells={self._cells_text(track.cells)} "
            f"danger_score={track.danger_score:.2f} occupancy={track.occupancy_score:.2f} "
            f"diff_source={track.diff_source.value}"
        )
        return track

    PR26OccupancyTracker._new_track = hard_new_track

    def hard_memory_alive(self, track: DangerTrack, now: float) -> bool:
        if danger_has_authority(track.danger_score):
            return (
                now - track.last_danger_time <= self.config.danger_memory_seconds
                or self._frame - track.last_danger_frame
                <= self.config.danger_memory_frames
            )
        return (
            now - track.last_seen <= self.config.danger_memory_seconds
            or self._frame - track.last_seen_frame <= self.config.danger_memory_frames
        )

    PR26OccupancyTracker._memory_alive = hard_memory_alive

    def hard_update_track(self, track, cluster, now, player_center, player_cell):
        meta = metadata(self).setdefault(track.track_id, _TrackEvidence())
        old_cells = track.cells
        old_foot_cell = track.foot_cell
        movement = math.dist(track.foot_point, cluster.foot_point)
        raw_consistent = bool(meta.last_raw_ids & cluster.raw_track_ids)
        if raw_consistent:
            meta.raw_consistency_hits += 1
        current_raw_present = bool(cluster.raw_track_ids)
        width, height = int(cluster.bbox[2]), int(cluster.bbox[3])
        vertical_body = bool(
            height >= 28
            and height >= width * 0.80
            and width <= 80
            and len(cluster.cells) <= 3
        )
        plausible_motion = 4.0 <= movement <= 112.0
        meta.motion_votes.append(plausible_motion)
        entity_evidence = bool(
            (vertical_body and current_raw_present)
            or raw_consistent
            or sum(meta.motion_votes) >= 2
        )
        meta.entity_votes.append(entity_evidence)
        track.entity_votes.append(entity_evidence)
        meta.last_raw_ids = cluster.raw_track_ids

        danger_now = danger_has_authority(cluster.danger_prior)
        if danger_now:
            track.last_danger_time = now
            track.last_danger_frame = self._frame
            track.danger_score = max(track.danger_score, cluster.danger_prior)
        elif not self._memory_alive(track, now):
            track.danger_score = 0.0

        track.visible = True
        track.last_seen = now
        track.last_seen_frame = self._frame
        track.cells = cluster.cells
        track.bbox = cluster.bbox
        track.foot_point = cluster.foot_point
        track.foot_cell = cluster.foot_cell
        track.occupancy_score = cluster.occupancy_score
        track.true_changed_ratio = cluster.true_changed_ratio
        track.largest_blob_area = cluster.largest_blob_area
        track.diff_source = self._cluster_source(cluster)
        track.raw_track_ids = cluster.raw_track_ids

        confirmed = sum(meta.entity_votes) >= self.config.evidence_votes
        if confirmed:
            first_confirmation = track.entity_state is not EntityState.ENTITY_CONFIRMED
            track.entity_state = EntityState.ENTITY_CONFIRMED
            track.attention_lock = True
            if first_confirmation:
                source = "DANGER" if danger_has_authority(track.danger_score) else "ENTITY"
                self._emit(
                    f"PR26_ENTITY_CONFIRMED id={track.track_id} source={source} "
                    f"cells={self._cells_text(track.cells)} vertical={vertical_body} "
                    f"raw_consistent={raw_consistent} motion_votes={sum(meta.motion_votes)}/3"
                )
        else:
            track.entity_state = EntityState.DANGER_CANDIDATE
            track.face_only_lock = False
            track.attention_lock = danger_has_authority(track.danger_score)

        if not old_cells & cluster.cells and old_foot_cell != cluster.foot_cell:
            self._emit(
                f"PR26_ENTITY_MOVED id={track.track_id} from={old_foot_cell} "
                f"to={cluster.foot_cell} movement={movement:.1f}px "
                f"danger_score={track.danger_score:.2f}",
                "DANGER_MOVED",
            )

        pixel_distance = math.dist(player_center, cluster.foot_point)
        grid_distance = player_cell.chebyshev_distance(cluster.foot_cell)
        track.pixel_distance_history.append(pixel_distance)
        track.grid_distance_history.append(grid_distance)
        reductions, total = self._approach(track.pixel_distance_history)
        if confirmed and reductions >= self.config.approach_reductions and total >= self.config.approach_total_px:
            track.hostility_state = HostilityState.HOSTILE_PROBABLE
            track.reason = f"autonomous approach reductions={reductions} total={total:.1f}px"
        elif confirmed:
            track.hostility_state = HostilityState.OBSERVE_HOSTILITY
            track.reason = "entity confirmed; waiting for autonomous pixel approach"
        else:
            track.reason = "cluster persistent but lacks motion/raw body evidence"

        if (
            confirmed
            and track.hostility_state is HostilityState.HOSTILE_PROBABLE
            and (grid_distance <= 1 or pixel_distance <= self.config.contact_distance_px)
        ):
            track.hostility_state = HostilityState.HOSTILE_CONFIRMED
            track.combat_lock = True
            track.reason = f"hostile contact pixel_distance={pixel_distance:.1f} D={grid_distance}"
            self._emit(
                f"PR26_COMBAT_LOCK id={track.track_id} active=True "
                f"pixel_distance={pixel_distance:.1f} D={grid_distance}",
                "COMBAT_LOCK_CHANGED",
            )

        proximity = max(0.0, 1.0 - pixel_distance / 480.0)
        meta.quality = (
            (2.0 if danger_has_authority(track.danger_score) else 0.0)
            + (0.7 if raw_consistent else 0.0)
            + (0.4 if vertical_body else 0.0)
            + min(0.8, sum(meta.motion_votes) * 0.28)
            + cluster.occupancy_score * 0.45
            + proximity * 0.65
        )

    PR26OccupancyTracker._update_track = hard_update_track

    def hard_active(self):
        meta_by_id = metadata(self)
        for track in self._tracks.values():
            track.face_only_lock = False
            track.ambiguous = False
        candidates = [
            track
            for track in self._tracks.values()
            if track.visible and track.entity_state is EntityState.ENTITY_CONFIRMED
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda track: (
                -meta_by_id.get(track.track_id, _TrackEvidence()).quality,
                -track.occupancy_score,
                track.track_id,
            )
        )
        best = candidates[0]
        best_quality = meta_by_id.get(best.track_id, _TrackEvidence()).quality
        if len(candidates) > 1:
            second_quality = meta_by_id.get(candidates[1].track_id, _TrackEvidence()).quality
            if best_quality - second_quality < 0.22:
                best.ambiguous = True
                best.reason = (
                    f"AMBIGUOUS validated entities quality_delta="
                    f"{best_quality-second_quality:.2f}; authority blocked"
                )
                return best
        best.face_only_lock = True
        best.attention_lock = True
        label = "DANGER_LOCK" if danger_has_authority(best.danger_score) else "ENTITY_LOCK"
        if getattr(self, "_pr26_selected_track_id", None) != best.track_id:
            self._pr26_selected_track_id = best.track_id
            self._emit(
                f"PR26_SELECTED_VISUAL_LOCK id={best.track_id} lock={label} "
                f"quality={best_quality:.2f} cells={self._cells_text(best.cells)}",
                "FACE_ONLY_LOCK_CHANGED",
            )
        if best.hostility_state is not HostilityState.HOSTILE_CONFIRMED:
            best.reason = f"SELECTED_{label}; waiting for autonomous pixel approach"
        return best

    PR26OccupancyTracker._active = hard_active

    _INSTALLED = True
    print(
        "PR26.6 ENTITY HARDENING: horizontal/border artifacts rejected; "
        "DANGER_WEAK has no authority; motion/raw body evidence required; "
        "teleport association blocked; distributed scene changes reset all authority"
    )


__all__ = [
    "cluster_artifact_reason",
    "danger_has_authority",
    "global_scene_change_cells",
    "install_runtime_entity_hardening",
]
