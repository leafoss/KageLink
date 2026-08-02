from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field, is_dataclass, replace
from types import SimpleNamespace
from typing import Any, Iterable

from .domain import CELL_SIZE_PX, CandidateObservation, GridCell, ObservationKind
from .hostility_gate import EntityState, HostilityState
from .occupancy_model import DiffSource, OccupancyCluster, PR26ControlMode


_TRACKING_INSTALLED = False
_PHYSICAL_INSTALLED = False
_TARGET_MEMORY_PATCHED = False
_ACTIVE_TARGET_MEMORY: Any | None = None
_TARGET_ENRICH_ORIGINAL: Any | None = None

_LOCAL_RADIUS_STEP_1_SECONDS = 2.5
_LOCAL_RADIUS_STEP_2_SECONDS = 7.0
_LOCAL_RADIUS_MAX_CELLS = 3
_REID_VOTES_REQUIRED = 2
_REID_IDENTITY_MIN = 0.68
_REID_APPEARANCE_MIN = 0.45
_REID_BACKGROUND_MAX = 0.72
_PERSISTENT_REID_SECONDS = 90.0


@dataclass(slots=True)
class _RoundTargetMemory:
    track: Any
    track_id: int
    latched_at: float
    last_visual_at: float
    foot_point: tuple[float, float]
    foot_cell: GridCell
    cells: frozenset[GridCell]
    bbox: tuple[int, int, int, int]
    camera_dx: float
    camera_dy: float
    last_raw_track_id: int | None = None
    authority: str = "VISUAL_CLUSTER"
    outside_radius_votes: int = 0
    reid_votes: deque[bool] = field(default_factory=lambda: deque(maxlen=3))
    reid_key: tuple[Any, ...] | None = None
    last_event_key: tuple[Any, ...] | None = None


def progressive_reid_radius(missing_seconds: float) -> int:
    """Expand local ReID from D1 to D3 without ever scanning beyond D3."""

    value = max(0.0, float(missing_seconds))
    if value <= _LOCAL_RADIUS_STEP_1_SECONDS:
        return 1
    if value <= _LOCAL_RADIUS_STEP_2_SECONDS:
        return 2
    return _LOCAL_RADIUS_MAX_CELLS


def contact_player_rect(state: Any) -> tuple[int, int, int, int]:
    """Return the smaller player core used after the hostile target is latched.

    Initial acquisition keeps the larger player exclusion mask. During confirmed
    contact that mask can erase both overlapping sprites, so the continuity path
    removes only the player's core and leaves surrounding enemy pixels available.
    """

    center_x, center_y = (float(value) for value in state.player_center)
    width, height, margin = 18, 38, 2
    return (
        int(round(center_x - width / 2.0)) - margin,
        int(round(center_y - height / 2.0)) - margin,
        width + margin * 2,
        height + margin * 2,
    )


def _candidate_foot(candidate: CandidateObservation) -> tuple[float, float] | None:
    if candidate.foot_point is not None:
        return float(candidate.foot_point[0]), float(candidate.foot_point[1])
    if candidate.bbox is None:
        return None
    left, top, width, height = candidate.bbox
    return float(left + width / 2.0), float(top + height)


def capsule_reid_matches(
    candidate: CandidateObservation,
    *,
    player_cell: GridCell,
    predicted_foot: tuple[float, float],
    radius_cells: int,
) -> bool:
    """Require Target Capsule evidence, compact geometry and D<=3 locality."""

    if (
        not candidate.visible
        or not candidate.body_like
        or candidate.bbox is None
        or candidate.background_probability >= _REID_BACKGROUND_MAX
    ):
        return False
    if player_cell.chebyshev_distance(candidate.anchor_cell) > _LOCAL_RADIUS_MAX_CELLS:
        return False
    if candidate.identity_score < _REID_IDENTITY_MIN:
        return False
    if candidate.appearance_score < _REID_APPEARANCE_MIN:
        return False
    if not (candidate.reidentified or candidate.is_target_body):
        return False

    _, _, width, height = (int(value) for value in candidate.bbox)
    if not (8 <= width <= 84 and 16 <= height <= 112):
        return False
    if width >= 96 or (width >= 80 and height <= 56):
        return False

    foot = _candidate_foot(candidate)
    if foot is None:
        return False
    maximum_px = (
        max(1, min(_LOCAL_RADIUS_MAX_CELLS, int(radius_cells))) + 0.75
    ) * CELL_SIZE_PX
    return math.dist(foot, predicted_foot) <= maximum_px


