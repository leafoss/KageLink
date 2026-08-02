from __future__ import annotations

import math
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable

import cv2

from .domain import CELL_SIZE_PX, GridCell
from .hostility_gate import EntityState, HostilityState
from .occupancy_model import DangerTrack, DiffSource, OccupancyCluster
from .tile_perception import TileClass, TileEvidence


@dataclass(frozen=True, slots=True)
class DangerAffinity:
    best_category: TileClass
    best_similarity: float
    danger_similarity: float
    best_non_danger_similarity: float
    danger_margin: float
    level: str


_INSTALLED = False


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(default if raw is None or not raw.strip() else raw)


def _thresholds() -> tuple[float, float, float, float]:
    return (
        _env_float("KAGE_PR26_DANGER_CONFIRMED_SIMILARITY", 0.90),
        _env_float("KAGE_PR26_DANGER_LIKELY_SIMILARITY", 0.82),
        _env_float("KAGE_PR26_DANGER_WEAK_SIMILARITY", 0.72),
        _env_float("KAGE_PR26_DANGER_MARGIN", 0.04),
    )


def _level(danger: float, margin: float, final_category: TileClass) -> str:
    confirmed, likely, weak, minimum_margin = _thresholds()
    if final_category is TileClass.DANGER and danger >= confirmed:
        return "DANGER_CONFIRMED"
    if danger >= likely and margin >= minimum_margin:
        return "DANGER_LIKELY"
    if danger >= weak:
        return "DANGER_WEAK_PRIOR"
    return "NONE"


def _prior(affinity: DangerAffinity) -> float:
    if affinity.level == "DANGER_CONFIRMED":
        return affinity.danger_similarity
    if affinity.level == "DANGER_LIKELY":
        return affinity.danger_similarity
    if affinity.level == "DANGER_WEAK_PRIOR":
        return affinity.danger_similarity * 0.72
    return 0.0


def _plausible_cluster(cluster: OccupancyCluster) -> bool:
    _, _, width, height = cluster.bbox
    return bool(
        1 <= len(cluster.cells) <= 6
        and 6 <= int(width) <= CELL_SIZE_PX * 2
        and 10 <= int(height) <= CELL_SIZE_PX * 3
        and cluster.occupancy_score >= 0.34
        and any(
            item.diff_source is DiffSource.EXACT_CELL_BASELINE
            for item in cluster.cell_observations
        )
    )


