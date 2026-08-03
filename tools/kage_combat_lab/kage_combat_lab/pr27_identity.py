from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
from typing import Mapping, Sequence

import numpy as np

from .pr27_fragments import DescriptorFactory
from .pr27_model import (
    AppearanceDescriptor,
    PR27Config,
    SelfTrackState,
    SpriteClass,
    SpriteObservation,
    SpriteRole,
    TrackState,
    TrackedSprite,
)


def bbox_iou(
    a: tuple[int, int, int, int] | None,
    b: tuple[int, int, int, int] | None,
) -> float:
    if a is None or b is None:
        return 0.0
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0, right - left) * max(0, bottom - top)
    return intersection / max(1, aw * ah + bw * bh - intersection)


def copy_descriptor(value: AppearanceDescriptor) -> AppearanceDescriptor:
    return AppearanceDescriptor(
        np.asarray(value.hsv_histogram, dtype=np.float32).copy(),
        np.asarray(value.structure_vector, dtype=np.float32).copy(),
        float(value.edge_density),
    )


def lock_track_role(
    track: TrackedSprite,
    desired: SpriteRole,
    *,
    frame_index: int,
    source: str,
    confidence: float,
) -> bool:
    current = track.effective_role
    if track.role_locked and current is not desired:
        track.role_conflict_reason = (
            f"ROLE_FLIP_BLOCKED:{current.value}->{desired.value}"
        )
        return False
    track.role = desired
    track.role_locked = desired in {
        SpriteRole.SELF,
        SpriteRole.ENEMY,
        SpriteRole.NPC,
    }
    if track.role_assigned_frame < 0:
        track.role_assigned_frame = frame_index
    track.role_source = source
    track.role_confidence = max(
        track.role_confidence,
        float(confidence),
    )
    track.role_conflict_reason = None
    if desired is SpriteRole.SELF:
        track.classification = SpriteClass.PLAYER
        track.known_enemy = False
    elif desired is SpriteRole.ENEMY:
        track.classification = SpriteClass.ENEMY
        track.known_enemy = True
    elif desired is SpriteRole.NPC:
        track.classification = SpriteClass.NPC
        track.known_enemy = False
    return True


@dataclass(slots=True)
class SelfIdentityCapsule:
    """Slow-changing SELF identity; ambiguous observations never update it."""

    widths: deque[float] = field(default_factory=lambda: deque(maxlen=31))
    heights: deque[float] = field(default_factory=lambda: deque(maxlen=31))
    descriptors: deque[AppearanceDescriptor] = field(
        default_factory=lambda: deque(maxlen=12)
    )
    update_count: int = 0
    calibration_confidence: float = 0.0
    calibration_method: str = "unavailable"

    @property
    def ready(self) -> bool:
        return bool(self.widths and self.heights and self.descriptors)

    @property
    def median_size(self) -> tuple[float, float] | None:
        if not self.widths or not self.heights:
            return None
        return (
            float(np.median(self.widths)),
            float(np.median(self.heights)),
        )

    def bootstrap_metadata(self, metadata: Mapping[str, object]) -> None:
        value = metadata.get("self_body_size")
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                width, height = float(value[0]), float(value[1])
            except (TypeError, ValueError):
                width, height = 0.0, 0.0
            if width > 0 and height > 0:
                self.widths.append(width)
                self.heights.append(height)

        raw_descriptor = metadata.get("self_appearance_descriptor")
        if isinstance(raw_descriptor, Mapping):
            try:
                histogram = np.asarray(
                    raw_descriptor.get("hsv_histogram", ()),
                    dtype=np.float32,
                )
                structure = np.asarray(
                    raw_descriptor.get("structure_vector", ()),
                    dtype=np.float32,
                )
                edge_density = float(
                    raw_descriptor.get("edge_density", 0.0)
                )
            except (TypeError, ValueError):
                histogram = np.empty((0,), dtype=np.float32)
                structure = np.empty((0,), dtype=np.float32)
                edge_density = 0.0
            if histogram.shape == (32,) and structure.shape == (64,):
                self.descriptors.append(
                    AppearanceDescriptor(
                        histogram.copy(),
                        structure.copy(),
                        edge_density,
                    )
                )

        try:
            self.calibration_confidence = float(
                metadata.get("self_calibration_confidence", 0.0)
            )
        except (TypeError, ValueError):
            self.calibration_confidence = 0.0
        self.calibration_method = str(
            metadata.get("self_calibration_method", "unavailable")
        )

    def score(
        self,
        observation: SpriteObservation,
    ) -> tuple[float, float, float]:
        if observation.body_bbox is None:
            return 0.0, 0.0, 0.0
        _, _, width, height = observation.body_bbox
        median = self.median_size
        if median is None:
            size_score = 1.0
        else:
            median_width, median_height = median
            width_ratio = min(width, median_width) / max(
                1.0,
                max(width, median_width),
            )
            height_ratio = min(height, median_height) / max(
                1.0,
                max(height, median_height),
            )
            size_score = math.sqrt(
                max(0.0, width_ratio * height_ratio)
            )
        if not self.descriptors:
            appearance_score = 1.0
        else:
            appearance_score = max(
                DescriptorFactory.similarity(
                    reference,
                    observation.descriptor,
                )
                for reference in self.descriptors
            )
        identity_score = 0.62 * appearance_score + 0.38 * size_score
        return identity_score, appearance_score, size_score

    def update(
        self,
        observation: SpriteObservation,
        *,
        clean: bool,
    ) -> None:
        if not clean or observation.body_bbox is None:
            return
        _, _, width, height = observation.body_bbox
        self.widths.append(float(width))
        self.heights.append(float(height))
        self.descriptors.append(
            copy_descriptor(observation.descriptor)
        )
        self.update_count += 1