def _copy_decision(decision: Any, **updates: Any) -> Any:
    allowed = {
        name: value
        for name, value in updates.items()
        if hasattr(decision, name)
    }
    if is_dataclass(decision):
        return replace(decision, **allowed)
    values = dict(vars(decision)) if hasattr(decision, "__dict__") else {}
    values.update(allowed)
    return SimpleNamespace(**values)


def _install_target_capsule_pre_enrichment() -> None:
    """Score raw detections with Target Capsule before PR26 occupancy filtering.

    Previously PR26 filtered first and Target Capsule ran second, so the ReID
    system never saw candidates discarded by occupancy. This performs exactly
    one enrichment pass per frame timestamp and makes the later post-gate pass a
    no-op for candidates that have already been processed.
    """

    global _TARGET_MEMORY_PATCHED, _TARGET_ENRICH_ORIGINAL
    if _TARGET_MEMORY_PATCHED:
        return

    from . import target_memory as target_module

    CurrentMemory = target_module.TargetCapsuleMemory
    original_init = CurrentMemory.__init__
    original_enrich = CurrentMemory.enrich_candidates
    _TARGET_ENRICH_ORIGINAL = original_enrich

    def continuity_init(self, *args, **kwargs):
        global _ACTIVE_TARGET_MEMORY
        original_init(self, *args, **kwargs)
        _ACTIVE_TARGET_MEMORY = self
        self._pr26_pre_enriched_timestamp = None

    def continuity_enrich(
        self,
        *,
        frame_bgr,
        state,
        candidates,
        timestamp,
    ):
        global _ACTIVE_TARGET_MEMORY
        _ACTIVE_TARGET_MEMORY = self
        if getattr(self, "_pr26_pre_enriched_timestamp", None) == float(timestamp):
            return tuple(candidates)
        return original_enrich(
            self,
            frame_bgr=frame_bgr,
            state=state,
            candidates=candidates,
            timestamp=timestamp,
        )

    CurrentMemory.__init__ = continuity_init
    CurrentMemory.enrich_candidates = continuity_enrich
    _TARGET_MEMORY_PATCHED = True


def _pre_enrich_raw_candidates(
    *,
    frame_bgr: Any,
    state: Any,
    candidates: Iterable[CandidateObservation],
    timestamp: float,
) -> tuple[CandidateObservation, ...]:
    memory = _ACTIVE_TARGET_MEMORY
    original = _TARGET_ENRICH_ORIGINAL
    current = tuple(candidates)
    if memory is None or original is None:
        return current
    enriched = tuple(
        original(
            memory,
            frame_bgr=frame_bgr,
            state=state,
            candidates=current,
            timestamp=timestamp,
        )
    )
    memory._pr26_pre_enriched_timestamp = float(timestamp)
    return enriched


def _camera_state(tracker: Any) -> tuple[float, float]:
    return (
        float(getattr(tracker.map, "camera_dx", 0.0)),
        float(getattr(tracker.map, "camera_dy", 0.0)),
    )


def _track_grid_distance(track: Any, player_cell: GridCell | None) -> int:
    if player_cell is None:
        return 1_000_000
    cells = tuple(getattr(track, "cells", ()))
    if not cells:
        return player_cell.chebyshev_distance(track.foot_cell)
    return min(player_cell.chebyshev_distance(cell) for cell in cells)


def _update_memory_from_track(
    tracker: Any,
    memory: _RoundTargetMemory,
    track: Any,
    now: float,
    *,
    authority: str = "VISUAL_CLUSTER",
) -> None:
    camera_dx, camera_dy = _camera_state(tracker)
    memory.track = track
    memory.last_visual_at = float(now)
    memory.foot_point = (float(track.foot_point[0]), float(track.foot_point[1]))
    memory.foot_cell = track.foot_cell
    memory.cells = frozenset(track.cells)
    memory.bbox = tuple(int(value) for value in track.bbox)
    memory.camera_dx = camera_dx
    memory.camera_dy = camera_dy
    if track.raw_track_ids:
        memory.last_raw_track_id = min(track.raw_track_ids)
    memory.authority = str(authority)
    memory.reid_votes.clear()
    memory.reid_key = None