def install_semantic_entity_priority() -> None:
    """Preserve DANGER affinity and track exact-baseline entities without a hard semantic gate."""

    global _INSTALLED
    if _INSTALLED:
        return

    from .occupancy_tracking import PR26OccupancyTracker
    from .pixel_occupancy import PixelOccupancyMap
    from .tile_perception import PR24CombatTilePerception

    def semantic_scan(self, *, frame_bgr, state, observer):
        x0, y0, width, height = (int(value) for value in state.arena_rect)
        if width <= 0 or height <= 0:
            raise RuntimeError("PR26_TILE_ARENA_INVALID")
        arena = frame_bgr[y0 : y0 + height, x0 : x0 + width]
        if arena.size == 0:
            raise RuntimeError("PR26_TILE_ARENA_EMPTY")

        raw_origin = getattr(observer, "grid_origin", (0.0, 0.0))
        origin_x = float(raw_origin[0])
        origin_y = float(raw_origin[1])
        inset = max(0, min(8, int(self.config.crop_inset_px)))
        evidence: dict[GridCell, TileEvidence] = {}
        affinities: dict[GridCell, DangerAffinity] = {}

        for cell_x in self._cell_range(width, origin_x):
            left = int(round(origin_x + cell_x * CELL_SIZE_PX))
            for cell_y in self._cell_range(height, origin_y):
                top = int(round(origin_y + cell_y * CELL_SIZE_PX))
                crop = arena[top : top + CELL_SIZE_PX, left : left + CELL_SIZE_PX].copy()
                if crop.shape[:2] != (CELL_SIZE_PX, CELL_SIZE_PX):
                    continue
                feature_crop = crop[inset : CELL_SIZE_PX - inset, inset : CELL_SIZE_PX - inset]
                feature = self.extractor.extract(feature_crop)
                best = self._terrain_examples[0]
                best_score = -1.0
                danger_score = 0.0
                non_danger_score = 0.0
                for example in self._terrain_examples:
                    score = self.extractor.similarity(feature, example.feature)
                    if score > best_score:
                        best = example
                        best_score = score
                    if example.category is TileClass.DANGER:
                        danger_score = max(danger_score, score)
                    else:
                        non_danger_score = max(non_danger_score, score)

                similarity = max(0.0, min(1.0, best_score))
                known = similarity >= self.config.similarity_threshold
                final_category = best.category if known else TileClass.UNKNOWN
                cell = GridCell(cell_x, cell_y)
                previous = self._previous_crops.get(cell)
                temporal_activity, local_activity_bbox = self._temporal_activity(previous, crop)
                self._previous_crops[cell] = crop
                activity_bbox = None
                if local_activity_bbox is not None:
                    bx, by, bw, bh = local_activity_bbox
                    activity_bbox = (left + bx, top + by, bw, bh)
                margin = danger_score - non_danger_score
                affinity = DangerAffinity(
                    best_category=best.category,
                    best_similarity=similarity,
                    danger_similarity=danger_score,
                    best_non_danger_similarity=non_danger_score,
                    danger_margin=margin,
                    level=_level(danger_score, margin, final_category),
                )
                affinities[cell] = affinity
                evidence[cell] = TileEvidence(
                    cell=cell,
                    bbox=(left, top, CELL_SIZE_PX, CELL_SIZE_PX),
                    category=final_category,
                    similarity=similarity,
                    novelty=1.0 - similarity,
                    known_terrain=known,
                    temporal_activity=temporal_activity,
                    activity_bbox=activity_bbox,
                    matched_example_id=best.example_id,
                )

        self.last_evidence = evidence
        self.last_danger_affinity = affinities
        self.last_summary = {
            "cells": len(evidence),
            "unknown": sum(1 for item in evidence.values() if item.unknown),
            "active_unknown": sum(
                1
                for item in evidence.values()
                if item.unknown
                and item.novelty >= self.config.novelty_threshold
                and item.temporal_activity >= self.config.temporal_activity_threshold
            ),
            "danger_confirmed": sum(1 for item in affinities.values() if item.level == "DANGER_CONFIRMED"),
            "danger_likely": sum(1 for item in affinities.values() if item.level == "DANGER_LIKELY"),
            "danger_weak": sum(1 for item in affinities.values() if item.level == "DANGER_WEAK_PRIOR"),
        }
        return evidence

    PR24CombatTilePerception.scan = semantic_scan

    original_observe = PixelOccupancyMap.observe

    def semantic_observe(self, *args, **kwargs):
        cells, ready = original_observe(self, *args, **kwargs)
        affinities = getattr(self.perception, "last_danger_affinity", {}) if self.perception else {}
        for cell, item in cells.items():
            affinity = affinities.get(cell)
            if affinity is None:
                continue
            item.danger_prior = max(item.danger_prior, _prior(affinity))
            if item.danger_prior > 0.0:
                item.occupancy_score = min(1.0, item.occupancy_score + item.danger_prior * 0.15)
        return cells, ready

    PixelOccupancyMap.observe = semantic_observe

    original_new_track = PR26OccupancyTracker._new_track

    def semantic_new_track(self, cluster: OccupancyCluster, now: float):
        danger_seeded = cluster.danger_prior >= _thresholds()[2] * 0.72
        if danger_seeded:
            return original_new_track(self, cluster, now)
        track = DangerTrack(
            track_id=self._next_id,
            first_seen=now,
            last_seen=now,
            last_seen_frame=self._frame,
            last_danger_time=-1e9,
            last_danger_frame=-1_000_000,
            cells=cluster.cells,
            bbox=cluster.bbox,
            foot_point=cluster.foot_point,
            foot_cell=cluster.foot_cell,
            occupancy_score=cluster.occupancy_score,
            danger_score=cluster.danger_prior,
            true_changed_ratio=cluster.true_changed_ratio,
            largest_blob_area=cluster.largest_blob_area,
            diff_source=self._cluster_source(cluster),
            raw_track_ids=cluster.raw_track_ids,
            entity_votes=deque(maxlen=self.config.evidence_window),
            attention_lock=False,
            reason="EXACT_BASELINE entity candidate; awaiting 2-of-3 persistence",
        )
        self._next_id += 1
        self._tracks[track.track_id] = track
        self._emit(
            f"PR26_ENTITY_SEED id={track.track_id} cells={self._cells_text(track.cells)} "
            f"danger_score={track.danger_score:.2f} occupancy={track.occupancy_score:.2f} "
            f"diff_source={track.diff_source.value}"
        )
        return track

    PR26OccupancyTracker._new_track = semantic_new_track

    def semantic_memory_alive(self, track: DangerTrack, now: float) -> bool:
        if track.danger_score >= _thresholds()[2] * 0.72:
            return (
                now - track.last_danger_time <= self.config.danger_memory_seconds
                or self._frame - track.last_danger_frame <= self.config.danger_memory_frames
            )
        return (
            now - track.last_seen <= self.config.danger_memory_seconds
            or self._frame - track.last_seen_frame <= self.config.danger_memory_frames
        )

    PR26OccupancyTracker._memory_alive = semantic_memory_alive

    def semantic_update_track(self, track, cluster, now, player_center, player_cell):
        old_cells, old_foot = track.cells, track.foot_cell
        weak_prior = _thresholds()[2] * 0.72
        danger_now = cluster.danger_prior >= weak_prior
        if danger_now:
            track.last_danger_time = now
            track.last_danger_frame = self._frame
            track.danger_score = max(track.danger_score, cluster.danger_prior)
            track.attention_lock = True
        elif track.danger_score >= weak_prior and self._memory_alive(track, now):
            track.danger_score *= 0.995
        else:
            track.danger_score *= 0.92

        valid_entity = _plausible_cluster(cluster)
        track.entity_votes.append(valid_entity)
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

        if track.persistence >= self.config.evidence_votes:
            if not track.face_only_lock:
                source = "DANGER_LOCK" if track.danger_score >= weak_prior else "ENTITY_LOCK"
                self._emit(
                    f"PR26_{source} id={track.track_id} active=True cells={self._cells_text(track.cells)} "
                    f"danger_score={track.danger_score:.2f} occupancy={track.occupancy_score:.2f}",
                    "FACE_ONLY_LOCK_CHANGED",
                )
            track.attention_lock = True
            track.face_only_lock = True
            track.entity_state = EntityState.ENTITY_CONFIRMED
        else:
            track.entity_state = EntityState.DANGER_CANDIDATE

        if not old_cells & cluster.cells and old_foot != cluster.foot_cell:
            self._emit(
                f"PR26_ENTITY_MOVED id={track.track_id} from={old_foot} to={cluster.foot_cell} "
                f"danger_score={track.danger_score:.2f}",
                "DANGER_MOVED",
            )

        pixel_distance = math.dist(player_center, cluster.foot_point)
        grid_distance = player_cell.chebyshev_distance(cluster.foot_cell)
        track.pixel_distance_history.append(pixel_distance)
        track.grid_distance_history.append(grid_distance)
        reductions, total = self._approach(track.pixel_distance_history)
        if reductions >= self.config.approach_reductions and total >= self.config.approach_total_px:
            track.hostility_state = HostilityState.HOSTILE_PROBABLE
            track.reason = f"autonomous approach reductions={reductions} total={total:.1f}px"
        if (
            track.hostility_state is HostilityState.HOSTILE_PROBABLE
            and (grid_distance <= 1 or pixel_distance <= self.config.contact_distance_px)
        ):
            if not track.combat_lock:
                self._emit(
                    f"PR26_COMBAT_LOCK id={track.track_id} active=True pixel_distance={pixel_distance:.1f} D={grid_distance}",
                    "COMBAT_LOCK_CHANGED",
                )
            track.hostility_state = HostilityState.HOSTILE_CONFIRMED
            track.combat_lock = True
            track.reason = f"hostile contact pixel_distance={pixel_distance:.1f} D={grid_distance}"
        elif track.face_only_lock and track.hostility_state not in {
            HostilityState.HOSTILE_PROBABLE,
            HostilityState.HOSTILE_CONFIRMED,
        }:
            values = tuple(track.pixel_distance_history)
            if (
                now - track.first_seen >= self.config.non_aggressive_seconds
                and len(values) >= 3
                and max(values) - min(values) <= 16.0
            ):
                track.hostility_state = HostilityState.NON_AGGRESSIVE_ENTITY
                track.reason = "cluster remained stable during passive observation"
            else:
                track.hostility_state = HostilityState.OBSERVE_HOSTILITY
                label = "DANGER_LOCK" if track.danger_score >= weak_prior else "ENTITY_LOCK"
                track.reason = f"{label}; waiting for autonomous pixel approach"

    PR26OccupancyTracker._update_track = semantic_update_track

    def semantic_associate(self, clusters, now, player_center, player_cell):
        options: list[tuple[float, int, int]] = []
        for track_id, track in self._tracks.items():
            for index, cluster in enumerate(clusters):
                score = self._association(track, cluster, now)
                if score is not None:
                    options.append((score, track_id, index))
        options.sort(reverse=True)
        used_tracks: set[int] = set()
        unused_clusters = set(range(len(clusters)))
        for _, track_id, index in options:
            if track_id in used_tracks or index not in unused_clusters:
                continue
            self._update_track(self._tracks[track_id], clusters[index], now, player_center, player_cell)
            used_tracks.add(track_id)
            unused_clusters.remove(index)
        for track_id, track in tuple(self._tracks.items()):
            if track_id in used_tracks:
                continue
            track.visible = False
            track.entity_votes.append(False)
            if not self._memory_alive(track, now):
                track.attention_lock = track.face_only_lock = track.combat_lock = False
                track.entity_state = EntityState.LOST
                track.reason = "visual entity identity expired"
        for index in sorted(unused_clusters):
            cluster = clusters[index]
            if not _plausible_cluster(cluster):
                continue
            track = self._new_track(cluster, now)
            self._update_track(track, cluster, now, player_center, player_cell)
        expired = [
            track_id
            for track_id, track in self._tracks.items()
            if not self._memory_alive(track, now)
            and self._frame - track.last_seen_frame > self.config.danger_memory_frames
        ]
        for track_id in expired:
            self._tracks.pop(track_id, None)

    PR26OccupancyTracker._associate = semantic_associate

    original_filter = PR26OccupancyTracker.filter_candidates

    def semantic_filter(self, *args, **kwargs):
        result = original_filter(self, *args, **kwargs)
        player = tuple(float(value) for value in kwargs["state"].player_center)
        affinities = getattr(self.map.perception, "last_danger_affinity", {}) if self.map.perception else {}
        for cluster in self.last_clusters:
            cluster_affinities = [affinities[cell] for cell in cluster.cells if cell in affinities]
            best_affinity = max(cluster_affinities, key=lambda item: item.danger_similarity, default=None)
            distance = math.dist(player, cluster.foot_point)
            persistence = max((item.persistence for item in cluster.cell_observations), default=0)
            self._emit(
                f"PR26_CLUSTER_CANDIDATE local_id={cluster.local_id} cells={self._cells_text(cluster.cells)} "
                f"bbox={cluster.bbox[2]}x{cluster.bbox[3]} foot=({cluster.foot_point[0]:.1f},{cluster.foot_point[1]:.1f}) "
                f"pixel_ratio={cluster.true_changed_ratio:.3f} occupancy={cluster.occupancy_score:.2f} "
                f"danger_level={(best_affinity.level if best_affinity else 'NONE')} "
                f"danger_similarity={(best_affinity.danger_similarity if best_affinity else 0.0):.3f} "
                f"danger_margin={(best_affinity.danger_margin if best_affinity else 0.0):.3f} "
                f"raw_ids={sorted(cluster.raw_track_ids)} distance={distance:.1f}px persistence={persistence}/3"
            )
        return result

    PR26OccupancyTracker.filter_candidates = semantic_filter
    _INSTALLED = True
    print(
        "PR26.5 SEMANTIC ENTITY PRIORITY: DANGER_CONFIRMED/LIKELY/WEAK preserved; "
        "EXACT baseline entities can reach ENTITY_LOCK without a perfect PR24 class"
    )


__all__ = ["DangerAffinity", "install_semantic_entity_priority"]
