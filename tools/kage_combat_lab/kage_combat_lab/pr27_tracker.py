from __future__ import annotations

import math
from typing import Sequence

from .pr27_fragments import DescriptorFactory
from .pr27_identity import bbox_iou, lock_track_role
from .pr27_model import (
    CELL_SIZE_PX,
    PR27Config,
    SpriteClass,
    SpriteObservation,
    SpriteRole,
    TrackState,
    TrackedSprite,
)
from .pr27_registry import KnownSpriteRegistry


class SpriteTracker:
    """Second-stage tracker. It never owns, creates or reclassifies SELF."""

    def __init__(self, config: PR27Config, registry: KnownSpriteRegistry | None = None) -> None:
        self.config = config.normalized()
        self.registry = registry or KnownSpriteRegistry()
        self.tracks: dict[int, TrackedSprite] = {}
        self.next_track_id = 1
        self.player_track_id: int | None = None
        self.enemy_track_id: int | None = None
        self.pending_enemy_track_id: int | None = None
        self.pending_enemy_hits = 0
        self.pending_rebind_key: tuple[int, int] | None = None
        self.pending_rebind_hits = 0
        self.trainer_exclusion_bbox: tuple[int, int, int, int] | None = None
        self.trainer_forbidden_cells: frozenset[tuple[int, int]] = frozenset()
        self.last_candidate_rejections: list[str] = []
        self.association_diagnostics: list[dict[str, object]] = []
        self.role_flip_attempt: str | None = None
        self.role_flip_blocked: str | None = None
        self.shared_observation_blocked = False
        self.close_candidate_count = 0
        self.last_rebind_reason: str | None = None
        self.self_track: TrackedSprite | None = None

    def set_trainer_exclusion(
        self,
        bbox: tuple[int, int, int, int] | None,
        forbidden_cells: Sequence[tuple[int, int]] = (),
    ) -> None:
        self.trainer_exclusion_bbox = bbox
        self.trainer_forbidden_cells = frozenset(forbidden_cells)

    @staticmethod
    def _bbox_intersects(a, b) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

    @staticmethod
    def _anchor_cell_distance(left, right) -> int:
        if left is None or right is None:
            return 999
        return max(abs(left[0] - right[0]), abs(left[1] - right[1]))

    @staticmethod
    def _predicted_anchor(track: TrackedSprite) -> tuple[float, float]:
        if len(track.movement_history) < 2:
            return track.body_anchor or track.center
        previous, current = track.movement_history[-2], track.movement_history[-1]
        dx = max(-CELL_SIZE_PX, min(CELL_SIZE_PX, current[0] - previous[0]))
        dy = max(-CELL_SIZE_PX, min(CELL_SIZE_PX, current[1] - previous[1]))
        return current[0] + dx, current[1] + dy

    def _inside_roi(self, key: tuple[int, int] | None) -> bool:
        return (
            key is not None
            and key[0] * key[0] + key[1] * key[1]
            <= self.config.roi_radius_cells**2
        )

    def _trainer_rejection_observation(
        self,
        observation: SpriteObservation,
    ) -> str | None:
        if not observation.has_body_lock:
            return "BODY_LOCK_MISSING"
        if not self._inside_roi(observation.anchor_cell):
            return "OUTSIDE_LOCAL_ROI"
        if observation.anchor_cell in self.trainer_forbidden_cells:
            return "TRAINER_FORBIDDEN_ANCHOR_CELL"
        if self.trainer_exclusion_bbox is not None:
            if (
                observation.body_bbox is not None
                and self._bbox_intersects(
                    observation.body_bbox,
                    self.trainer_exclusion_bbox,
                )
            ):
                return "TRAINER_BODY_BBOX_INTERSECTION"
            if observation.body_anchor is not None:
                x, y, width, height = self.trainer_exclusion_bbox
                ax, ay = observation.body_anchor
                if x <= ax < x + width and y <= ay < y + height:
                    return "TRAINER_BODY_ANCHOR_INSIDE_ZONE"
        return None

    def _trainer_rejection_track(self, track: TrackedSprite) -> str | None:
        if not track.has_body_lock:
            return "BODY_LOCK_MISSING"
        if not self._inside_roi(track.anchor_cell):
            return "OUTSIDE_LOCAL_ROI"
        if track.anchor_cell in self.trainer_forbidden_cells:
            return "TRAINER_FORBIDDEN_ANCHOR_CELL"
        if self.trainer_exclusion_bbox is not None:
            if (
                track.body_bbox is not None
                and self._bbox_intersects(
                    track.body_bbox,
                    self.trainer_exclusion_bbox,
                )
            ):
                return "TRAINER_BODY_BBOX_INTERSECTION"
            if track.body_anchor is not None:
                x, y, width, height = self.trainer_exclusion_bbox
                ax, ay = track.body_anchor
                if x <= ax < x + width and y <= ay < y + height:
                    return "TRAINER_BODY_ANCHOR_INSIDE_ZONE"
        return None

    def _self_conflict_observation(
        self,
        observation: SpriteObservation,
    ) -> str | None:
        if self.self_track is None:
            return None
        if observation.reserved_role is SpriteRole.SELF:
            return "SELF_OBSERVATION_RESERVED"
        if observation.merged_body:
            return "MERGED_BODY_EXCLUDED"
        overlap = 0.0
        if (
            observation.body_bbox is not None
            and self.self_track.body_bbox is not None
        ):
            overlap = bbox_iou(
                observation.body_bbox,
                self.self_track.body_bbox,
            )
            if overlap >= 0.72:
                return "SELF_BBOX_OVERLAP_HARD_GATE"
        if (
            observation.body_anchor is not None
            and self.self_track.body_anchor is not None
        ):
            distance = math.hypot(
                observation.body_anchor[0] - self.self_track.body_anchor[0],
                observation.body_anchor[1] - self.self_track.body_anchor[1],
            )
            if (
                distance
                <= max(8.0, self.config.merged_anchor_distance_px)
                and overlap >= self.config.merged_body_iou_threshold
            ):
                return "SELF_ANCHOR_OVERLAP_HARD_GATE"
        return None

    def _association_score(
        self,
        track: TrackedSprite,
        observation: SpriteObservation,
        *,
        target_track: bool,
        arena_shape: Sequence[int],
    ) -> float:
        del arena_shape
        if track.effective_role is SpriteRole.SELF:
            return 0.0
        if not track.has_body_lock or not observation.has_body_lock:
            return 0.0
        if self._self_conflict_observation(observation) is not None:
            return 0.0
        trainer_reason = self._trainer_rejection_observation(observation)
        if trainer_reason is not None and (
            target_track or track.effective_role is SpriteRole.ENEMY
        ):
            return 0.0
        cell_distance = self._anchor_cell_distance(
            track.anchor_cell,
            observation.anchor_cell,
        )
        allowed_step = (
            1 + track.missing_frames
            if target_track
            else self.config.maximum_track_cell_step + track.missing_frames
        )
        if cell_distance > allowed_step:
            return 0.0
        appearance = DescriptorFactory.similarity(
            track.appearance_signature,
            observation.descriptor,
        )
        old_bbox, new_bbox = track.body_bbox, observation.body_bbox
        assert (
            old_bbox is not None
            and new_bbox is not None
            and observation.body_anchor is not None
        )
        old_area = max(1, old_bbox[2] * old_bbox[3])
        new_area = max(1, new_bbox[2] * new_bbox[3])
        size = min(old_area, new_area) / max(old_area, new_area)
        predicted = self._predicted_anchor(track)
        anchor_distance = math.hypot(
            observation.body_anchor[0] - predicted[0],
            observation.body_anchor[1] - predicted[1],
        )
        max_distance = CELL_SIZE_PX * max(1.25, allowed_step + 0.75)
        if target_track and anchor_distance > max_distance:
            return 0.0
        proximity = max(0.0, 1.0 - anchor_distance / max_distance)
        overlap = bbox_iou(old_bbox, new_bbox)
        temporal = max(
            0.0,
            1.0 - cell_distance / max(1.0, allowed_step + 1.0),
        )
        body = min(track.body_confidence, observation.body_confidence)
        if target_track and (
            appearance < self.config.target_minimum_appearance
            or size < 0.52
            or body < self.config.body_lock_min_confidence
        ):
            return 0.0
        score = (
            0.40 * appearance
            + 0.28 * proximity
            + 0.14 * overlap
            + 0.08 * size
            + 0.06 * temporal
            + 0.04 * body
        )
        return min(1.0, score + 0.05) if target_track else score

    def _update_track(
        self,
        track: TrackedSprite,
        observation: SpriteObservation,
        frame_index: int,
        score: float,
    ) -> None:
        if track.effective_role is SpriteRole.SELF:
            self.role_flip_attempt = (
                f"SELF->{observation.reserved_role.value}"
            )
            self.role_flip_blocked = "ROLE_FLIP_BLOCKED"
            track.role_conflict_reason = self.role_flip_blocked
            return
        identity_score = DescriptorFactory.similarity(
            track.appearance_signature,
            observation.descriptor,
        )
        track.previous_cells = track.current_cells
        track.current_cells = observation.cells
        track.fragments = observation.fragments
        track.native_bbox = observation.native_bbox
        track.combined_mask = observation.combined_mask
        track.appearance_signature = observation.descriptor
        track.body_bbox = observation.body_bbox
        track.body_anchor = observation.body_anchor
        track.anchor_cell = observation.anchor_cell
        track.body_confidence = observation.body_confidence
        track.last_seen_frame = frame_index
        track.missing_frames = 0
        track.observations += 1
        track.confidence = max(track.confidence * 0.60, score)
        track.track_state = TrackState.TRACKED
        track.rejection_reason = self._trainer_rejection_track(track)
        track.observation_id = observation.observation_id
        track.association_score = score
        track.identity_score = identity_score
        track.predicted_anchor = observation.body_anchor
        track.track_source = "tracked"
        if track.body_anchor is not None:
            track.movement_history.append(track.body_anchor)

    def _create_track(
        self,
        observation: SpriteObservation,
        frame_index: int,
    ) -> TrackedSprite | None:
        self_reason = self._self_conflict_observation(observation)
        if self_reason is not None:
            self.last_candidate_rejections.append(
                f"observation={observation.observation_id}:{self_reason}"
            )
            if self_reason == "SELF_OBSERVATION_RESERVED":
                self.shared_observation_blocked = True
            return None
        rejection = self._trainer_rejection_observation(observation)
        if rejection is not None:
            self.last_candidate_rejections.append(
                f"observation={observation.observation_id}:{rejection}"
            )
            return None
        track = TrackedSprite(
            track_id=self.next_track_id,
            current_cells=observation.cells,
            previous_cells=frozenset(),
            fragments=observation.fragments,
            native_bbox=observation.native_bbox,
            combined_mask=observation.combined_mask,
            appearance_signature=observation.descriptor,
            first_seen_frame=frame_index,
            last_seen_frame=frame_index,
            body_bbox=observation.body_bbox,
            body_anchor=observation.body_anchor,
            anchor_cell=observation.anchor_cell,
            body_confidence=observation.body_confidence,
            confidence=max(0.50, observation.body_confidence),
            observation_id=observation.observation_id,
            role=SpriteRole.UNKNOWN,
            role_source="non_self_observation",
            association_score=max(0.50, observation.body_confidence),
        )
        if track.body_anchor is not None:
            track.movement_history.append(track.body_anchor)
        self.tracks[track.track_id] = track
        self.next_track_id += 1
        return track

    def _self_anchor(
        self,
        arena_shape: Sequence[int],
    ) -> tuple[float, float]:
        if (
            self.self_track is not None
            and self.self_track.body_anchor is not None
        ):
            return self.self_track.body_anchor
        return (
            int(arena_shape[1]) * self.config.player_anchor_x_ratio,
            int(arena_shape[0]) * self.config.player_anchor_y_ratio,
        )

    def _classify_known_role(
        self,
        track: TrackedSprite,
        frame_index: int,
    ) -> None:
        trainer_reason = self._trainer_rejection_track(track)
        if trainer_reason is not None:
            lock_track_role(
                track,
                SpriteRole.NPC,
                frame_index=frame_index,
                source="trainer_exclusion",
                confidence=1.0,
            )
            track.rejection_reason = trainer_reason
            if self.enemy_track_id == track.track_id:
                self.enemy_track_id = None
            return
        known, score = self.registry.best_match(track.appearance_signature)
        if known is None or score < self.config.known_sprite_threshold:
            return
        track.known_sprite_id = known.sprite_id
        track.confidence = max(track.confidence, score)
        if known.category is SpriteClass.PLAYER:
            self.role_flip_attempt = f"{track.effective_role.value}->SELF"
            self.role_flip_blocked = (
                "ROLE_FLIP_BLOCKED:NON_SELF_TRACK_CANNOT_BECOME_SELF"
            )
            track.role_conflict_reason = self.role_flip_blocked
            track.classification = SpriteClass.UNKNOWN
            track.known_enemy = False
            return
        desired = (
            SpriteRole.ENEMY
            if known.category is SpriteClass.ENEMY
            else SpriteRole.NPC
        )
        if lock_track_role(
            track,
            desired,
            frame_index=frame_index,
            source="known_sprite",
            confidence=score,
        ):
            if desired is SpriteRole.ENEMY:
                self.enemy_track_id = track.track_id
                self.pending_enemy_track_id = None
                self.pending_enemy_hits = 0

    def _enemy_candidate_score(
        self,
        track: TrackedSprite,
        arena_shape: Sequence[int],
    ) -> float:
        if (
            track.track_state is not TrackState.TRACKED
            or not track.has_body_lock
        ):
            return 0.0
        if track.effective_role not in {
            SpriteRole.UNKNOWN,
            SpriteRole.ENEMY,
        }:
            return 0.0
        if track.observations < self.config.enemy_confirm_frames:
            return 0.0
        trainer_reason = self._trainer_rejection_track(track)
        if trainer_reason is not None:
            track.rejection_reason = trainer_reason
            self.last_candidate_rejections.append(
                f"track={track.track_id}:{trainer_reason}"
            )
            return 0.0
        if track.body_confidence < self.config.body_lock_min_confidence:
            self.last_candidate_rejections.append(
                f"track={track.track_id}:BODY_CONFIDENCE_LOW"
            )
            return 0.0
        expected_self = self._self_anchor(arena_shape)
        assert track.body_anchor is not None and track.body_bbox is not None
        separation = math.hypot(
            track.body_anchor[0] - expected_self[0],
            track.body_anchor[1] - expected_self[1],
        )
        if (
            self.self_track is not None
            and bbox_iou(track.body_bbox, self.self_track.body_bbox) >= 0.72
        ):
            self.last_candidate_rejections.append(
                f"track={track.track_id}:SELF_BBOX_OVERLAP_HARD_GATE"
            )
            return 0.0
        if separation <= max(8.0, self.config.merged_anchor_distance_px):
            self.last_candidate_rejections.append(
                f"track={track.track_id}:SELF_ANCHOR_OVERLAP_HARD_GATE"
            )
            return 0.0
        _, _, width, height = track.body_bbox
        area = width * height
        aspect = width / max(1.0, float(height))
        persistence = min(
            1.0,
            track.observations
            / max(1.0, self.config.enemy_confirm_frames + 2.0),
        )
        shape = max(0.0, 1.0 - abs(aspect - 0.65) / 1.30)
        size = (
            1.0
            if 180 <= area <= 6000
            else max(0.0, 1.0 - abs(area - 2200.0) / 6000.0)
        )
        movement = 0.0
        if len(track.movement_history) >= 2:
            first, last = (
                track.movement_history[0],
                track.movement_history[-1],
            )
            movement = min(
                1.0,
                math.hypot(last[0] - first[0], last[1] - first[1])
                / 24.0,
            )
        relative_proximity = max(
            0.0,
            1.0
            - max(abs(track.anchor_cell[0]), abs(track.anchor_cell[1]))
            / (self.config.roi_radius_cells + 1.0),
        )
        close_bonus = max(
            0.0,
            1.0
            - separation
            / max(1.0, self.config.close_enemy_distance_px * 2.0),
        )
        return (
            0.26 * persistence
            + 0.20 * shape
            + 0.13 * size
            + 0.10 * movement
            + 0.09 * track.body_confidence
            + 0.05 * min(1.0, track.confidence)
            + 0.08 * relative_proximity
            + 0.09 * close_bonus
        )

    def _select_context_enemy(
        self,
        arena_shape: Sequence[int],
        frame_index: int,
    ) -> None:
        if not self.config.enable_context_enemy:
            return
        if self.enemy_track_id is not None:
            current = self.tracks.get(self.enemy_track_id)
            if (
                current is not None
                and current.track_state is not TrackState.LOST
                and self._trainer_rejection_track(current) is None
            ):
                return
            self.enemy_track_id = None
        scored = [
            (self._enemy_candidate_score(track, arena_shape), track)
            for track in self.tracks.values()
        ]
        scored = [
            (score, track)
            for score, track in scored
            if score >= 0.54
        ]
        if not scored:
            self.pending_enemy_track_id = None
            self.pending_enemy_hits = 0
            return
        scored.sort(
            key=lambda item: (
                item[0],
                item[1].observations,
                item[1].body_confidence,
                -item[1].track_id,
            ),
            reverse=True,
        )
        score, candidate = scored[0]
        if self.pending_enemy_track_id == candidate.track_id:
            self.pending_enemy_hits += 1
        else:
            self.pending_enemy_track_id = candidate.track_id
            self.pending_enemy_hits = 1
        if self.pending_enemy_hits < 2:
            return
        if lock_track_role(
            candidate,
            SpriteRole.ENEMY,
            frame_index=frame_index,
            source="context_enemy",
            confidence=max(score, 0.72),
        ):
            candidate.confidence = max(candidate.confidence, score, 0.72)
            self.enemy_track_id = candidate.track_id
        self.pending_enemy_track_id = None
        self.pending_enemy_hits = 0

    def _close_candidate_score(
        self,
        observation: SpriteObservation,
        target: TrackedSprite,
    ) -> float:
        if (
            observation.body_anchor is None
            or observation.body_bbox is None
            or self.self_track is None
            or self.self_track.body_anchor is None
        ):
            return 0.0
        if self._self_conflict_observation(observation) is not None:
            return 0.0
        distance_self = math.hypot(
            observation.body_anchor[0] - self.self_track.body_anchor[0],
            observation.body_anchor[1] - self.self_track.body_anchor[1],
        )
        if distance_self > self.config.close_enemy_distance_px:
            return 0.0
        appearance = DescriptorFactory.similarity(
            target.appearance_signature,
            observation.descriptor,
        )
        target_anchor = target.predicted_anchor or target.body_anchor
        distance_target = self.config.close_enemy_distance_px
        if target_anchor is not None:
            distance_target = math.hypot(
                observation.body_anchor[0] - target_anchor[0],
                observation.body_anchor[1] - target_anchor[1],
            )
        proximity_self = max(
            0.0,
            1.0 - distance_self / self.config.close_enemy_distance_px,
        )
        proximity_target = max(
            0.0,
            1.0
            - distance_target
            / (self.config.close_enemy_distance_px * 1.5),
        )
        size = 0.0
        if target.body_bbox is not None:
            old_area = max(1, target.body_bbox[2] * target.body_bbox[3])
            new_area = max(
                1,
                observation.body_bbox[2] * observation.body_bbox[3],
            )
            size = min(old_area, new_area) / max(old_area, new_area)
        return (
            0.42 * appearance
            + 0.25 * proximity_target
            + 0.18 * proximity_self
            + 0.10 * size
            + 0.05 * observation.body_confidence
        )

    def _try_close_rebind(
        self,
        unmatched: list[SpriteObservation],
        *,
        frame_index: int,
    ) -> tuple[list[SpriteObservation], int | None]:
        if self.enemy_track_id is None:
            return unmatched, None
        target = self.tracks.get(self.enemy_track_id)
        if target is None or target.track_state is TrackState.TRACKED:
            self.pending_rebind_key = None
            self.pending_rebind_hits = 0
            return unmatched, None
        scored = [
            (self._close_candidate_score(observation, target), observation)
            for observation in unmatched
        ]
        scored = [
            (score, observation)
            for score, observation in scored
            if score >= 0.56
        ]
        if not scored:
            self.pending_rebind_key = None
            self.pending_rebind_hits = 0
            return unmatched, None
        scored.sort(
            key=lambda item: (item[0], item[1].body_confidence),
            reverse=True,
        )
        score, candidate = scored[0]
        key = candidate.anchor_cell
        if key == self.pending_rebind_key:
            self.pending_rebind_hits += 1
        else:
            self.pending_rebind_key = key
            self.pending_rebind_hits = 1
        if (
            self.pending_rebind_hits
            < self.config.close_reacquire_confirm_frames
        ):
            return unmatched, None
        self._update_track(target, candidate, frame_index, score)
        target.track_source = "rebound"
        target.role = SpriteRole.ENEMY
        target.role_locked = True
        target.known_enemy = True
        self.last_rebind_reason = "VISIBLE_CLOSE_CANDIDATE_REBOUND"
        self.pending_rebind_key = None
        self.pending_rebind_hits = 0
        return (
            [
                observation
                for observation in unmatched
                if observation.observation_id
                != candidate.observation_id
            ],
            target.track_id,
        )

    def invalidate_enemy_lock(self, reason: str) -> None:
        if self.enemy_track_id is None:
            return
        target = self.tracks.get(self.enemy_track_id)
        if target is not None:
            target.track_state = TrackState.TEMPORARILY_MISSING
            target.missing_frames = max(1, target.missing_frames)
            target.track_source = "reacquiring"
            target.rejection_reason = reason
        self.last_rebind_reason = reason

    def update(
        self,
        observations: Sequence[SpriteObservation],
        *,
        frame_index: int,
        arena_shape: Sequence[int],
        self_track: TrackedSprite | None = None,
        reserved_observation_ids: Sequence[int] = (),
        merged_observation_ids: Sequence[int] = (),
    ) -> tuple[TrackedSprite, ...]:
        self.last_candidate_rejections.clear()
        self.association_diagnostics.clear()
        self.role_flip_attempt = None
        self.role_flip_blocked = None
        self.shared_observation_blocked = False
        self.last_rebind_reason = None
        self.self_track = self_track
        self.player_track_id = (
            None if self_track is None else self_track.track_id
        )
        reserved = frozenset(reserved_observation_ids)
        merged = frozenset(merged_observation_ids)
        allowed_observations = []
        for observation in observations:
            if observation.observation_id in reserved:
                self.shared_observation_blocked = True
                self.last_candidate_rejections.append(
                    f"observation={observation.observation_id}:SELF_OBSERVATION_RESERVED"
                )
                continue
            if (
                observation.observation_id in merged
                or observation.merged_body
            ):
                self.last_candidate_rejections.append(
                    f"observation={observation.observation_id}:MERGED_BODY_EXCLUDED"
                )
                continue
            allowed_observations.append(observation)

        candidates: list[tuple[int, float, int, int]] = []
        active_tracks = list(self.tracks.values())
        for track in active_tracks:
            target_track = track.track_id == self.enemy_track_id
            threshold = (
                self.config.target_association_min_score
                if target_track
                else self.config.association_min_score
            )
            for observation_index, observation in enumerate(
                allowed_observations
            ):
                score = self._association_score(
                    track,
                    observation,
                    target_track=target_track,
                    arena_shape=arena_shape,
                )
                self.association_diagnostics.append(
                    {
                        "candidate_id": observation.observation_id,
                        "candidate_role": track.effective_role.value,
                        "candidate_score": score,
                        "position_score": None,
                        "appearance_score": DescriptorFactory.similarity(
                            track.appearance_signature,
                            observation.descriptor,
                        ),
                        "size_score": None,
                        "motion_score": None,
                        "role_gate_passed": score > 0.0,
                        "rejection_reason": (
                            None if score > 0.0 else "ASSOCIATION_GATE"
                        ),
                    }
                )
                if score >= threshold:
                    candidates.append(
                        (
                            1 if target_track else 0,
                            score,
                            track.track_id,
                            observation_index,
                        )
                    )
        candidates.sort(reverse=True)
        used_tracks: set[int] = set()
        used_observations: set[int] = set()
        for _, score, track_id, observation_index in candidates:
            if (
                track_id in used_tracks
                or observation_index in used_observations
            ):
                continue
            self._update_track(
                self.tracks[track_id],
                allowed_observations[observation_index],
                frame_index,
                score,
            )
            used_tracks.add(track_id)
            used_observations.add(observation_index)

        unmatched = [
            observation
            for index, observation in enumerate(allowed_observations)
            if index not in used_observations
        ]
        unmatched, rebound_track_id = self._try_close_rebind(
            unmatched,
            frame_index=frame_index,
        )
        if rebound_track_id is not None:
            used_tracks.add(rebound_track_id)

        target_track = (
            self.tracks.get(self.enemy_track_id)
            if self.enemy_track_id is not None
            else None
        )
        if (
            target_track is not None
            and target_track.anchor_cell is not None
            and target_track.track_state is TrackState.TRACKED
        ):
            unmatched = [
                observation
                for observation in unmatched
                if observation.anchor_cell is not None
                and (
                    observation.anchor_cell[0]
                    - target_track.anchor_cell[0]
                )
                ** 2
                + (
                    observation.anchor_cell[1]
                    - target_track.anchor_cell[1]
                )
                ** 2
                <= self.config.target_focus_radius_cells**2
            ]

        unmatched.sort(
            key=lambda item: (item.body_confidence, item.pixel_count),
            reverse=True,
        )
        for observation in unmatched:
            if len(self.tracks) >= self.config.maximum_active_tracks:
                break
            track = self._create_track(observation, frame_index)
            if track is not None:
                used_tracks.add(track.track_id)

        purge_ids = []
        for track in active_tracks:
            if track.track_id in used_tracks:
                continue
            track.missing_frames += 1
            track.observation_id = None
            track.predicted_anchor = self._predicted_anchor(track)
            track.track_source = "predicted"
            missing_limit = (
                self.config.target_missing_grace_frames
                if track.track_id == self.enemy_track_id
                else self.config.maximum_missing_frames
            )
            if track.missing_frames <= missing_limit:
                track.track_state = TrackState.TEMPORARILY_MISSING
            else:
                track.track_state = TrackState.LOST
                purge_ids.append(track.track_id)
        for track_id in purge_ids:
            if self.enemy_track_id == track_id:
                self.enemy_track_id = None
            if self.pending_enemy_track_id == track_id:
                self.pending_enemy_track_id = None
                self.pending_enemy_hits = 0
            self.tracks.pop(track_id, None)

        for track in self.tracks.values():
            if track.track_state is TrackState.TRACKED:
                self._classify_known_role(track, frame_index)
        self._select_context_enemy(arena_shape, frame_index)

        self.close_candidate_count = 0
        if self_track is not None and self_track.body_anchor is not None:
            for observation in allowed_observations:
                if observation.body_anchor is None:
                    continue
                distance = math.hypot(
                    observation.body_anchor[0]
                    - self_track.body_anchor[0],
                    observation.body_anchor[1]
                    - self_track.body_anchor[1],
                )
                if (
                    distance <= self.config.close_enemy_distance_px
                    and self._self_conflict_observation(observation)
                    is None
                ):
                    self.close_candidate_count += 1
        return tuple(
            sorted(self.tracks.values(), key=lambda item: item.track_id)
        )