def _predicted_memory_geometry(
    tracker: Any,
    memory: _RoundTargetMemory,
) -> tuple[
    tuple[float, float],
    GridCell,
    frozenset[GridCell],
    tuple[int, int, int, int],
]:
    camera_dx, camera_dy = _camera_state(tracker)
    shift_x = camera_dx - memory.camera_dx
    shift_y = camera_dy - memory.camera_dy
    foot = (memory.foot_point[0] + shift_x, memory.foot_point[1] + shift_y)
    cell_shift_x = int(round(shift_x / CELL_SIZE_PX))
    cell_shift_y = int(round(shift_y / CELL_SIZE_PX))
    foot_cell = GridCell(
        memory.foot_cell.x + cell_shift_x,
        memory.foot_cell.y + cell_shift_y,
    )
    cells = frozenset(
        GridCell(cell.x + cell_shift_x, cell.y + cell_shift_y)
        for cell in memory.cells
    )
    left, top, width, height = memory.bbox
    bbox = (
        int(round(left + shift_x)),
        int(round(top + shift_y)),
        int(width),
        int(height),
    )
    return foot, foot_cell, cells, bbox


def _compact_track_geometry(track: Any) -> bool:
    _, _, width, height = (int(value) for value in track.bbox)
    return bool(
        8 <= width <= 84
        and 16 <= height <= 112
        and not (width >= 80 and height <= 56)
        and len(tuple(track.cells)) <= 3
    )


def cluster_reid_matches(
    cluster: OccupancyCluster,
    *,
    player_cell: GridCell,
    predicted_foot: tuple[float, float],
    previous_bbox: tuple[int, int, int, int],
    radius_cells: int,
) -> bool:
    """Relaxed local continuation for the already-latched enemy only.

    This rule can never create a new round enemy. It accepts only a compact
    exact-baseline component inside D3 and near the camera-compensated previous
    target position, allowing animation fragments that are too weak for initial
    acquisition to restore the already-known hostile identity.
    """

    if player_cell.chebyshev_distance(cluster.foot_cell) > _LOCAL_RADIUS_MAX_CELLS:
        return False
    if not any(
        item.diff_source is DiffSource.EXACT_CELL_BASELINE
        for item in cluster.cell_observations
    ):
        return False
    _, _, width, height = (int(value) for value in cluster.bbox)
    if not (
        6 <= width <= 84
        and 14 <= height <= 112
        and len(cluster.cells) <= 3
        and float(cluster.occupancy_score) >= 0.45
        and float(cluster.true_changed_ratio) >= 0.045
        and int(cluster.largest_blob_area) >= 90
    ):
        return False
    if width >= 96 or (width >= 80 and height <= 56):
        return False

    _, _, previous_width, previous_height = (
        int(value) for value in previous_bbox
    )
    width_similarity = min(width, previous_width) / max(
        1.0,
        float(max(width, previous_width)),
    )
    height_similarity = min(height, previous_height) / max(
        1.0,
        float(max(height, previous_height)),
    )
    current_aspect = float(height) / float(max(1, width))
    previous_aspect = float(previous_height) / float(max(1, previous_width))
    aspect_similarity = min(current_aspect, previous_aspect) / max(
        1e-6,
        max(current_aspect, previous_aspect),
    )
    shape_similarity = (
        width_similarity + height_similarity + aspect_similarity
    ) / 3.0
    if shape_similarity < 0.34:
        return False

    maximum_px = (
        max(1, min(_LOCAL_RADIUS_MAX_CELLS, int(radius_cells))) + 0.90
    ) * CELL_SIZE_PX
    return math.dist(cluster.foot_point, predicted_foot) <= maximum_px


def _vote_reid(
    memory: _RoundTargetMemory,
    key: tuple[Any, ...],
    detected: bool,
) -> int:
    if memory.reid_key != key:
        memory.reid_key = key
        memory.reid_votes.clear()
    memory.reid_votes.append(bool(detected))
    return sum(memory.reid_votes)


