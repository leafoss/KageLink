from __future__ import annotations

import math
import os
import time
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

import numpy as np

from .domain import CELL_SIZE_PX, CandidateObservation, GridCell, ObservationKind
from .hostility_gate import (
    EntityState,
    GateSnapshot,
    HostilityState,
    PR26HostilityGate,
    StructuralMetrics,
)
from .tile_perception import TERRAIN_CLASSES, TileClass, TileEvidence


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(default if raw is None or not raw.strip() else raw)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(default if raw is None or not raw.strip() else raw)


@dataclass(slots=True)
class _ContinuityTrack:
    key: int
    raw_track_id: int
    cell: GridCell
    first_seen: float
    last_seen: float
    last_centroid: tuple[float, float]
    last_bbox: tuple[int, int, int, int]
    entity_state: EntityState
    entity_votes: deque[bool] = field(default_factory=lambda: deque(maxlen=3))
    distance_history: deque[int] = field(default_factory=lambda: deque(maxlen=5))
    hostility_state: HostilityState = HostilityState.NONE
    visual_lock: bool = False
    combat_lock: bool = False
    danger_memory_until: float = 0.0
    max_danger_confidence: float = 0.0
    danger_confidence: float = 0.0
    terrain_class: TileClass = TileClass.UNKNOWN
    metrics: StructuralMetrics = field(
        default_factory=lambda: StructuralMetrics(0.0, 0, 0, 0)
    )
    candidate: CandidateObservation | None = None
    reason: str = "new entity suspect"

    @property
    def persistence(self) -> int:
        return sum(1 for value in self.entity_votes if value)


