from __future__ import annotations

import math
from typing import Sequence

from .pr27_fragments import DescriptorFactory
from .pr27_model import CELL_SIZE_PX, PR27Config, SpriteClass, SpriteObservation, TrackState, TrackedSprite
from .pr27_registry import KnownSpriteRegistry


class SpriteTracker:
    def __init__(self, config: PR27Config, registry: KnownSpriteRegistry | None = None) -> None:
        self.config = config.normalized()
        self.registry = registry or KnownSpriteRegistry()
        self.tracks: dict[int, TrackedSprite] = {}
        self.next_track_id = 1
        self.player_track_id: int | None = None
        self.enemy_track_id: int | None = None

    @staticmethod
    def _cell_distance(left: frozenset[tuple[int, int]], right: frozenset[tuple[int, int]]) -> int:
        if not left or not right:
            return 999
        return min(max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a in left for b in right)

    @staticmethod
    def _bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        left, top = max(ax, bx), max(ay, by)
        right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        intersection = max(0, right - left) * max(0, bottom - top)
        union = max(1, aw * ah + bw * bh - intersection)
        return intersection / union

    @staticmethod
    def _predicted_center(track: TrackedSprite) -> tuple[float, float]:
        if len(track.movement_history) < 2:
            return track.center
        previous = track.movement_history[-2]
        current = track.movement_history[-1]
        return current[0] + (current[0] - previous[0]), current[1] + (current[1] - previous[1])

    def _association_score(
        self,
        track: TrackedSprite,
        observation: SpriteObservation,
        *,
        target_track: bool,
        arena_shape: Sequence[int],
    ) -> float:
        distance = self._cell_distance(track.current_cells, observation.cells)
        allowed_step = self.config.maximum_track_cell_step + track.missing_frames
        if target_track:
            allowed_step += self.config.target_focus_radius_cells
        if distance > allowed_step:
            return 0.0
        appearance = DescriptorFactory.similarity(track.appearance_signature, observation.descriptor)
        if target_track:
            arena_h, arena_w = int(arena_shape[0]), int(arena_shape[1])
            player_anchor = (
                arena_w * self.config.player_anchor_x_ratio,
                arena_h * self.config.player_anchor_y_ratio,
            )
            player_distance = math.hypot(
                observation.center[0] - player_anchor[0],
                observation.center[1] - player_anchor[1],
            )
            if player_distance <= self.config.player_anchor_radius_px * 1.25:
                return 0.0
            if appearance < self.config.target_minimum_appearance:
                return 0.0
        temporal = max(0.0, 1.0 - distance / max(1.0, allowed_step + 1.0))
        predicted = self._predicted_center(track)
        center_distance = math.hypot(
            observation.center[0] - predicted[0],
            observation.center[1] - predicted[1],
        )
        proximity = max(0.0, 1.0 - center_distance / max(CELL_SIZE_PX, CELL_SIZE_PX * (allowed_step + 1)))
        overlap = self._bbox_iou(track.native_bbox, observation.native_bbox)
        old_area = max(1, track.native_bbox[2] * track.native_bbox[3])
        new_area = max(1, observation.native_bbox[2] * observation.native_bbox[3])
        size = min(old_area, new_area) / max(old_area, new_area)
        score = 0.50 * appearance + 0.20 * temporal + 0.15 * proximity + 0.10 * size + 0.05 * overlap
        if target_track:
            score = min(1.0, score + 0.08)
        return score

    def _update_track(self, track: TrackedSprite, observation: SpriteObservation, frame_index: int, score: float) -> None:
        track.previous_cells = track.current_cells
        track.current_cells = observation.cells
        track.fragments = observation.fragments
        track.native_bbox = observation.native_bbox
        track.combined_mask = observation.combined_mask
        track.appearance_signature = observation.descriptor
        track.last_seen_frame = frame_index
        track.missing_frames = 0
        track.observations += 1
        track.confidence = max(track.confidence * 0.6, score)
        track.track_state = TrackState.TRACKED
        track.movement_history.append(observation.center)

    def _create_track(self, observation: SpriteObservation, frame_index: int) -> TrackedSprite:
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
            confidence=0.50,
        )
        track.movement_history.append(observation.center)
        self.tracks[track.track_id] = track
        self.next_track_id += 1
        return track

    def _classify(self, track: TrackedSprite, arena_shape: Sequence[int]) -> None:
        known, score = self.registry.best_match(track.appearance_signature)
        if known is not None and score >= self.config.known_sprite_threshold:
            track.classification = known.category
            track.known_sprite_id = known.sprite_id
            track.known_enemy = known.category is SpriteClass.ENEMY
            track.confidence = max(track.confidence, score)

        arena_h, arena_w = int(arena_shape[0]), int(arena_shape[1])
        anchor = (
            arena_w * self.config.player_anchor_x_ratio,
            arena_h * self.config.player_anchor_y_ratio,
        )
        center = track.center
        anchor_distance = math.hypot(center[0] - anchor[0], center[1] - anchor[1])
        if (
            track.observations >= self.config.player_confirm_frames
            and anchor_distance <= self.config.player_anchor_radius_px
            and (self.player_track_id is None or self.player_track_id == track.track_id)
        ):
            track.classification = SpriteClass.PLAYER
            track.known_enemy = False
            self.player_track_id = track.track_id
            return

        if track.classification is SpriteClass.UNKNOWN and self.config.enable_context_enemy:
            if (
                track.observations >= self.config.enemy_confirm_frames
                and track.track_id != self.player_track_id
                and (self.enemy_track_id is None or self.enemy_track_id == track.track_id)
            ):
                track.classification = SpriteClass.ENEMY
                track.known_enemy = True
                track.confidence = max(track.confidence, 0.70)
                self.enemy_track_id = track.track_id

    def update(
        self,
        observations: Sequence[SpriteObservation],
        *,
        frame_index: int,
        arena_shape: Sequence[int],
    ) -> tuple[TrackedSprite, ...]:
        candidates: list[tuple[int, float, int, int]] = []
        active_tracks = list(self.tracks.values())
        for track in active_tracks:
            target_track = track.track_id == self.enemy_track_id
            threshold = (
                self.config.target_association_min_score
                if target_track
                else self.config.association_min_score
            )
            for observation_index, observation in enumerate(observations):
                score = self._association_score(
                    track,
                    observation,
                    target_track=target_track,
                    arena_shape=arena_shape,
                )
                if score >= threshold:
                    candidates.append((1 if target_track else 0, score, track.track_id, observation_index))
        candidates.sort(reverse=True)
        used_tracks: set[int] = set()
        used_observations: set[int] = set()
        for _, score, track_id, observation_index in candidates:
            if track_id in used_tracks or observation_index in used_observations:
                continue
            self._update_track(self.tracks[track_id], observations[observation_index], frame_index, score)
            used_tracks.add(track_id)
            used_observations.add(observation_index)

        unmatched = [
            observation
            for index, observation in enumerate(observations)
            if index not in used_observations
        ]
        unmatched.sort(key=lambda item: item.pixel_count, reverse=True)
        for observation in unmatched:
            if len(self.tracks) >= self.config.maximum_active_tracks:
                break
            track = self._create_track(observation, frame_index)
            used_tracks.add(track.track_id)

        purge_ids: list[int] = []
        for track in active_tracks:
            if track.track_id in used_tracks:
                continue
            track.missing_frames += 1
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
            if self.player_track_id == track_id:
                self.player_track_id = None
            if self.enemy_track_id == track_id:
                self.enemy_track_id = None
            self.tracks.pop(track_id, None)

        for track in self.tracks.values():
            if track.track_state is TrackState.TRACKED:
                self._classify(track, arena_shape)
        return tuple(sorted(self.tracks.values(), key=lambda item: item.track_id))
