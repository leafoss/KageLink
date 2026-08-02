from __future__ import annotations

import math
import os
import time
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable

import cv2
import numpy as np

from .domain import CELL_SIZE_PX, CandidateObservation, GridCell, ObservationKind
from .tile_perception import TERRAIN_CLASSES, TileClass, TileEvidence


class EntityState(str, Enum):
    TERRAIN_ONLY = "TERRAIN_ONLY"
    DANGER_CANDIDATE = "DANGER_CANDIDATE"
    ENTITY_SUSPECT = "ENTITY_SUSPECT"
    ENTITY_CONFIRMED = "ENTITY_CONFIRMED"
    LOST = "LOST"
    ENDED = "ENDED"


class HostilityState(str, Enum):
    NONE = "NONE"
    OBSERVE_HOSTILITY = "OBSERVE_HOSTILITY"
    HOSTILE_PROBABLE = "HOSTILE_PROBABLE"
    HOSTILE_CONFIRMED = "HOSTILE_CONFIRMED"
    NON_AGGRESSIVE_ENTITY = "NON_AGGRESSIVE_ENTITY"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(default if raw is None or not raw.strip() else raw)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(default if raw is None or not raw.strip() else raw)


@dataclass(frozen=True, slots=True)
class HostilityGateConfig:
    danger_candidate_confidence: float = 0.80
    danger_strong_confidence: float = 0.95
    changed_ratio_suspect: float = 0.08
    changed_ratio_strong: float = 0.12
    largest_blob_min: int = 180
    largest_blob_strong: int = 250
    blob_width_min: int = 8
    blob_height_min: int = 14
    blob_height_strong: int = 18
    persistence_frames: int = 2
    stable_non_aggressive_seconds: float = 3.0
    suspicious_cell_ttl_seconds: float = 5.0
    continuity_cell_jump: int = 1
    continuity_centroid_px: float = 96.0
    pixel_difference_threshold: int = 22
    overlay_enabled: bool = False

    @classmethod
    def from_environment(cls) -> "HostilityGateConfig":
        return cls(
            danger_candidate_confidence=_env_float("KAGE_PR26_DANGER_CONFIDENCE", 0.80),
            danger_strong_confidence=_env_float("KAGE_PR26_DANGER_STRONG", 0.95),
            changed_ratio_suspect=_env_float("KAGE_PR26_CHANGED_RATIO", 0.08),
            changed_ratio_strong=_env_float("KAGE_PR26_CHANGED_RATIO_STRONG", 0.12),
            largest_blob_min=_env_int("KAGE_PR26_BLOB_AREA", 180),
            largest_blob_strong=_env_int("KAGE_PR26_BLOB_AREA_STRONG", 250),
            blob_width_min=_env_int("KAGE_PR26_BLOB_WIDTH", 8),
            blob_height_min=_env_int("KAGE_PR26_BLOB_HEIGHT", 14),
            blob_height_strong=_env_int("KAGE_PR26_BLOB_HEIGHT_STRONG", 18),
            persistence_frames=_env_int("KAGE_PR26_ENTITY_PERSISTENCE", 2),
            stable_non_aggressive_seconds=_env_float("KAGE_PR26_NON_AGGRESSIVE_SECONDS", 3.0),
            suspicious_cell_ttl_seconds=_env_float("KAGE_PR26_SUSPICIOUS_TTL", 5.0),
            overlay_enabled=os.environ.get("KAGE_PR26_HOSTILITY_OVERLAY", "0").strip().lower()
            in {"1", "true", "yes", "on"},
        ).normalized()

    def normalized(self) -> "HostilityGateConfig":
        if not 0.50 <= self.danger_candidate_confidence <= 1.0:
            raise ValueError("danger confidence must be between 0.50 and 1.0")
        if not 0.0 <= self.changed_ratio_suspect <= self.changed_ratio_strong <= 1.0:
            raise ValueError("changed-ratio thresholds are invalid")
        if self.persistence_frames < 2:
            raise ValueError("entity persistence must be at least two frames")
        return self


@dataclass(frozen=True, slots=True)
class StructuralMetrics:
    changed_pixel_ratio: float
    largest_blob_area: int
    blob_width: int
    blob_height: int
    edge_delta: float = 0.0
    structural_similarity: float = 1.0

    @property
    def bbox_text(self) -> str:
        return f"{self.blob_width}x{self.blob_height}"


