from __future__ import annotations

import json
import math
import time
from collections import deque
from typing import Any, Iterable

import cv2
import numpy as np

from .domain import CELL_SIZE_PX, CandidateObservation, GridCell, ObservationKind
from .hostility_gate import EntityState, HostilityState
from .occupancy_model import (
    CellOccupancy,
    DangerTrack,
    DiffSource,
    OccupancyCluster,
    OccupancyConfig,
    OccupancySnapshot,
    OccupancyState,
    PR26ControlMode,
)
from .pixel_occupancy import PixelOccupancyMap
from .tile_perception import TileClass, TileEvidence


class PR26OccupancyTracker:
    """Mobile DANGER identity driven by real pixel occupancy clusters."""

    def __init__(self, config: OccupancyConfig | None = None) -> None:
        self.config = (config or OccupancyConfig.from_environment()).normalized()
        self.mode = PR26ControlMode.from_environment()
        self.map = PixelOccupancyMap(self.config)
        self._tracks: dict[int, DangerTrack] = {}
        self._next_id = 1
        self._frame = -1
        self._last_pr24_scan: float | None = None
        self._events: deque[str] = deque()
        self._video_events: deque[str] = deque()
        self._last_save = -1e9
        self.last_snapshot = OccupancySnapshot(control_mode=self.mode.value)
        self.last_overlay_frame: np.ndarray | None = None
        self.last_evidence: dict[GridCell, TileEvidence] = {}
        self.last_cells: dict[GridCell, CellOccupancy] = {}
        self.last_clusters: tuple[OccupancyCluster, ...] = ()

    def bind_perception(self, perception: Any) -> None:
        self.map.bind_perception(perception)

    def notify_pr24_scan(self, timestamp: float) -> None:
        self._last_pr24_scan = float(timestamp)

    def consume_console_events(self) -> tuple[str, ...]:
        values = tuple(self._events)
        self._events.clear()
        return values

    def consume_video_events(self) -> tuple[str, ...]:
        values = tuple(self._video_events)
        self._video_events.clear()
        return values

    def _emit(self, text: str, video: str | None = None) -> None:
        self._events.append(text)
        if video:
            self._video_events.append(video)

    @staticmethod
    def _cells_text(cells: Iterable[GridCell]) -> str:
        ordered = sorted(cells, key=lambda cell: (cell.y, cell.x))
        return "{" + ",".join(f"({c.x},{c.y})" for c in ordered) + "}"

    def _memory_alive(self, track: DangerTrack, now: float) -> bool:
        return (
            now - track.last_danger_time <= self.config.danger_memory_seconds
            or self._frame - track.last_danger_frame <= self.config.danger_memory_frames
        )

    def _association(self, track: DangerTrack, cluster: OccupancyCluster, now: float) -> float | None:
        dt = max(0.01, now - track.last_seen)
        jump = max(1, int(math.ceil(dt * self.config.max_speed_cells_per_second)))
        cell_distance = track.foot_cell.chebyshev_distance(cluster.foot_cell)
        shared_cells = len(track.cells & cluster.cells)
        shared_raw = len(track.raw_track_ids & cluster.raw_track_ids)
        pixel_distance = math.dist(track.foot_point, cluster.foot_point)
        if cell_distance > jump and not shared_cells and not shared_raw:
            return None
        if pixel_distance > (jump + 1) * CELL_SIZE_PX and not shared_cells and not shared_raw:
            return None
        return (
            shared_cells * 200.0
            + shared_raw * 160.0
            + cluster.danger_prior * 120.0
            + cluster.occupancy_score * 80.0
            - cell_distance * 35.0
            - pixel_distance * 0.25
        )

    def _new_track(self, cluster: OccupancyCluster, now: float) -> DangerTrack:
        track = DangerTrack(
            track_id=self._next_id,
            first_seen=now,
            last_seen=now,
            last_seen_frame=self._frame,
            last_danger_time=now,
            last_danger_frame=self._frame,
            cells=cluster.cells,
            bbox=cluster.bbox,
            foot_point=cluster.foot_point,
            foot_cell=cluster.foot_cell,
            occupancy_score=cluster.occupancy_score,
            danger_score=max(cluster.danger_prior, self.config.danger_confidence),
            true_changed_ratio=cluster.true_changed_ratio,
            largest_blob_area=cluster.largest_blob_area,
            diff_source=self._cluster_source(cluster),
            raw_track_ids=cluster.raw_track_ids,
            entity_votes=deque(maxlen=self.config.evidence_window),
        )
        self._next_id += 1
        self._tracks[track.track_id] = track
        self._emit(
            f"PR26_DANGER_SEED id={track.track_id} cells={self._cells_text(track.cells)} "
            f"confidence={cluster.danger_prior:.2f} danger_score={track.danger_score:.2f} "
            f"diff_source={track.diff_source.value} "
            f"true_changed_ratio={track.true_changed_ratio:.3f}",
            "DANGER_FIRST_SEEN",
        )
        return track

    @staticmethod
    def _cluster_source(cluster: OccupancyCluster) -> DiffSource:
        sources = {item.diff_source for item in cluster.cell_observations}
        if DiffSource.EXACT_CELL_BASELINE in sources:
            return DiffSource.EXACT_CELL_BASELINE
        if DiffSource.CLASS_REFERENCE in sources:
            return DiffSource.CLASS_REFERENCE
        return DiffSource.NONE

    def _approach(self, history: Iterable[float]) -> tuple[int, float]:
        values = tuple(float(value) for value in history)
        reductions = sum(
            1
            for previous, current in zip(values, values[1:])
            if previous - current >= self.config.approach_step_min_px
        )
        total = max(0.0, values[0] - values[-1]) if len(values) >= 2 else 0.0
        return reductions, total

    def _update_track(
        self,
        track: DangerTrack,
        cluster: OccupancyCluster,
        now: float,
        player_center: tuple[float, float],
        player_cell: GridCell,
    ) -> None:
        old_cells, old_foot = track.cells, track.foot_cell
        danger_now = cluster.danger_prior >= self.config.danger_confidence
        if danger_now:
            track.last_danger_time = now
            track.last_danger_frame = self._frame
            track.danger_score = max(track.danger_score, cluster.danger_prior)
        elif self._memory_alive(track, now):
            track.danger_score = max(self.config.danger_confidence, track.danger_score * 0.995)
        else:
            track.danger_score *= 0.92

        track.entity_votes.append(True)
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
                self._emit(
                    f"PR26_FACE_ONLY_LOCK id={track.track_id} active=True "
                    f"cells={self._cells_text(track.cells)} danger_score={track.danger_score:.2f}",
                    "FACE_ONLY_LOCK_CHANGED",
                )
            track.face_only_lock = True
            track.entity_state = EntityState.ENTITY_CONFIRMED
        else:
            track.entity_state = EntityState.DANGER_CANDIDATE

        if not old_cells & cluster.cells and old_foot != cluster.foot_cell:
            self._emit(
                f"PR26_DANGER_MOVED id={track.track_id} from={old_foot} "
                f"to={cluster.foot_cell} danger_score={track.danger_score:.2f}",
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
                    f"PR26_COMBAT_LOCK id={track.track_id} active=True "
                    f"pixel_distance={pixel_distance:.1f} D={grid_distance}",
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
                track.reason = "FACE_ONLY_LOCK; waiting for autonomous pixel approach"

    def _associate(
        self,
        clusters: tuple[OccupancyCluster, ...],
        now: float,
        player_center: tuple[float, float],
        player_cell: GridCell,
    ) -> None:
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
                track.reason = "mobile DANGER identity expired"
        for index in sorted(unused_clusters):
            cluster = clusters[index]
            if cluster.danger_prior < self.config.danger_confidence:
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

    def _active(self) -> DangerTrack | None:
        tracks = [track for track in self._tracks.values() if track.attention_lock]
        if not tracks:
            return None
        tracks.sort(
            key=lambda track: (
                not track.visible,
                not track.combat_lock,
                not track.face_only_lock,
                -track.danger_score,
                -track.occupancy_score,
                track.track_id,
            )
        )
        best = tracks[0]
        best.ambiguous = False
        if len(tracks) > 1:
            second = tracks[1]
            best.ambiguous = (
                best.visible
                and second.visible
                and abs(best.danger_score - second.danger_score) < 0.04
                and abs(best.occupancy_score - second.occupancy_score) < 0.06
            )
            if best.ambiguous:
                best.face_only_lock = best.combat_lock = False
                best.reason = "AMBIGUOUS danger clusters; authority blocked"
        return best

    def _face(self, player: tuple[float, float], foot: tuple[float, float]) -> str | None:
        dx, dy = foot[0] - player[0], foot[1] - player[1]
        if max(abs(dx), abs(dy)) <= self.config.face_deadzone_px:
            return None
        if abs(dx) >= abs(dy):
            return "RIGHT" if dx > 0 else "LEFT"
        return "DOWN" if dy > 0 else "UP"

    def _candidate(self, track: DangerTrack, player: tuple[float, float]) -> CandidateObservation:
        return CandidateObservation(
            track_id=2_000_000 + track.track_id,
            anchor_cell=track.foot_cell,
            kind=ObservationKind.CLEAN_BODY,
            visible=track.visible,
            body_like=True,
            confidence=max(0.80, min(1.0, 0.55 * track.danger_score + 0.45 * track.occupancy_score)),
            cells_touched=frozenset({track.foot_cell}),
            face_hint=self._face(player, track.foot_point),
            bbox=track.bbox,
            foot_point=track.foot_point,
            relative_offset_px=(track.foot_point[0] - player[0], track.foot_point[1] - player[1]),
            identity_score=max(0.75, track.danger_score),
            appearance_score=max(0.70, track.occupancy_score),
            position_score=0.90,
            shape_similarity=max(0.60, track.occupancy_score),
            motion_score=0.80 if track.hostility_state in {HostilityState.HOSTILE_PROBABLE, HostilityState.HOSTILE_CONFIRMED} else 0.55,
            background_probability=0.05,
        )

    def _snapshot(self, track: DangerTrack | None) -> OccupancySnapshot:
        if track is None:
            return OccupancySnapshot(control_mode=self.mode.value)
        reductions, total = self._approach(track.pixel_distance_history)
        coverage = max(
            (self.last_cells[cell].bbox_coverage_ratio for cell in track.cells if cell in self.last_cells),
            default=0.0,
        )
        return OccupancySnapshot(
            visual_lock=track.face_only_lock,
            combat_lock=track.combat_lock,
            raw_track_id=2_000_000 + track.track_id,
            cell=track.foot_cell,
            entity_state=track.entity_state,
            hostility_state=track.hostility_state,
            danger_confidence=track.danger_score,
            terrain_class=TileClass.DANGER,
            changed_pixel_ratio=track.true_changed_ratio,
            true_changed_ratio=track.true_changed_ratio,
            bbox_coverage_ratio=coverage,
            diff_source=track.diff_source.value,
            largest_blob_area=track.largest_blob_area,
            persistence=track.persistence,
            distance_history=tuple(track.grid_distance_history),
            pixel_distance_history=tuple(round(v, 2) for v in track.pixel_distance_history),
            approach_votes=reductions,
            approach_total_px=total,
            reason=track.reason,
            attention_lock=track.attention_lock,
            face_only_lock=track.face_only_lock,
            cluster_id=track.track_id,
            cluster_cells=tuple((c.x, c.y) for c in sorted(track.cells)),
            occupancy_score=track.occupancy_score,
            danger_score=track.danger_score,
            control_mode=self.mode.value,
            ambiguous=track.ambiguous,
        )

    def _overlay(self, frame: np.ndarray, state: Any, active: DangerTrack | None) -> np.ndarray:
        result = frame.copy()
        arena_x, arena_y, _, _ = (int(v) for v in state.arena_rect)
        for item in self.last_cells.values():
            left, top, width, height = item.evidence.bbox
            color = (0, 0, 255) if item.state is OccupancyState.OCCUPIED else (0, 180, 255) if item.state is OccupancyState.WEAK else (0, 140, 0)
            start, end = (arena_x + left, arena_y + top), (arena_x + left + width, arena_y + top + height)
            cv2.rectangle(result, start, end, color, 1)
            cv2.putText(result, f"{item.true_changed_ratio:.2f} {item.diff_source.value[:1]} D{item.danger_prior:.2f}", (start[0] + 2, start[1] + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.30, color, 1, cv2.LINE_AA)
        for cluster in self.last_clusters:
            left, top, width, height = cluster.bbox
            cv2.rectangle(result, (arena_x + left, arena_y + top), (arena_x + left + width, arena_y + top + height), (255, 0, 255), 2)
            cv2.circle(result, (arena_x + int(cluster.foot_point[0]), arena_y + int(cluster.foot_point[1])), 5, (255, 0, 255), -1)
        if active:
            cv2.putText(result, f"PR26.3 {self.mode.value} id={active.track_id} face={active.face_only_lock} combat={active.combat_lock}", (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
        return result

    def _save_evidence(self, now: float, overlay: np.ndarray, active: DangerTrack | None) -> None:
        if now - self._last_save < self.config.evidence_save_seconds:
            return
        ranked = sorted(self.last_cells.values(), key=lambda x: (x.danger_prior, x.occupancy_score, x.true_changed_ratio), reverse=True)[:5]
        if not ranked:
            return
        root = self.config.evidence_root / f"frame_{self._frame:06d}"
        root.mkdir(parents=True, exist_ok=True)
        rows = []
        for item in ranked:
            stem = f"cell_{item.cell.x}_{item.cell.y}"
            for suffix, image in (("baseline", item.baseline), ("current", item.crop), ("diff", item.diff), ("mask", item.mask)):
                if image is not None:
                    cv2.imwrite(str(root / f"{stem}_{suffix}.png"), image)
            rows.append({
                "cell": [item.cell.x, item.cell.y],
                "class": item.evidence.category.value,
                "class_confidence": round(item.evidence.similarity, 4),
                "diff_source": item.diff_source.value,
                "true_changed_ratio": round(item.true_changed_ratio, 4),
                "bbox_coverage_ratio": round(item.bbox_coverage_ratio, 4),
                "largest_blob": item.largest_blob_area,
                "occupancy_score": round(item.occupancy_score, 4),
                "danger_prior": round(item.danger_prior, 4),
                "state": item.state.value,
            })
        cv2.imwrite(str(root / "overlay.png"), overlay)
        (root / "metadata.json").write_text(json.dumps({"frame": self._frame, "control_mode": self.mode.value, "active_track": active.track_id if active else None, "cells": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        self._last_save = now
        self._emit(f"PR26_EVIDENCE_SAVED path={root}")

    def filter_candidates(
        self,
        *,
        frame_bgr: np.ndarray,
        state: Any,
        observer: Any,
        candidates: Iterable[CandidateObservation],
        evidence: dict[GridCell, TileEvidence],
        now: float | None = None,
    ) -> tuple[CandidateObservation, ...]:
        timestamp = time.monotonic() if now is None else float(now)
        self._frame += 1
        if self._last_pr24_scan is None:
            self._last_pr24_scan = timestamp
        danger_fresh = timestamp - self._last_pr24_scan <= 0.15
        current = tuple(candidates)
        self.last_evidence = dict(evidence)
        self.last_cells, baseline_ready = self.map.observe(
            frame=frame_bgr,
            state=state,
            candidates=current,
            evidence=evidence,
            danger_fresh=danger_fresh,
        )
        for cell in baseline_ready:
            self._emit(f"PR26_BASELINE_READY cell={cell} diff_source=EXACT_CELL_BASELINE")
        self.last_clusters = self.map.clusters(self.last_cells, current)
        origin = getattr(observer, "grid_origin", (0.0, 0.0))
        player = (float(state.player_center[0]), float(state.player_center[1]))
        player_cell = GridCell(math.floor((player[0] - float(origin[0])) / CELL_SIZE_PX), math.floor((player[1] - float(origin[1])) / CELL_SIZE_PX))
        self._associate(self.last_clusters, timestamp, player, player_cell)
        active = self._active()
        self.last_snapshot = self._snapshot(active)
        overlay = self._overlay(frame_bgr, state, active)
        self.last_overlay_frame = overlay if self.config.overlay_enabled else None
        self._save_evidence(timestamp, overlay, active)
        occupied = sum(item.state is OccupancyState.OCCUPIED for item in self.last_cells.values())
        exact = sum(item.diff_source is DiffSource.EXACT_CELL_BASELINE for item in self.last_cells.values())
        self._emit(f"PR26_OCCUPANCY frame={self._frame} cells={len(self.last_cells)} occupied={occupied} clusters={len(self.last_clusters)} exact_baselines={exact} stored_baselines={len(self.map.exact_baselines)} mode={self.mode.value}")
        if active:
            history = ",".join(f"{v:.1f}" for v in active.pixel_distance_history) or "-"
            self._emit(f"PR26_MOBILE_DANGER id={active.track_id} cells={self._cells_text(active.cells)} foot={active.foot_cell} face={self._face(player, active.foot_point) or '-'} attention_lock={active.attention_lock} face_only_lock={active.face_only_lock} combat_lock={active.combat_lock} danger_score={active.danger_score:.2f} true_changed_ratio={active.true_changed_ratio:.3f} diff_source={active.diff_source.value} pixel_history={history} reason={active.reason}")
        if active is None or active.ambiguous or not active.visible:
            return ()
        if self.mode is PR26ControlMode.PERCEPTION_ONLY:
            return ()
        if self.mode is PR26ControlMode.FACE_ONLY and active.face_only_lock:
            return (self._candidate(active, player),)
        if self.mode is PR26ControlMode.FULL_COMBAT and active.combat_lock:
            return (self._candidate(active, player),)
        return ()


__all__ = [
    "DiffSource",
    "OccupancyConfig",
    "OccupancySnapshot",
    "OccupancyState",
    "PR26ControlMode",
    "PR26OccupancyTracker",
]