class PR26ContinuityHostilityGate(PR26HostilityGate):
    """PR26.2 hostility gate resilient to real capture oscillation.

    New tracks still require a positive raw ID plus a PR24 DANGER seed (or a
    strong structural change over confidently known terrain). Existing tracks
    are evaluated before rejection, retain DANGER memory briefly, and confirm
    entity presence with two positive votes inside the last three frames.
    """

    def __init__(self) -> None:
        super().__init__()
        self._tracks: dict[int, _ContinuityTrack] = {}
        self._raw_to_key: dict[int, int] = {}
        self._next_key = 1
        self._danger_memory_seconds = _env_float(
            "KAGE_PR26_DANGER_MEMORY_SECONDS", 1.25
        )
        self._evidence_window = max(3, _env_int("KAGE_PR26_EVIDENCE_WINDOW", 3))
        self._evidence_votes_required = max(
            2, _env_int("KAGE_PR26_EVIDENCE_VOTES", 2)
        )
        self._direct_cell_jump = max(
            self.config.continuity_cell_jump,
            _env_int("KAGE_PR26_DIRECT_CELL_JUMP", 2),
        )
        self._direct_centroid_px = max(
            self.config.continuity_centroid_px,
            _env_float("KAGE_PR26_DIRECT_CENTROID_PX", 128.0),
        )
        if self._danger_memory_seconds <= 0.0:
            raise ValueError("danger memory must be positive")
        if self._evidence_votes_required > self._evidence_window:
            raise ValueError("evidence votes cannot exceed evidence window")

    @staticmethod
    def _entity_cell(
        candidate: CandidateObservation,
        origin: tuple[float, float] | None,
    ) -> GridCell:
        if origin is None:
            return candidate.anchor_cell
        origin_x, origin_y = (float(value) for value in origin)
        if candidate.foot_point is not None:
            foot_x, foot_y = (float(value) for value in candidate.foot_point)
        elif candidate.bbox is not None:
            left, top, width, height = (float(value) for value in candidate.bbox)
            foot_x = left + width * 0.5
            foot_y = top + height
        else:
            return candidate.anchor_cell
        return GridCell(
            math.floor((foot_x - origin_x) / CELL_SIZE_PX),
            math.floor((foot_y - origin_y) / CELL_SIZE_PX),
        )

    @staticmethod
    def _bbox_plausible(bbox: tuple[int, int, int, int] | None) -> bool:
        if bbox is None:
            return False
        _, _, width, height = bbox
        return 4 <= int(width) <= 96 and 8 <= int(height) <= 192

    def _find_track(
        self,
        candidate: CandidateObservation,
        entity_cell: GridCell,
        now: float,
    ) -> tuple[_ContinuityTrack | None, bool]:
        direct_key = self._raw_to_key.get(int(candidate.track_id))
        if direct_key is not None and direct_key in self._tracks:
            return self._tracks[direct_key], True

        centroid = self._centroid(candidate)
        matches: list[tuple[float, _ContinuityTrack]] = []
        for track in self._tracks.values():
            if now - track.last_seen > 1.5:
                continue
            cell_jump = track.cell.chebyshev_distance(entity_cell)
            if cell_jump > self.config.continuity_cell_jump:
                continue
            center_distance = math.dist(track.last_centroid, centroid)
            if center_distance > self.config.continuity_centroid_px:
                continue
            matches.append((center_distance + cell_jump * CELL_SIZE_PX, track))
        matches.sort(key=lambda item: item[0])
        return (matches[0][1], False) if matches else (None, False)

    def _continuity_valid(
        self,
        track: _ContinuityTrack,
        candidate: CandidateObservation,
        entity_cell: GridCell,
        direct_id: bool,
    ) -> bool:
        cell_limit = self._direct_cell_jump if direct_id else self.config.continuity_cell_jump
        centroid_limit = (
            self._direct_centroid_px if direct_id else self.config.continuity_centroid_px
        )
        return (
            track.cell.chebyshev_distance(entity_cell) <= cell_limit
            and math.dist(track.last_centroid, self._centroid(candidate)) <= centroid_limit
        )

    def _new_track(
        self,
        candidate: CandidateObservation,
        entity_cell: GridCell,
        now: float,
        entity_state: EntityState,
    ) -> _ContinuityTrack:
        key = self._next_key
        self._next_key += 1
        track = _ContinuityTrack(
            key=key,
            raw_track_id=int(candidate.track_id),
            cell=entity_cell,
            first_seen=now,
            last_seen=now,
            last_centroid=self._centroid(candidate),
            last_bbox=candidate.bbox or (0, 0, 0, 0),
            entity_state=entity_state,
            entity_votes=deque(maxlen=self._evidence_window),
        )
        self._tracks[key] = track
        self._raw_to_key[track.raw_track_id] = key
        return track

    def _snapshot_for(
        self,
        track: _ContinuityTrack | None,
        now: float | None = None,
    ) -> GateSnapshot:
        if track is None:
            return GateSnapshot()
        approach, retreat = self._distance_votes(track.distance_history)
        vote_text = "".join("1" if value else "0" for value in track.entity_votes) or "-"
        timestamp = time.monotonic() if now is None else float(now)
        memory = timestamp <= track.danger_memory_until
        reason = f"{track.reason}; votes={vote_text}; danger_recent={memory}"
        return GateSnapshot(
            visual_lock=track.visual_lock,
            combat_lock=track.combat_lock,
            raw_track_id=track.raw_track_id,
            cell=track.cell,
            entity_state=track.entity_state,
            hostility_state=track.hostility_state,
            danger_confidence=track.danger_confidence,
            terrain_class=track.terrain_class,
            changed_pixel_ratio=track.metrics.changed_pixel_ratio,
            largest_blob_area=track.metrics.largest_blob_area,
            blob_width=track.metrics.blob_width,
            blob_height=track.metrics.blob_height,
            persistence=track.persistence,
            distance_history=tuple(track.distance_history),
            approach_votes=approach,
            retreat_votes=retreat,
            reason=reason,
        )

    def _reject(
        self,
        candidate: CandidateObservation,
        evidence: TileEvidence,
        metrics: StructuralMetrics,
        reason: str,
        track: _ContinuityTrack | None,
        now: float,
    ) -> GateSnapshot:
        memory = bool(track is not None and now <= track.danger_memory_until)
        vote_text = (
            "-"
            if track is None
            else "".join("1" if value else "0" for value in track.entity_votes)
        )
        self._emit(
            f"PR26_REJECT track={candidate.track_id} cell={candidate.anchor_cell} "
            f"class={evidence.category.value} confidence={evidence.similarity:.2f} "
            f"reason={reason} visible={candidate.visible} "
            f"bbox_plausible={self._bbox_plausible(candidate.bbox)} "
            f"danger_recent={memory} votes={vote_text or '-'} "
            f"changed_ratio={metrics.changed_pixel_ratio:.3f} "
            f"largest_blob={metrics.largest_blob_area}"
        )
        if track is not None:
            return self._snapshot_for(track, now)
        danger_confidence = (
            float(evidence.similarity) if evidence.category is TileClass.DANGER else 0.0
        )
        return GateSnapshot(
            raw_track_id=int(candidate.track_id),
            cell=candidate.anchor_cell,
            terrain_class=evidence.category,
            danger_confidence=danger_confidence,
            changed_pixel_ratio=metrics.changed_pixel_ratio,
            largest_blob_area=metrics.largest_blob_area,
            blob_width=metrics.blob_width,
            blob_height=metrics.blob_height,
            reason=reason,
        )

    def observe_candidate(
        self,
        *,
        candidate: CandidateObservation,
        evidence: TileEvidence,
        metrics: StructuralMetrics,
        player_cell: GridCell,
        now: float,
        entity_cell: GridCell | None = None,
    ) -> GateSnapshot:
        resolved_cell = candidate.anchor_cell if entity_cell is None else entity_cell
        if int(candidate.track_id) < 0:
            self._emit(
                f"PR26_SYNTHETIC_BLOCKED track={candidate.track_id} cell={resolved_cell} "
                "reason=SYNTHETIC_CANDIDATES_CANNOT_ACQUIRE_COMBAT_TARGET",
                "SYNTHETIC_CANDIDATE_BLOCKED",
            )
            return GateSnapshot(
                raw_track_id=int(candidate.track_id),
                cell=resolved_cell,
                entity_state=EntityState.TERRAIN_ONLY,
                reason="negative synthetic candidate blocked",
            )

        track, direct_id = self._find_track(candidate, resolved_cell, now)
        if track is not None and not self._continuity_valid(
            track, candidate, resolved_cell, direct_id
        ):
            return self._reject(
                candidate, evidence, metrics, "CONTINUITY_FAILED", track, now
            )

        danger_now_confidence = (
            float(evidence.similarity) if evidence.category is TileClass.DANGER else 0.0
        )
        danger_now = danger_now_confidence >= self.config.danger_candidate_confidence
        structural_suspect = (
            metrics.changed_pixel_ratio >= self.config.changed_ratio_suspect
            and metrics.largest_blob_area >= self.config.largest_blob_min
            and metrics.blob_width >= self.config.blob_width_min
            and metrics.blob_height >= self.config.blob_height_min
        )
        structural_strong = (
            metrics.changed_pixel_ratio >= self.config.changed_ratio_strong
            and metrics.largest_blob_area >= self.config.largest_blob_strong
            and metrics.blob_height >= self.config.blob_height_strong
        )
        known_terrain = (
            evidence.category in TERRAIN_CLASSES
            and evidence.category is not TileClass.DANGER
            and float(evidence.similarity) >= self.config.danger_candidate_confidence
        )

        if track is None:
            if not candidate.visible:
                return self._reject(
                    candidate, evidence, metrics, "NEW_TRACK_NOT_VISIBLE", None, now
                )
            if not self._bbox_plausible(candidate.bbox):
                return self._reject(
                    candidate, evidence, metrics, "NEW_TRACK_IMPLAUSIBLE_BBOX", None, now
                )
            acquire = (
                (danger_now and structural_suspect)
                or (known_terrain and structural_strong)
            )
            if not acquire:
                reason = "NO_DANGER_SEED"
                if danger_now:
                    reason = "DANGER_STRUCTURE_TOO_WEAK"
                elif known_terrain:
                    reason = "KNOWN_TERRAIN_STRUCTURE_TOO_WEAK"
                return self._reject(candidate, evidence, metrics, reason, None, now)
            initial = (
                EntityState.DANGER_CANDIDATE
                if danger_now
                else EntityState.ENTITY_SUSPECT
            )
            track = self._new_track(candidate, resolved_cell, now, initial)
            self._emit(
                f"PR26_TILE_CLASS cell={resolved_cell} "
                f"class={evidence.category.value.upper()} "
                f"confidence={evidence.similarity:.2f} "
                f"changed_ratio={metrics.changed_pixel_ratio:.3f} "
                f"largest_blob={metrics.largest_blob_area} bbox={metrics.bbox_text}",
                "DANGER_FIRST_SEEN",
            )

        previous_entity = track.entity_state
        previous_visual = track.visual_lock
        previous_hostility = track.hostility_state
        previous_combat = track.combat_lock

        if danger_now:
            track.max_danger_confidence = max(
                track.max_danger_confidence, danger_now_confidence
            )
            track.danger_memory_until = max(
                track.danger_memory_until, now + self._danger_memory_seconds
            )
        danger_recent = now <= track.danger_memory_until
        bbox_usable = self._bbox_plausible(candidate.bbox) or self._bbox_plausible(
            track.last_bbox
        )
        evidence_valid = (
            candidate.visible
            and bbox_usable
            and (
                ((danger_now or danger_recent) and structural_suspect)
                or (danger_recent and structural_strong)
            )
        )
        track.entity_votes.append(bool(evidence_valid))

        if track.raw_track_id != int(candidate.track_id):
            self._raw_to_key.pop(track.raw_track_id, None)
            track.raw_track_id = int(candidate.track_id)
            self._raw_to_key[track.raw_track_id] = track.key
        track.cell = resolved_cell
        track.last_seen = now
        track.last_centroid = self._centroid(candidate)
        if candidate.bbox is not None:
            track.last_bbox = candidate.bbox
        track.candidate = candidate
        track.terrain_class = evidence.category
        track.metrics = metrics
        track.danger_confidence = (
            max(track.max_danger_confidence, danger_now_confidence)
            if danger_recent
            else danger_now_confidence
        )

        confirmed = (
            danger_recent
            and len(track.entity_votes) >= self._evidence_votes_required
            and track.persistence >= self._evidence_votes_required
        )
        if confirmed:
            track.entity_state = EntityState.ENTITY_CONFIRMED
            track.visual_lock = True
            if track.hostility_state is HostilityState.NONE:
                track.hostility_state = HostilityState.OBSERVE_HOSTILITY
            if previous_entity is not EntityState.ENTITY_CONFIRMED:
                votes = "".join("1" if value else "0" for value in track.entity_votes)
                self._emit(
                    f"PR26_ENTITY_STATE track={track.raw_track_id} cell={track.cell} "
                    f"state=ENTITY_CONFIRMED persistence={track.persistence} "
                    f"votes={votes} source=PR24_DANGER_MEMORY_PLUS_STRUCTURE",
                    "ENTITY_CONFIRMED",
                )
                self._emit(
                    f"PR26_HOSTILITY_OBSERVE track={track.raw_track_id} "
                    "D_history=- approach_votes=0 retreat_votes=0 "
                    "state=OBSERVE_HOSTILITY",
                    "HOSTILITY_OBSERVATION_STARTED",
                )
        elif not track.visual_lock:
            track.entity_state = (
                EntityState.DANGER_CANDIDATE
                if danger_recent
                else EntityState.ENTITY_SUSPECT
            )
            track.reason = (
                "waiting for 2-of-3 persistent entity evidence"
                if candidate.visible
                else "waiting through transient visibility loss"
            )

        if track.visual_lock and candidate.visible and evidence_valid:
            distance = player_cell.chebyshev_distance(resolved_cell)
            track.distance_history.append(distance)
            approach, _ = self._distance_votes(track.distance_history)
            if distance == 0:
                track.hostility_state = HostilityState.HOSTILE_CONFIRMED
                track.combat_lock = True
                track.reason = "visible entity reached D=0 autonomously"
            elif distance <= 1 and approach >= 1:
                track.hostility_state = HostilityState.HOSTILE_CONFIRMED
                track.combat_lock = True
                track.reason = "visible entity reached D<=1 after autonomous approach"
            elif approach >= 3:
                track.hostility_state = HostilityState.HOSTILE_PROBABLE
                track.reason = "three coherent distance reductions observed"
            elif track.hostility_state is not HostilityState.HOSTILE_PROBABLE:
                distances = tuple(track.distance_history)
                stable_range = max(distances) - min(distances) if distances else 0
                if (
                    now - track.first_seen
                    >= self.config.stable_non_aggressive_seconds
                    and len(distances) >= 3
                    and approach == 0
                    and stable_range <= 1
                ):
                    track.hostility_state = HostilityState.NON_AGGRESSIVE_ENTITY
                    track.reason = "distance remained stable during passive observation"
                else:
                    track.hostility_state = HostilityState.OBSERVE_HOSTILITY
                    track.reason = "passive visual lock; waiting for autonomous approach"
        elif track.visual_lock and not track.combat_lock:
            track.reason = "visual lock retained through transient weak/occluded frame"

        if track.visual_lock != previous_visual:
            self._emit(
                f"PR26_VISUAL_LOCK track={track.raw_track_id} active={track.visual_lock}",
                "VISUAL_LOCK_CHANGED",
            )
        if track.combat_lock != previous_combat:
            self._emit(
                f"PR26_COMBAT_LOCK track={track.raw_track_id} active={track.combat_lock} "
                f"reason={track.reason}",
                "COMBAT_LOCK_CHANGED",
            )
        if (
            track.hostility_state is HostilityState.HOSTILE_CONFIRMED
            and previous_hostility is not HostilityState.HOSTILE_CONFIRMED
        ):
            self._emit(
                f"PR26_HOSTILITY_CONFIRMED track={track.raw_track_id} "
                f"D={track.distance_history[-1]} reason={track.reason}",
                "HOSTILE_CONFIRMED",
            )
        elif (
            track.hostility_state is HostilityState.NON_AGGRESSIVE_ENTITY
            and previous_hostility is not HostilityState.NON_AGGRESSIVE_ENTITY
        ):
            self._emit(
                f"PR26_NON_AGGRESSIVE track={track.raw_track_id} "
                f"observed_seconds={now - track.first_seen:.2f} "
                "reason=DISTANCE_STABLE",
                "NON_AGGRESSIVE_CLASSIFIED",
            )

        if track.visual_lock:
            approach, retreat = self._distance_votes(track.distance_history)
            votes = "".join("1" if value else "0" for value in track.entity_votes)
            history = ",".join(str(value) for value in track.distance_history) or "-"
            self._emit(
                f"PR26_HOSTILITY_OBSERVE track={track.raw_track_id} "
                f"D_history={history} approach_votes={approach} "
                f"retreat_votes={retreat} danger_recent={danger_recent} "
                f"votes={votes} state={track.hostility_state.value}"
            )
        return self._snapshot_for(track, now)

    @staticmethod
    def _evidence_for_candidate(
        candidate: CandidateObservation,
        entity_cell: GridCell,
        evidence: dict[GridCell, TileEvidence],
    ) -> TileEvidence | None:
        cells = set(candidate.cells_touched)
        cells.add(candidate.anchor_cell)
        cells.add(entity_cell)
        matching = [evidence[cell] for cell in cells if cell in evidence]
        if not matching:
            matching = [
                item
                for cell, item in evidence.items()
                if cell.chebyshev_distance(entity_cell) <= 1
            ]
        if not matching:
            return None
        return max(
            matching,
            key=lambda item: (
                item.category is TileClass.DANGER,
                -item.cell.chebyshev_distance(entity_cell),
                item.similarity,
                item.temporal_activity,
            ),
        )

    def _expire_tracks(self, now: float) -> None:
        expired = [
            key
            for key, track in self._tracks.items()
            if now - track.last_seen > self.config.suspicious_cell_ttl_seconds
        ]
        for key in expired:
            track = self._tracks.pop(key)
            self._raw_to_key.pop(track.raw_track_id, None)

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
        current = tuple(candidates)
        raw_origin = getattr(observer, "grid_origin", (0.0, 0.0))
        entity_cells = {
            self._entity_cell(candidate, raw_origin) for candidate in current
        }
        occupied_cells = {
            cell for candidate in current for cell in candidate.cells_touched
        } | entity_cells
        self._update_baselines(
            frame_bgr=frame_bgr,
            state=state,
            evidence=evidence,
            occupied_cells=occupied_cells,
        )
        player_x, player_y = (float(value) for value in state.player_center)
        player_cell = GridCell(
            math.floor((player_x - float(raw_origin[0])) / CELL_SIZE_PX),
            math.floor((player_y - float(raw_origin[1])) / CELL_SIZE_PX),
        )

        authorized: list[CandidateObservation] = []
        for candidate in current:
            entity_cell = self._entity_cell(candidate, raw_origin)
            item = self._evidence_for_candidate(candidate, entity_cell, evidence)
            if item is None:
                self._emit(
                    f"PR26_REJECT track={candidate.track_id} cell={entity_cell} "
                    "reason=NO_TILE_EVIDENCE"
                )
                continue
            metrics = (
                StructuralMetrics(0.0, 0, 0, 0)
                if int(candidate.track_id) < 0
                else self.measure_structural_change(
                    frame_bgr=frame_bgr,
                    state=state,
                    candidate=candidate,
                    evidence=item,
                )
            )
            snapshot = self.observe_candidate(
                candidate=candidate,
                evidence=item,
                metrics=metrics,
                player_cell=player_cell,
                entity_cell=entity_cell,
                now=timestamp,
            )
            if snapshot.combat_lock:
                authorized.append(
                    replace(
                        candidate,
                        anchor_cell=entity_cell,
                        kind=ObservationKind.CLEAN_BODY,
                        body_like=True,
                        cells_touched=frozenset({entity_cell}),
                        confidence=max(
                            float(candidate.confidence),
                            float(snapshot.danger_confidence),
                            0.80,
                        ),
                        identity_score=max(float(candidate.identity_score), 0.70),
                        appearance_score=max(float(candidate.appearance_score), 0.70),
                        background_probability=min(
                            float(candidate.background_probability), 0.20
                        ),
                    )
                )

        self._expire_tracks(timestamp)
        ranked = sorted(
            self._tracks.values(),
            key=lambda track: (
                not track.combat_lock,
                not track.visual_lock,
                -track.persistence,
                track.distance_history[-1] if track.distance_history else 999,
                -track.danger_confidence,
            ),
        )
        self.last_snapshot = self._snapshot_for(ranked[0] if ranked else None, timestamp)
        self.last_evidence = dict(evidence)
        self.last_overlay_frame = (
            self.annotate_frame(frame_bgr, state=state, evidence=evidence)
            if self.config.overlay_enabled
            else None
        )
        authorized.sort(
            key=lambda candidate: (
                player_cell.chebyshev_distance(candidate.anchor_cell),
                -float(candidate.identity_score),
                int(candidate.track_id),
            )
        )
        return tuple(authorized)


__all__ = ["PR26ContinuityHostilityGate"]