@dataclass(frozen=True, slots=True)
class GateSnapshot:
    visual_lock: bool = False
    combat_lock: bool = False
    raw_track_id: int | None = None
    cell: GridCell | None = None
    entity_state: EntityState = EntityState.TERRAIN_ONLY
    hostility_state: HostilityState = HostilityState.NONE
    danger_confidence: float = 0.0
    terrain_class: TileClass = TileClass.UNKNOWN
    changed_pixel_ratio: float = 0.0
    largest_blob_area: int = 0
    blob_width: int = 0
    blob_height: int = 0
    persistence: int = 0
    distance_history: tuple[int, ...] = ()
    approach_votes: int = 0
    retreat_votes: int = 0
    reason: str = "no visual entity"

    def as_log_fields(self) -> dict[str, Any]:
        return {
            "visual_lock": self.visual_lock,
            "combat_lock": self.combat_lock,
            "entity_state": self.entity_state.value,
            "hostility_state": self.hostility_state.value,
            "danger_confidence": round(self.danger_confidence, 4),
            "terrain_class": self.terrain_class.value,
            "changed_ratio": round(self.changed_pixel_ratio, 4),
            "largest_blob": self.largest_blob_area,
            "blob_width": self.blob_width,
            "blob_height": self.blob_height,
            "entity_persistence": self.persistence,
            "D_history": list(self.distance_history),
            "approach_votes": self.approach_votes,
            "retreat_votes": self.retreat_votes,
            "hostility_track_id": self.raw_track_id,
            "hostility_reason": self.reason,
        }


@dataclass(slots=True)
class _TrackedEntity:
    key: int
    raw_track_id: int
    cell: GridCell
    first_seen: float
    last_seen: float
    last_centroid: tuple[float, float]
    last_bbox: tuple[int, int, int, int]
    persistence: int = 1
    entity_state: EntityState = EntityState.ENTITY_SUSPECT
    hostility_state: HostilityState = HostilityState.NONE
    visual_lock: bool = False
    combat_lock: bool = False
    danger_confidence: float = 0.0
    terrain_class: TileClass = TileClass.UNKNOWN
    metrics: StructuralMetrics = field(
        default_factory=lambda: StructuralMetrics(0.0, 0, 0, 0)
    )
    distance_history: deque[int] = field(default_factory=lambda: deque(maxlen=5))
    candidate: CandidateObservation | None = None
    reason: str = "new entity suspect"