def _cluster_candidate(
    tracker: Any,
    track: Any,
    cluster: OccupancyCluster,
    player_center: tuple[float, float],
) -> CandidateObservation:
    return CandidateObservation(
        track_id=2_000_000 + track.track_id,
        anchor_cell=cluster.foot_cell,
        kind=ObservationKind.REIDENTIFIED_BODY,
        visible=True,
        body_like=True,
        confidence=max(0.82, float(cluster.occupancy_score)),
        cells_touched=frozenset(cluster.cells),
        face_hint=tracker._face(player_center, cluster.foot_point),
        bbox=cluster.bbox,
        foot_point=cluster.foot_point,
        relative_offset_px=(
            float(cluster.foot_point[0]) - float(player_center[0]),
            float(cluster.foot_point[1]) - float(player_center[1]),
        ),
        identity_score=0.82,
        appearance_score=max(0.55, float(cluster.occupancy_score)),
        position_score=0.82,
        shape_similarity=0.72,
        motion_score=0.62,
        background_probability=0.08,
        reidentified=True,
    )


def install_combat_target_continuity_tracking() -> None:
    """Latch the confirmed round enemy and perform progressive D1->D3 ReID."""

    global _TRACKING_INSTALLED
    if _TRACKING_INSTALLED:
        return

    from . import strategy as strategy_module
    from .occupancy_tracking import PR26OccupancyTracker
    from .pixel_occupancy import PixelOccupancyMap

    _install_target_capsule_pre_enrichment()

    CurrentStrategy = strategy_module.GridFocusStrategy

    class PersistentRoundTargetStrategy(CurrentStrategy):
        def __init__(self, *args, **kwargs) -> None:
            kwargs.setdefault("local_reid_seconds", _PERSISTENT_REID_SECONDS)
            kwargs.setdefault("hard_lost_seconds", _PERSISTENT_REID_SECONDS)
            super().__init__(*args, **kwargs)

    strategy_module.GridFocusStrategy = PersistentRoundTargetStrategy

    original_observe = PixelOccupancyMap.observe

    def contact_overlap_observe(self, *, state, player_rect=None, **kwargs):
        if bool(getattr(self, "_pr26_contact_mask_enabled", False)):
            player_rect = contact_player_rect(state)
            self._pr26_contact_player_rect = player_rect
        return original_observe(
            self,
            state=state,
            player_rect=player_rect,
            **kwargs,
        )

    PixelOccupancyMap.observe = contact_overlap_observe

    original_associate = PR26OccupancyTracker._associate

    def persistent_associate(self, clusters, now, player_center, player_cell):
        self._pr26_continuity_now = float(now)
        self._pr26_current_player_center = (
            float(player_center[0]),
            float(player_center[1]),
        )
        memory: _RoundTargetMemory | None = getattr(
            self,
            "_pr26_round_target_memory",
            None,
        )
        predicted_before = (
            _predicted_memory_geometry(self, memory)
            if memory is not None
            else None
        )
        if memory is not None:
            self._tracks.setdefault(memory.track_id, memory.track)

        original_associate(self, clusters, now, player_center, player_cell)

        memory = getattr(self, "_pr26_round_target_memory", None)
        if memory is None:
            return
        track = self._tracks.get(memory.track_id)
        if track is None:
            track = memory.track
            self._tracks[memory.track_id] = track
        memory.track = track

        if track.visible and predicted_before is not None:
            predicted_foot, predicted_cell, predicted_cells, predicted_bbox = (
                predicted_before
            )
            association_distance = math.dist(track.foot_point, predicted_foot)
            association_valid = bool(
                _compact_track_geometry(track)
                and association_distance <= 176.0
                and _track_grid_distance(track, player_cell)
                <= _LOCAL_RADIUS_MAX_CELLS
            )
            if not association_valid:
                track.visible = False
                track.combat_lock = False
                track.foot_point = predicted_foot
                track.foot_cell = predicted_cell
                track.cells = predicted_cells
                track.bbox = predicted_bbox
                track.reason = (
                    "latched target association rejected; progressive local ReID active"
                )
                key = (
                    "ASSOCIATION_REJECTED",
                    int(round(association_distance / 16.0)),
                    _track_grid_distance(track, player_cell),
                )
                if memory.last_event_key != key:
                    memory.last_event_key = key
                    self._emit(
                        f"PR26_TARGET_ASSOCIATION_REJECTED id={track.track_id} "
                        f"distance={association_distance:.1f}px "
                        f"D={_track_grid_distance(track, player_cell)} "
                        "reason=NOT_COMPACT_OR_OUTSIDE_LOCAL_CONTINUITY"
                    )

        track.attention_lock = True
        track.face_only_lock = True
        track.entity_state = EntityState.ENTITY_CONFIRMED
        track.hostility_state = HostilityState.HOSTILE_CONFIRMED
        track.ambiguous = False
        if not track.visible:
            track.combat_lock = False
            track.reason = "round enemy retained; progressive local ReID active"
        self._pr26_selected_track_id = memory.track_id

    PR26OccupancyTracker._associate = persistent_associate

    original_active = PR26OccupancyTracker._active

    def round_target_active(self):
        selected = original_active(self)
        now = float(
            getattr(self, "_pr26_continuity_now", time.monotonic())
        )
        memory: _RoundTargetMemory | None = getattr(
            self,
            "_pr26_round_target_memory",
            None,
        )
        if memory is None:
            locked = selected
            if locked is None or not bool(getattr(locked, "combat_lock", False)):
                locked = next(
                    (
                        track
                        for track in self._tracks.values()
                        if bool(getattr(track, "combat_lock", False))
                    ),
                    None,
                )
            if locked is not None:
                camera_dx, camera_dy = _camera_state(self)
                memory = _RoundTargetMemory(
                    track=locked,
                    track_id=locked.track_id,
                    latched_at=now,
                    last_visual_at=now,
                    foot_point=(
                        float(locked.foot_point[0]),
                        float(locked.foot_point[1]),
                    ),
                    foot_cell=locked.foot_cell,
                    cells=frozenset(locked.cells),
                    bbox=tuple(int(value) for value in locked.bbox),
                    camera_dx=camera_dx,
                    camera_dy=camera_dy,
                    last_raw_track_id=(
                        min(locked.raw_track_ids)
                        if locked.raw_track_ids
                        else None
                    ),
                )
                self._pr26_round_target_memory = memory
                self._emit(
                    f"PR26_ROUND_TARGET_LATCHED id={locked.track_id} "
                    f"cells={self._cells_text(locked.cells)} authority=UNTIL_KO"
                )

        if memory is None:
            self.map._pr26_contact_mask_enabled = False
            self._pr26_continuity_authority = "NONE"
            return selected

        track = self._tracks.get(memory.track_id, memory.track)
        self._tracks[memory.track_id] = track
        memory.track = track
        player_cell = getattr(self, "_pr26_current_player_cell", None)
        distance = _track_grid_distance(track, player_cell)

        if track.visible:
            if distance > _LOCAL_RADIUS_MAX_CELLS:
                memory.outside_radius_votes += 1
                track.attention_lock = True
                track.face_only_lock = True
                track.combat_lock = True
                track.entity_state = EntityState.ENTITY_CONFIRMED
                track.hostility_state = HostilityState.HOSTILE_CONFIRMED
                track.ambiguous = False
                _update_memory_from_track(
                    self,
                    memory,
                    track,
                    now,
                    authority="OUTSIDE_D3",
                )
                self._pr26_continuity_authority = "OUTSIDE_D3"
                if memory.outside_radius_votes == 2:
                    self._emit(
                        f"PR26_TARGET_OUTSIDE_D3 id={track.track_id} D={distance} "
                        "identity=LATCHED action=BLOCKED"
                    )
            else:
                memory.outside_radius_votes = 0
                track.attention_lock = True
                track.face_only_lock = True
                track.combat_lock = True
                track.entity_state = EntityState.ENTITY_CONFIRMED
                track.hostility_state = HostilityState.HOSTILE_CONFIRMED
                track.ambiguous = False
                _update_memory_from_track(
                    self,
                    memory,
                    track,
                    now,
                    authority="VISUAL_CLUSTER",
                )
                self._pr26_continuity_authority = "VISUAL_CLUSTER"
        else:
            track.attention_lock = True
            track.face_only_lock = True
            track.combat_lock = False
            track.entity_state = EntityState.ENTITY_CONFIRMED
            track.hostility_state = HostilityState.HOSTILE_CONFIRMED
            track.ambiguous = False
            track.reason = "round enemy retained; waiting for visual ReID inside D3"
            if memory.authority == "VISUAL_CLUSTER":
                memory.authority = "CONTACT_MEMORY"
            self._pr26_continuity_authority = memory.authority

        self._pr26_selected_track_id = track.track_id
        for other in self._tracks.values():
            if other.track_id != track.track_id:
                other.attention_lock = False
                other.face_only_lock = False
                other.combat_lock = False
                other.ambiguous = False

        _, predicted_cell, _, _ = _predicted_memory_geometry(self, memory)
        predicted_distance = (
            player_cell.chebyshev_distance(predicted_cell)
            if player_cell is not None
            else 1_000_000
        )
        self.map._pr26_contact_mask_enabled = bool(
            distance <= 1 or predicted_distance <= 1
        )
        return track

    PR26OccupancyTracker._active = round_target_active

    original_filter = PR26OccupancyTracker.filter_candidates

    def continuity_filter(self, *args, **kwargs):
        timestamp = float(kwargs.get("now", time.monotonic()))
        raw_candidates = _pre_enrich_raw_candidates(
            frame_bgr=kwargs.get("frame_bgr"),
            state=kwargs.get("state"),
            candidates=kwargs.get("candidates", ()),
            timestamp=timestamp,
        )
        forwarded = dict(kwargs)
        forwarded["candidates"] = raw_candidates
        result = tuple(original_filter(self, *args, **forwarded))
        if self.mode is not PR26ControlMode.FULL_COMBAT:
            return result

        memory: _RoundTargetMemory | None = getattr(
            self,
            "_pr26_round_target_memory",
            None,
        )
        if memory is None:
            return result

        track = self._tracks.get(memory.track_id, memory.track)
        self._tracks[memory.track_id] = track
        memory.track = track
        player_cell = getattr(self, "_pr26_current_player_cell", None)
        player_center = getattr(self, "_pr26_current_player_center", None)
        if player_cell is None or player_center is None:
            return result

        if result and track.visible and track.combat_lock:
            distance = _track_grid_distance(track, player_cell)
            if distance <= _LOCAL_RADIUS_MAX_CELLS:
                self._pr26_continuity_authority = "VISUAL_CLUSTER"
                memory.authority = "VISUAL_CLUSTER"
            else:
                self._pr26_continuity_authority = "OUTSIDE_D3"
                memory.authority = "OUTSIDE_D3"
            return result

        predicted_foot, predicted_cell, predicted_cells, predicted_bbox = (
            _predicted_memory_geometry(self, memory)
        )
        missing_seconds = max(0.0, timestamp - memory.last_visual_at)
        radius = progressive_reid_radius(missing_seconds)

        capsule_matches = [
            candidate
            for candidate in raw_candidates
            if capsule_reid_matches(
                candidate,
                player_cell=player_cell,
                predicted_foot=predicted_foot,
                radius_cells=radius,
            )
        ]
        capsule_matches.sort(
            key=lambda candidate: (
                candidate.track_id != memory.last_raw_track_id,
                -float(candidate.identity_score),
                -float(candidate.appearance_score),
                math.dist(
                    _candidate_foot(candidate) or predicted_foot,
                    predicted_foot,
                ),
                candidate.track_id,
            )
        )
        best_capsule = capsule_matches[0] if capsule_matches else None

        cluster_matches = [
            cluster
            for cluster in tuple(getattr(self, "last_clusters", ()))
            if cluster_reid_matches(
                cluster,
                player_cell=player_cell,
                predicted_foot=predicted_foot,
                previous_bbox=memory.bbox,
                radius_cells=radius,
            )
        ]
        cluster_matches.sort(
            key=lambda cluster: (
                math.dist(cluster.foot_point, predicted_foot),
                -float(cluster.occupancy_score),
                -int(cluster.largest_blob_area),
                cluster.local_id,
            )
        )
        best_cluster = cluster_matches[0] if cluster_matches else None

        confirmed_candidate: CandidateObservation | None = None
        confirmed_authority: str | None = None

        if best_capsule is not None:
            key = ("CAPSULE", int(best_capsule.track_id))
            votes = _vote_reid(memory, key, True)
            strong_capsule = bool(
                float(best_capsule.identity_score) >= 0.82
                and float(best_capsule.appearance_score) >= 0.65
                and float(best_capsule.background_probability) <= 0.25
            )
            required_votes = 1 if strong_capsule else _REID_VOTES_REQUIRED
            if votes >= required_votes:
                foot = _candidate_foot(best_capsule)
                assert foot is not None
                track.visible = True
                track.last_seen = timestamp
                track.last_seen_frame = self._frame
                track.cells = frozenset(
                    set(best_capsule.cells_touched)
                    | {best_capsule.anchor_cell}
                )
                track.bbox = tuple(int(value) for value in best_capsule.bbox)
                track.foot_point = foot
                track.foot_cell = best_capsule.anchor_cell
                track.occupancy_score = max(
                    0.60,
                    float(best_capsule.confidence),
                    float(best_capsule.appearance_score),
                )
                track.raw_track_ids = frozenset(
                    {best_capsule.track_id}
                    if best_capsule.track_id >= 0
                    else set()
                )
                track.entity_votes.append(True)
                track.attention_lock = True
                track.face_only_lock = True
                track.combat_lock = True
                track.entity_state = EntityState.ENTITY_CONFIRMED
                track.hostility_state = HostilityState.HOSTILE_CONFIRMED
                track.ambiguous = False
                track.reason = (
                    "round enemy visually reidentified by Target Capsule inside D3"
                )
                memory.last_raw_track_id = (
                    best_capsule.track_id
                    if best_capsule.track_id >= 0
                    else memory.last_raw_track_id
                )
                _update_memory_from_track(
                    self,
                    memory,
                    track,
                    timestamp,
                    authority="CAPSULE_REID",
                )
                confirmed_candidate = replace(
                    best_capsule,
                    track_id=2_000_000 + track.track_id,
                    kind=ObservationKind.REIDENTIFIED_BODY,
                    visible=True,
                    body_like=True,
                    confidence=max(0.82, float(best_capsule.confidence)),
                    reidentified=True,
                    identity_score=max(
                        0.72,
                        float(best_capsule.identity_score),
                    ),
                    appearance_score=max(
                        0.50,
                        float(best_capsule.appearance_score),
                    ),
                    position_score=max(
                        0.65,
                        float(best_capsule.position_score),
                    ),
                    background_probability=min(
                        0.20,
                        float(best_capsule.background_probability),
                    ),
                )
                confirmed_authority = "CAPSULE_REID"
                self._emit(
                    f"PR26_TARGET_REID_CONFIRMED id={track.track_id} "
                    f"source=TARGET_CAPSULE raw_id={best_capsule.track_id} "
                    f"radius=D{radius} votes={votes}/{required_votes} "
                    f"identity={confirmed_candidate.identity_score:.2f} "
                    f"appearance={confirmed_candidate.appearance_score:.2f}"
                )

        elif best_cluster is not None:
            key = (
                "PIXEL_CLUSTER",
                best_cluster.foot_cell.x,
                best_cluster.foot_cell.y,
            )
            votes = _vote_reid(memory, key, True)
            if votes >= _REID_VOTES_REQUIRED:
                track.visible = True
                track.last_seen = timestamp
                track.last_seen_frame = self._frame
                track.cells = frozenset(best_cluster.cells)
                track.bbox = tuple(int(value) for value in best_cluster.bbox)
                track.foot_point = (
                    float(best_cluster.foot_point[0]),
                    float(best_cluster.foot_point[1]),
                )
                track.foot_cell = best_cluster.foot_cell
                track.occupancy_score = max(
                    0.55,
                    float(best_cluster.occupancy_score),
                )
                track.true_changed_ratio = float(
                    best_cluster.true_changed_ratio
                )
                track.largest_blob_area = int(
                    best_cluster.largest_blob_area
                )
                track.raw_track_ids = frozenset(best_cluster.raw_track_ids)
                track.entity_votes.append(True)
                track.attention_lock = True
                track.face_only_lock = True
                track.combat_lock = True
                track.entity_state = EntityState.ENTITY_CONFIRMED
                track.hostility_state = HostilityState.HOSTILE_CONFIRMED
                track.ambiguous = False
                track.reason = (
                    "latched round enemy reidentified by compact local pixel cluster"
                )
                _update_memory_from_track(
                    self,
                    memory,
                    track,
                    timestamp,
                    authority="PIXEL_REID",
                )
                confirmed_candidate = _cluster_candidate(
                    self,
                    track,
                    best_cluster,
                    player_center,
                )
                confirmed_authority = "PIXEL_REID"
                self._emit(
                    f"PR26_TARGET_REID_CONFIRMED id={track.track_id} "
                    f"source=LOCAL_PIXEL_CLUSTER radius=D{radius} "
                    f"votes={votes}/{_REID_VOTES_REQUIRED} "
                    f"bbox={best_cluster.bbox[2]}x{best_cluster.bbox[3]} "
                    f"occupancy={best_cluster.occupancy_score:.2f}"
                )
        else:
            if memory.reid_key is not None:
                memory.reid_votes.append(False)

        if confirmed_candidate is not None and confirmed_authority is not None:
            self._pr26_continuity_authority = confirmed_authority
            memory.authority = confirmed_authority
            self.last_snapshot = self._snapshot(track)
            self.map._pr26_contact_mask_enabled = (
                _track_grid_distance(track, player_cell) <= 1
            )
            return (confirmed_candidate,)

        track.visible = False
        track.combat_lock = False
        track.attention_lock = True
        track.face_only_lock = True
        track.entity_state = EntityState.ENTITY_CONFIRMED
        track.hostility_state = HostilityState.HOSTILE_CONFIRMED
        track.foot_point = predicted_foot
        track.foot_cell = predicted_cell
        track.cells = predicted_cells
        track.bbox = predicted_bbox

        hypothesis_present = (
            best_capsule is not None or best_cluster is not None
        )
        memory.authority = (
            "REID_PENDING" if hypothesis_present else "CONTACT_MEMORY"
        )
        self._pr26_continuity_authority = memory.authority
        track.reason = (
            f"round enemy retained; {memory.authority} "
            f"local_search=D{radius} missing={missing_seconds:.2f}s"
        )
        self.last_snapshot = self._snapshot(track)
        self.map._pr26_contact_mask_enabled = (
            _track_grid_distance(track, player_cell) <= 1
        )

        event_key = (
            memory.authority,
            radius,
            int(missing_seconds // 2),
            bool(best_capsule),
            bool(best_cluster),
        )
        if memory.last_event_key != event_key:
            memory.last_event_key = event_key
            self._emit(
                f"PR26_TARGET_MEMORY id={track.track_id} "
                f"authority={memory.authority} local_search=D{radius} "
                f"missing={missing_seconds:.2f}s "
                f"capsule={'YES' if best_capsule is not None else 'NO'} "
                f"pixel={'YES' if best_cluster is not None else 'NO'} "
                "switch=BLOCKED round_target_id=LATCHED"
            )
        return ()

    PR26OccupancyTracker.filter_candidates = continuity_filter

    _TRACKING_INSTALLED = True
    print(
        "PR26.9 COMBAT TARGET MEMORY: confirmed round enemy is latched until KO; "
        "contact overlap uses a smaller player core; Target Capsule runs progressive "
        "D1->D3 ReID; score challengers cannot replace the current target"
    )


def install_combat_target_continuity_physical_gate() -> None:
    """Block chase/H for memory-only states while retaining target identity."""

    global _PHYSICAL_INSTALLED
    if _PHYSICAL_INSTALLED:
        return

    from . import live_bridge as live_module
    from .runtime_tile_perception import current_hostility_gate

    CurrentPhysical = live_module.PhysicalCombatInput

    class PersistentTargetPhysicalInput(CurrentPhysical):
        def execute(self, decision, *, confirm_aim=None):
            mode = PR26ControlMode.from_environment()
            if mode is not PR26ControlMode.FULL_COMBAT:
                return super().execute(decision, confirm_aim=confirm_aim)

            gate = current_hostility_gate()
            authority = (
                str(getattr(gate, "_pr26_continuity_authority", "NONE"))
                if gate is not None
                else "NONE"
            )
            if authority not in {
                "CONTACT_MEMORY",
                "REID_PENDING",
                "OUTSIDE_D3",
            }:
                return super().execute(decision, confirm_aim=confirm_aim)

            safe = _copy_decision(
                decision,
                move=None,
                move_pulse_profile=None,
                move_pulse_ms=None,
                press_h=False,
                h_pulse_ms=None,
                h_authorized=False,
                turn_direction=None,
                h_cancel_reason=(
                    f"PR26_{authority}_VISUAL_CONFIRMATION_REQUIRED"
                ),
            )
            actions = tuple(super().execute(safe, confirm_aim=confirm_aim))
            return actions + (
                f"PR26_{authority}_MOVE_H_BLOCKED_TARGET_ID_RETAINED",
            )

    live_module.PhysicalCombatInput = PersistentTargetPhysicalInput
    _PHYSICAL_INSTALLED = True
    print(
        "PR26.9 PHYSICAL CONTINUITY GATE: CONTACT_MEMORY/REID_PENDING/OUTSIDE_D3 "
        "retain the round enemy and R/facing memory but cannot chase or fire H"
    )


__all__ = [
    "capsule_reid_matches",
    "cluster_reid_matches",
    "contact_player_rect",
    "install_combat_target_continuity_physical_gate",
    "install_combat_target_continuity_tracking",
    "progressive_reid_radius",
]