class SelfTracker:
    """Dedicated first-stage tracker. SELF never competes with other roles."""

    SELF_TRACK_ID = 0

    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.identity = SelfIdentityCapsule()
        self.track: TrackedSprite | None = None
        self.state = SelfTrackState.SELF_REACQUIRING
        self.expected_anchor: tuple[float, float] | None = None
        self.last_observation_id: int | None = None
        self.last_association_score = 0.0
        self.last_identity_score = 0.0
        self.last_role_source = "unavailable"
        self.last_rejection = "SELF_NOT_ACQUIRED"
        self.ambiguity_count = 0
        self.role_flip_attempt: str | None = None
        self.diagnostics: list[dict[str, object]] = []

    def bootstrap_metadata(
        self,
        metadata: Mapping[str, object],
    ) -> None:
        self.identity.bootstrap_metadata(metadata)
        anchor = metadata.get("self_anchor_arena")
        if isinstance(anchor, (list, tuple)) and len(anchor) == 2:
            try:
                x, y = float(anchor[0]), float(anchor[1])
            except (TypeError, ValueError):
                return
            if x >= 0.0 and y >= 0.0:
                self.expected_anchor = (x, y)

    def _fallback_anchor(
        self,
        arena_shape: Sequence[int],
    ) -> tuple[float, float]:
        return (
            int(arena_shape[1]) * self.config.player_anchor_x_ratio,
            int(arena_shape[0]) * self.config.player_anchor_y_ratio,
        )

    def _predicted_anchor(
        self,
        arena_shape: Sequence[int],
    ) -> tuple[float, float]:
        if self.track is None:
            return self.expected_anchor or self._fallback_anchor(arena_shape)
        if len(self.track.movement_history) >= 2:
            previous = self.track.movement_history[-2]
            current = self.track.movement_history[-1]
            dx = max(-32.0, min(32.0, current[0] - previous[0]))
            dy = max(-32.0, min(32.0, current[1] - previous[1]))
            return current[0] + dx, current[1] + dy
        if self.track.body_anchor is not None:
            return self.track.body_anchor
        return self.expected_anchor or self._fallback_anchor(arena_shape)

    def _candidate_score(
        self,
        observation: SpriteObservation,
        *,
        predicted: tuple[float, float],
        first_lock: bool,
    ) -> tuple[float, float, dict[str, object]]:
        if (
            not observation.has_body_lock
            or observation.body_anchor is None
            or observation.body_bbox is None
        ):
            return 0.0, 0.0, {
                "rejection_reason": "SELF_BODY_LOCK_MISSING"
            }
        identity_score, appearance_score, size_score = (
            self.identity.score(observation)
        )
        distance = math.hypot(
            observation.body_anchor[0] - predicted[0],
            observation.body_anchor[1] - predicted[1],
        )
        max_distance = (
            self.config.player_anchor_radius_px
            if first_lock
            else max(
                48.0,
                self.config.player_anchor_radius_px * 1.25,
            )
        )
        if distance > max_distance:
            return 0.0, identity_score, {
                "rejection_reason": "SELF_POSITION_GATE",
                "distance": distance,
                "identity_score": identity_score,
            }
        if self.identity.ready:
            minimum_identity = (
                max(0.26, self.config.self_identity_min_score * 0.80)
                if first_lock
                else self.config.self_identity_min_score
            )
            if identity_score < minimum_identity:
                return 0.0, identity_score, {
                    "rejection_reason": "SELF_IDENTITY_GATE",
                    "identity_score": identity_score,
                }
            if size_score < self.config.self_size_ratio_min:
                return 0.0, identity_score, {
                    "rejection_reason": "SELF_SIZE_GATE",
                    "size_score": size_score,
                }
        proximity = max(
            0.0,
            1.0 - distance / max(1.0, max_distance),
        )
        overlap = bbox_iou(
            None if self.track is None else self.track.body_bbox,
            observation.body_bbox,
        )
        body = max(0.0, min(1.0, observation.body_confidence))
        if first_lock:
            identity_weight = 0.28 if self.identity.ready else 0.08
            score = (
                (0.42 if self.identity.ready else 0.62) * proximity
                + 0.18 * body
                + 0.12 * size_score
                + identity_weight * appearance_score
            )
        else:
            score = (
                0.38 * proximity
                + 0.30 * identity_score
                + 0.17 * overlap
                + 0.10 * body
                + 0.05 * size_score
            )
        return score, identity_score, {
            "candidate_id": observation.observation_id,
            "candidate_role": SpriteRole.SELF.value,
            "candidate_score": score,
            "position_score": proximity,
            "appearance_score": appearance_score,
            "size_score": size_score,
            "identity_score": identity_score,
            "role_gate_passed": True,
            "rejection_reason": None,
        }

    @staticmethod
    def _new_track(
        observation: SpriteObservation,
        frame_index: int,
        *,
        calibrated: bool,
    ) -> TrackedSprite:
        value = TrackedSprite(
            track_id=SelfTracker.SELF_TRACK_ID,
            current_cells=frozenset({(0, 0)}),
            previous_cells=frozenset(),
            fragments=observation.fragments,
            native_bbox=observation.native_bbox,
            combined_mask=observation.combined_mask,
            appearance_signature=copy_descriptor(
                observation.descriptor
            ),
            first_seen_frame=frame_index,
            last_seen_frame=frame_index,
            body_bbox=observation.body_bbox,
            body_anchor=observation.body_anchor,
            anchor_cell=(0, 0),
            body_confidence=observation.body_confidence,
            confidence=max(0.75, observation.body_confidence),
            classification=SpriteClass.PLAYER,
            observation_id=observation.observation_id,
            role=SpriteRole.SELF,
            role_locked=True,
            role_assigned_frame=frame_index,
            role_source=(
                "self_calibrated_capsule"
                if calibrated
                else "self_bootstrap"
            ),
            role_confidence=max(0.75, observation.body_confidence),
            track_source="calibrated" if calibrated else "reacquired",
        )
        if value.body_anchor is not None:
            value.movement_history.append(value.body_anchor)
        return value

    def _update_track(
        self,
        observation: SpriteObservation,
        *,
        frame_index: int,
        association_score: float,
        identity_score: float,
    ) -> None:
        assert self.track is not None
        self.track.previous_cells = self.track.current_cells
        self.track.current_cells = frozenset({(0, 0)})
        self.track.fragments = observation.fragments
        self.track.native_bbox = observation.native_bbox
        self.track.combined_mask = observation.combined_mask
        self.track.appearance_signature = copy_descriptor(
            observation.descriptor
        )
        self.track.body_bbox = observation.body_bbox
        self.track.body_anchor = observation.body_anchor
        self.track.anchor_cell = (0, 0)
        self.track.body_confidence = observation.body_confidence
        self.track.last_seen_frame = frame_index
        self.track.missing_frames = 0
        self.track.observations += 1
        self.track.confidence = max(
            self.track.confidence * 0.75,
            association_score,
        )
        self.track.track_state = TrackState.TRACKED
        self.track.observation_id = observation.observation_id
        self.track.association_score = association_score
        self.track.identity_score = identity_score
        self.track.predicted_anchor = observation.body_anchor
        self.track.track_source = "tracked"
        lock_track_role(
            self.track,
            SpriteRole.SELF,
            frame_index=frame_index,
            source="self_tracker",
            confidence=association_score,
        )
        if observation.body_anchor is not None:
            self.track.movement_history.append(
                observation.body_anchor
            )

    def _coast(
        self,
        *,
        arena_shape: Sequence[int],
        frame_index: int,
        occluded: bool,
    ) -> None:
        if self.track is None:
            self.state = SelfTrackState.SELF_LOST_CRITICAL
            return
        predicted = self._predicted_anchor(arena_shape)
        self.track.predicted_anchor = predicted
        self.track.body_anchor = predicted
        self.track.anchor_cell = (0, 0)
        self.track.observation_id = None
        self.track.missing_frames += 1
        self.track.last_seen_frame = min(
            self.track.last_seen_frame,
            frame_index,
        )
        self.track.track_state = TrackState.TEMPORARILY_MISSING
        self.track.track_source = "predicted"
        self.state = (
            SelfTrackState.SELF_TEMPORARILY_OCCLUDED
            if occluded
            else SelfTrackState.SELF_PREDICTED
        )
        if self.track.missing_frames > self.config.self_prediction_frames:
            self.state = SelfTrackState.SELF_LOST_CRITICAL

    def coast(
        self,
        *,
        arena_shape: Sequence[int],
        frame_index: int,
        occluded: bool = True,
    ) -> TrackedSprite | None:
        self._coast(
            arena_shape=arena_shape,
            frame_index=frame_index,
            occluded=occluded,
        )
        self.last_observation_id = None
        self.last_association_score = 0.0
        self.last_identity_score = 0.0
        self.last_role_source = "predicted"
        return self.track

    def update(
        self,
        observations: Sequence[SpriteObservation],
        *,
        frame_index: int,
        arena_shape: Sequence[int],
        excluded_observation_ids: Sequence[int] = (),
        role_conflict_observation_ids: Sequence[int] = (),
    ) -> tuple[TrackedSprite | None, frozenset[int]]:
        excluded = frozenset(excluded_observation_ids)
        role_conflicts = frozenset(role_conflict_observation_ids)
        self.diagnostics = []
        predicted = self._predicted_anchor(arena_shape)
        first_lock = self.track is None
        scored: list[
            tuple[
                float,
                float,
                SpriteObservation,
                dict[str, object],
            ]
        ] = []
        for observation in observations:
            if observation.observation_id in excluded:
                self.diagnostics.append(
                    {
                        "candidate_id": observation.observation_id,
                        "candidate_role": SpriteRole.SELF.value,
                        "candidate_score": 0.0,
                        "role_gate_passed": False,
                        "rejection_reason": "MERGED_BODY_EXCLUDED",
                    }
                )
                continue
            if observation.observation_id in role_conflicts:
                self.diagnostics.append(
                    {
                        "candidate_id": observation.observation_id,
                        "candidate_role": SpriteRole.SELF.value,
                        "candidate_score": 0.0,
                        "role_gate_passed": False,
                        "rejection_reason": "ROLE_FLIP_BLOCKED",
                    }
                )
                continue
            score, identity_score, diagnostic = (
                self._candidate_score(
                    observation,
                    predicted=predicted,
                    first_lock=first_lock,
                )
            )
            self.diagnostics.append(diagnostic)
            if score > 0.0:
                scored.append(
                    (
                        score,
                        identity_score,
                        observation,
                        diagnostic,
                    )
                )
        scored.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2].body_confidence,
            ),
            reverse=True,
        )
        selected = None
        if scored:
            threshold = (
                0.42
                if first_lock
                else self.config.self_association_min_score
            )
            best = scored[0]
            ambiguous = (
                len(scored) > 1
                and best[0] - scored[1][0]
                < self.config.self_ambiguity_margin
            )
            if best[0] >= threshold and not (
                ambiguous and not first_lock
            ):
                selected = best
            elif ambiguous:
                self.ambiguity_count += 1
                self.last_rejection = "SELF_AMBIGUOUS_PRESERVED"
        if selected is None:
            self._coast(
                arena_shape=arena_shape,
                frame_index=frame_index,
                occluded=bool(excluded),
            )
            self.last_observation_id = None
            self.last_association_score = 0.0
            self.last_identity_score = 0.0
            self.last_role_source = "predicted"
            return self.track, frozenset()

        score, identity_score, observation, _ = selected
        was_missing = (
            self.track is not None and self.track.missing_frames > 0
        )
        if self.track is None:
            calibrated = self.identity.ready
            self.track = self._new_track(
                observation,
                frame_index,
                calibrated=calibrated,
            )
            self.state = SelfTrackState.SELF_TRACKED
            self.last_role_source = (
                "calibrated" if calibrated else "bootstrap"
            )
        else:
            self._update_track(
                observation,
                frame_index=frame_index,
                association_score=score,
                identity_score=identity_score,
            )
            self.state = SelfTrackState.SELF_TRACKED
            self.last_role_source = (
                "reacquired" if was_missing else "tracked"
            )
        observation.reserved_role = SpriteRole.SELF
        self.last_observation_id = observation.observation_id
        self.last_association_score = score
        self.last_identity_score = identity_score
        self.last_rejection = "-"
        self.ambiguity_count = 0
        self.identity.update(
            observation,
            clean=(
                not observation.merged_body
                and score >= self.config.self_association_min_score
            ),
        )
        return self.track, frozenset({observation.observation_id})