class PR26HostilityGate:
    """Passive visual lock followed by behavior-based combat authorization.

    Tiles never create offensive candidates. A positive raw visual track must be
    present, survive structural/persistence checks and approach the stationary
    player before it is exposed to PR25 Target Capsule and combat strategy.
    """

    def __init__(self, config: HostilityGateConfig | None = None) -> None:
        self.config = (config or HostilityGateConfig.from_environment()).normalized()
        self._tracks: dict[int, _TrackedEntity] = {}
        self._raw_to_key: dict[int, int] = {}
        self._next_key = 1
        self._cell_baselines: dict[GridCell, np.ndarray] = {}
        self._class_baselines: dict[TileClass, np.ndarray] = {}
        self._console_events: deque[str] = deque()
        self._video_events: deque[str] = deque()
        self.last_snapshot = GateSnapshot()
        self.last_overlay_frame: np.ndarray | None = None
        self.last_evidence: dict[GridCell, TileEvidence] = {}

    @staticmethod
    def _centroid(candidate: CandidateObservation) -> tuple[float, float]:
        if candidate.bbox is not None:
            left, top, width, height = candidate.bbox
            return float(left) + float(width) * 0.5, float(top) + float(height) * 0.5
        if candidate.foot_point is not None:
            return float(candidate.foot_point[0]), float(candidate.foot_point[1])
        return float(candidate.anchor_cell.x * CELL_SIZE_PX), float(candidate.anchor_cell.y * CELL_SIZE_PX)

    @staticmethod
    def _plausible_bbox(candidate: CandidateObservation) -> bool:
        if candidate.bbox is None:
            return False
        _, _, width, height = candidate.bbox
        return 4 <= int(width) <= 96 and 8 <= int(height) <= 192

    @staticmethod
    def _distance_votes(history: Iterable[int]) -> tuple[int, int]:
        values = tuple(int(value) for value in history)
        transitions = tuple(zip(values, values[1:]))[-4:]
        approach = sum(1 for previous, current in transitions if current < previous)
        retreat = sum(1 for previous, current in transitions if current > previous)
        return approach, retreat

    def _emit(self, text: str, video_event: str | None = None) -> None:
        self._console_events.append(text)
        if video_event:
            self._video_events.append(video_event)

    def consume_console_events(self) -> tuple[str, ...]:
        result = tuple(self._console_events)
        self._console_events.clear()
        return result

    def consume_video_events(self) -> tuple[str, ...]:
        result = tuple(self._video_events)
        self._video_events.clear()
        return result

    @staticmethod
    def _crop_for_cell(
        frame_bgr: np.ndarray,
        state: Any,
        evidence: TileEvidence,
    ) -> np.ndarray | None:
        arena_x, arena_y, _, _ = (int(value) for value in state.arena_rect)
        left, top, width, height = evidence.bbox
        crop = frame_bgr[
            arena_y + int(top) : arena_y + int(top + height),
            arena_x + int(left) : arena_x + int(left + width),
        ]
        if crop.shape[:2] != (CELL_SIZE_PX, CELL_SIZE_PX):
            return None
        return crop.copy()

    def _update_baselines(
        self,
        *,
        frame_bgr: np.ndarray,
        state: Any,
        evidence: dict[GridCell, TileEvidence],
        occupied_cells: set[GridCell],
    ) -> None:
        for cell, item in evidence.items():
            if cell in occupied_cells:
                continue
            if item.category not in TERRAIN_CLASSES or item.category is TileClass.DANGER:
                continue
            if item.similarity < 0.90 or item.temporal_activity > 0.008:
                continue
            crop = self._crop_for_cell(frame_bgr, state, item)
            if crop is None:
                continue
            previous = self._cell_baselines.get(cell)
            if previous is None:
                self._cell_baselines[cell] = crop
            else:
                self._cell_baselines[cell] = cv2.addWeighted(previous, 0.95, crop, 0.05, 0.0)
            class_previous = self._class_baselines.get(item.category)
            if class_previous is None:
                self._class_baselines[item.category] = crop
            else:
                self._class_baselines[item.category] = cv2.addWeighted(
                    class_previous, 0.98, crop, 0.02, 0.0
                )

    @staticmethod
    def _candidate_intersection_metrics(
        candidate: CandidateObservation,
        evidence: TileEvidence,
    ) -> StructuralMetrics:
        if candidate.bbox is None:
            return StructuralMetrics(0.0, 0, 0, 0)
        left, top, width, height = (int(value) for value in candidate.bbox)
        cell_left, cell_top, cell_width, cell_height = evidence.bbox
        right = min(left + width, cell_left + cell_width)
        bottom = min(top + height, cell_top + cell_height)
        overlap_width = max(0, right - max(left, cell_left))
        overlap_height = max(0, bottom - max(top, cell_top))
        area = overlap_width * overlap_height
        ratio = float(area) / float(CELL_SIZE_PX * CELL_SIZE_PX)
        return StructuralMetrics(
            changed_pixel_ratio=max(0.0, min(1.0, ratio)),
            largest_blob_area=area,
            blob_width=overlap_width,
            blob_height=overlap_height,
            structural_similarity=max(0.0, 1.0 - ratio),
        )

    def measure_structural_change(
        self,
        *,
        frame_bgr: np.ndarray,
        state: Any,
        candidate: CandidateObservation,
        evidence: TileEvidence,
    ) -> StructuralMetrics:
        current = self._crop_for_cell(frame_bgr, state, evidence)
        fallback = self._candidate_intersection_metrics(candidate, evidence)
        if current is None:
            return fallback
        baseline = self._cell_baselines.get(evidence.cell)
        if baseline is None and evidence.category in self._class_baselines:
            baseline = self._class_baselines[evidence.category]
        if baseline is None or baseline.shape != current.shape:
            return fallback

        current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        baseline_gray = cv2.cvtColor(baseline, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(current_gray, baseline_gray)
        _, mask = cv2.threshold(
            diff,
            int(self.config.pixel_difference_threshold),
            255,
            cv2.THRESH_BINARY,
        )
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        changed_ratio = float(np.count_nonzero(mask)) / float(mask.size)
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        largest_area = 0
        largest_width = 0
        largest_height = 0
        for index in range(1, count):
            _, _, width, height, area = (int(value) for value in stats[index])
            if area > largest_area:
                largest_area = area
                largest_width = width
                largest_height = height

        current_edges = cv2.Canny(current_gray, 45, 135)
        baseline_edges = cv2.Canny(baseline_gray, 45, 135)
        edge_delta = float(np.mean(cv2.absdiff(current_edges, baseline_edges))) / 255.0
        structural_similarity = max(0.0, 1.0 - float(np.mean(diff)) / 255.0)
        return StructuralMetrics(
            changed_pixel_ratio=max(changed_ratio, fallback.changed_pixel_ratio * 0.60),
            largest_blob_area=max(largest_area, round(fallback.largest_blob_area * 0.60)),
            blob_width=max(largest_width, fallback.blob_width),
            blob_height=max(largest_height, fallback.blob_height),
            edge_delta=edge_delta,
            structural_similarity=structural_similarity,
        )

    def _find_track(self, candidate: CandidateObservation, now: float) -> _TrackedEntity | None:
        direct_key = self._raw_to_key.get(int(candidate.track_id))
        if direct_key is not None:
            return self._tracks.get(direct_key)
        centroid = self._centroid(candidate)
        matches: list[tuple[float, _TrackedEntity]] = []
        for track in self._tracks.values():
            if now - track.last_seen > 1.5:
                continue
            cell_jump = track.cell.chebyshev_distance(candidate.anchor_cell)
            if cell_jump > self.config.continuity_cell_jump:
                continue
            center_distance = math.dist(track.last_centroid, centroid)
            if center_distance > self.config.continuity_centroid_px:
                continue
            matches.append((center_distance + cell_jump * CELL_SIZE_PX, track))
        matches.sort(key=lambda item: item[0])
        return matches[0][1] if matches else None

    def _new_track(
        self,
        candidate: CandidateObservation,
        *,
        now: float,
        entity_state: EntityState,
    ) -> _TrackedEntity:
        key = self._next_key
        self._next_key += 1
        bbox = candidate.bbox or (0, 0, 0, 0)
        track = _TrackedEntity(
            key=key,
            raw_track_id=int(candidate.track_id),
            cell=candidate.anchor_cell,
            first_seen=now,
            last_seen=now,
            last_centroid=self._centroid(candidate),
            last_bbox=bbox,
            entity_state=entity_state,
        )
        self._tracks[key] = track
        self._raw_to_key[int(candidate.track_id)] = key
        return track

    def _snapshot_for(self, track: _TrackedEntity | None) -> GateSnapshot:
        if track is None:
            return GateSnapshot()
        approach, retreat = self._distance_votes(track.distance_history)
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
            reason=track.reason,
        )

    def observe_candidate(
        self,
        *,
        candidate: CandidateObservation,
        evidence: TileEvidence,
        metrics: StructuralMetrics,
        player_cell: GridCell,
        now: float,
    ) -> GateSnapshot:
        if int(candidate.track_id) < 0:
            self._emit(
                f"PR26_SYNTHETIC_BLOCKED track={candidate.track_id} cell={candidate.anchor_cell} "
                "reason=SYNTHETIC_CANDIDATES_CANNOT_ACQUIRE_COMBAT_TARGET",
                "SYNTHETIC_CANDIDATE_BLOCKED",
            )
            return GateSnapshot(
                raw_track_id=int(candidate.track_id),
                cell=candidate.anchor_cell,
                entity_state=EntityState.TERRAIN_ONLY,
                reason="negative synthetic candidate blocked",
            )

        danger_confidence = (
            float(evidence.similarity) if evidence.category is TileClass.DANGER else 0.0
        )
        danger_candidate = danger_confidence >= self.config.danger_candidate_confidence
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
        terrain_reference_confident = (
            evidence.category in TERRAIN_CLASSES
            and float(evidence.similarity) >= self.config.danger_candidate_confidence
        )
        eligible = (
            candidate.visible
            and self._plausible_bbox(candidate)
            and (danger_candidate or (terrain_reference_confident and structural_suspect))
        )
        if not eligible:
            self._emit(
                f"PR26_REJECT track={candidate.track_id} cell={candidate.anchor_cell} "
                f"class={evidence.category.value} confidence={evidence.similarity:.2f} "
                f"reason=FLOOR_NOISE changed_ratio={metrics.changed_pixel_ratio:.3f} "
                f"largest_blob={metrics.largest_blob_area}"
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
                reason="floor/noise or weak visual evidence rejected",
            )

        initial_state = (
            EntityState.DANGER_CANDIDATE if danger_candidate else EntityState.ENTITY_SUSPECT
        )
        track = self._find_track(candidate, now)
        centroid = self._centroid(candidate)
        if track is None:
            track = self._new_track(candidate, now=now, entity_state=initial_state)
            self._emit(
                f"PR26_TILE_CLASS cell={candidate.anchor_cell} class={evidence.category.value.upper()} "
                f"confidence={evidence.similarity:.2f} changed_ratio={metrics.changed_pixel_ratio:.3f} "
                f"largest_blob={metrics.largest_blob_area} bbox={metrics.bbox_text}",
                "DANGER_FIRST_SEEN",
            )
        else:
            continuous = (
                track.cell.chebyshev_distance(candidate.anchor_cell)
                <= self.config.continuity_cell_jump
                and math.dist(track.last_centroid, centroid)
                <= self.config.continuity_centroid_px
            )
            track.persistence = track.persistence + 1 if continuous else 1
            if track.raw_track_id != int(candidate.track_id):
                self._raw_to_key.pop(track.raw_track_id, None)
                track.raw_track_id = int(candidate.track_id)
                self._raw_to_key[track.raw_track_id] = track.key

        previous_visual = track.visual_lock
        previous_combat = track.combat_lock
        previous_entity = track.entity_state
        previous_hostility = track.hostility_state
        track.cell = candidate.anchor_cell
        track.last_seen = now
        track.last_centroid = centroid
        track.last_bbox = candidate.bbox or track.last_bbox
        track.candidate = candidate
        track.danger_confidence = danger_confidence
        track.terrain_class = evidence.category
        track.metrics = metrics

        if track.persistence >= self.config.persistence_frames and (
            danger_candidate or structural_strong
        ):
            track.entity_state = EntityState.ENTITY_CONFIRMED
            track.visual_lock = True
            if track.hostility_state is HostilityState.NONE:
                track.hostility_state = HostilityState.OBSERVE_HOSTILITY
            if previous_entity is not EntityState.ENTITY_CONFIRMED:
                self._emit(
                    f"PR26_ENTITY_STATE track={track.raw_track_id} cell={track.cell} "
                    f"state=ENTITY_CONFIRMED persistence={track.persistence} "
                    "source=PR24_DANGER_PLUS_STRUCTURE",
                    "ENTITY_CONFIRMED",
                )
                self._emit(
                    f"PR26_HOSTILITY_OBSERVE track={track.raw_track_id} D_history=- "
                    "approach_votes=0 retreat_votes=0 state=OBSERVE_HOSTILITY",
                    "HOSTILITY_OBSERVATION_STARTED",
                )
        else:
            track.entity_state = initial_state
            track.reason = "waiting for persistent entity evidence"

        if track.visual_lock:
            distance = player_cell.chebyshev_distance(candidate.anchor_cell)
            track.distance_history.append(distance)
            approach, retreat = self._distance_votes(track.distance_history)
            if distance == 0 and candidate.visible:
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
            else:
                stable_seconds = now - track.first_seen
                distances = tuple(track.distance_history)
                stable_range = max(distances) - min(distances) if distances else 0
                if (
                    stable_seconds >= self.config.stable_non_aggressive_seconds
                    and len(distances) >= 3
                    and approach == 0
                    and stable_range <= 1
                ):
                    track.hostility_state = HostilityState.NON_AGGRESSIVE_ENTITY
                    track.reason = "distance remained stable during passive observation"
                else:
                    track.hostility_state = HostilityState.OBSERVE_HOSTILITY
                    track.reason = "passive visual lock; waiting for autonomous approach"

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
                f"observed_seconds={now - track.first_seen:.2f} reason=DISTANCE_STABLE",
                "NON_AGGRESSIVE_CLASSIFIED",
            )

        approach, retreat = self._distance_votes(track.distance_history)
        if track.visual_lock:
            self._emit(
                f"PR26_HOSTILITY_OBSERVE track={track.raw_track_id} "
                f"D_history={','.join(str(value) for value in track.distance_history)} "
                f"approach_votes={approach} retreat_votes={retreat} "
                f"state={track.hostility_state.value}"
            )
        return self._snapshot_for(track)

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
        occupied_cells = {
            cell for candidate in current for cell in candidate.cells_touched
        }
        self._update_baselines(
            frame_bgr=frame_bgr,
            state=state,
            evidence=evidence,
            occupied_cells=occupied_cells,
        )
        raw_origin = getattr(observer, "grid_origin", (0.0, 0.0))
        player_x, player_y = (float(value) for value in state.player_center)
        player_cell = GridCell(
            math.floor((player_x - float(raw_origin[0])) / CELL_SIZE_PX),
            math.floor((player_y - float(raw_origin[1])) / CELL_SIZE_PX),
        )

        snapshots: list[GateSnapshot] = []
        authorized: list[CandidateObservation] = []
        for candidate in current:
            if int(candidate.track_id) < 0:
                synthetic_evidence = evidence.get(candidate.anchor_cell)
                if synthetic_evidence is not None:
                    snapshots.append(
                        self.observe_candidate(
                            candidate=candidate,
                            evidence=synthetic_evidence,
                            metrics=StructuralMetrics(0.0, 0, 0, 0),
                            player_cell=player_cell,
                            now=timestamp,
                        )
                    )
                continue
            matching = [
                evidence[cell] for cell in candidate.cells_touched if cell in evidence
            ]
            if not matching and candidate.anchor_cell in evidence:
                matching = [evidence[candidate.anchor_cell]]
            if not matching:
                continue
            item = max(
                matching,
                key=lambda value: (
                    value.category is TileClass.DANGER,
                    value.similarity,
                    value.temporal_activity,
                ),
            )
            metrics = self.measure_structural_change(
                frame_bgr=frame_bgr,
                state=state,
                candidate=candidate,
                evidence=item,
            )
            snapshot = self.observe_candidate(
                candidate=candidate,
                evidence=item,
                metrics=metrics,
                player_cell=player_cell,
                now=timestamp,
            )
            snapshots.append(snapshot)
            if snapshot.combat_lock:
                authorized.append(
                    replace(
                        candidate,
                        kind=ObservationKind.CLEAN_BODY,
                        body_like=True,
                        cells_touched=frozenset({candidate.anchor_cell}),
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
        ranked_tracks = sorted(
            self._tracks.values(),
            key=lambda track: (
                not track.combat_lock,
                not track.visual_lock,
                -track.persistence,
                track.distance_history[-1] if track.distance_history else 999,
                -track.danger_confidence,
            ),
        )
        self.last_snapshot = self._snapshot_for(ranked_tracks[0] if ranked_tracks else None)
        self.last_evidence = dict(evidence)
        if self.config.overlay_enabled:
            self.last_overlay_frame = self.annotate_frame(
                frame_bgr,
                state=state,
                evidence=evidence,
            )
        else:
            self.last_overlay_frame = None

        authorized.sort(
            key=lambda candidate: (
                player_cell.chebyshev_distance(candidate.anchor_cell),
                -float(candidate.identity_score),
                int(candidate.track_id),
            )
        )
        return tuple(authorized)

    def annotate_frame(
        self,
        frame_bgr: np.ndarray,
        *,
        state: Any,
        evidence: dict[GridCell, TileEvidence],
    ) -> np.ndarray:
        annotated = frame_bgr.copy()
        arena_x, arena_y, _, _ = (int(value) for value in state.arena_rect)
        for cell, item in evidence.items():
            if item.category not in {TileClass.DANGER, TileClass.UNKNOWN}:
                continue
            left, top, width, height = item.bbox
            x1, y1 = arena_x + left, arena_y + top
            x2, y2 = x1 + width, y1 + height
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 1)
            cv2.putText(
                annotated,
                f"{item.category.value}:{item.similarity:.2f}",
                (x1 + 2, y1 + 13),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (0, 0, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                annotated,
                f"{item.category.value}:{item.similarity:.2f}",
                (x1 + 2, y1 + 13),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
        snapshot = self.last_snapshot
        text = (
            f"VISUAL={snapshot.visual_lock} COMBAT={snapshot.combat_lock} "
            f"ENTITY={snapshot.entity_state.value} HOST={snapshot.hostility_state.value} "
            f"D={list(snapshot.distance_history)}"
        )
        cv2.putText(
            annotated,
            text,
            (10, max(20, annotated.shape[0] - 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            text,
            (10, max(20, annotated.shape[0] - 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        return annotated


__all__ = [
    "EntityState",
    "GateSnapshot",
    "HostilityGateConfig",
    "HostilityState",
    "PR26HostilityGate",
    "StructuralMetrics",
]
