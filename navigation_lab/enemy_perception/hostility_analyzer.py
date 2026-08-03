from __future__ import annotations

from .models import (
    EntityClass,
    EntityObservation,
    EntityTrack,
    HostilityState,
)


class HostilityAnalyzer:
    """Explainable temporal scoring that separates entity motion from player motion."""

    def __init__(self, decay_interval_frames: int = 20) -> None:
        self.decay_interval_frames = max(1, int(decay_interval_frames))

    @staticmethod
    def manhattan(
        left: tuple[int, int] | None,
        right: tuple[int, int] | None,
    ) -> int | None:
        if left is None or right is None:
            return None
        return abs(left[0] - right[0]) + abs(left[1] - right[1])

    def update(
        self,
        track: EntityTrack,
        observation: EntityObservation,
        player_world: tuple[int, int] | None,
        player_stationary: bool,
        frame_index: int,
        attack_detected: bool = False,
        hp_loss_detected: bool = False,
    ) -> list[dict]:
        events: list[dict] = []
        distance = self.manhattan(track.current_world_cell, player_world)
        previous_distance = track.distance_history[-1] if track.distance_history else None
        observation.distance_to_player = distance
        observation.previous_distance_to_player = previous_distance
        if distance is not None:
            track.distance_history.append(distance)
            track.distance_history = track.distance_history[-64:]

        reasons: list[str] = []
        delta = 0
        if observation.movement_detected and track.last_scored_frame != frame_index:
            delta += 1
            reasons.append("entity_moved")
            if previous_distance is not None and distance is not None and distance < previous_distance:
                observation.approaching = True
                observation.movement_state = "approaching"
                delta += 2
                reasons.append("distance_decreased_by_entity_motion")
                track.approach_streak += 1
                if player_stationary:
                    delta += 3
                    reasons.append("entity_approached_while_player_stationary")
                if track.approach_streak >= 2:
                    delta += 2
                    reasons.append("repeated_approach")
                if track.previous_world_cell and track.current_world_cell:
                    vector = (
                        track.current_world_cell[0] - track.previous_world_cell[0],
                        track.current_world_cell[1] - track.previous_world_cell[1],
                    )
                    if track.last_move_vector is not None and vector != track.last_move_vector:
                        delta += 4
                        reasons.append("route_corrected_toward_player")
                    track.last_move_vector = vector
            else:
                track.approach_streak = 0

        if (
            track.classification.category == EntityClass.ENEMY
            and track.classification.confidence >= 0.95
            and "enemy_by_visual_class" not in track.hostility_reasons
        ):
            delta += 4
            reasons.append("enemy_by_visual_class")
        if attack_detected:
            delta += 5
            reasons.append("known_attack_animation")
        if hp_loss_detected:
            delta += 8
            reasons.append("hp_loss_correlated_with_nearby_entity")
        if (
            delta == 0
            and track.last_scored_frame
            and frame_index - track.last_scored_frame >= self.decay_interval_frames
            and track.hostility_score > 0
        ):
            delta = -1
            reasons.append("hostility_decay")

        if delta:
            track.hostility_score = max(0, track.hostility_score + delta)
            track.last_scored_frame = frame_index
            track.hostility_reasons.extend(reasons)
            track.hostility_reasons = track.hostility_reasons[-32:]
            events.append(
                {
                    "event": "hostility_score_changed",
                    "track_id": track.track_id,
                    "score_delta": delta,
                    "score": track.hostility_score,
                    "reasons": reasons,
                    "previous_distance": previous_distance,
                    "current_distance": distance,
                }
            )

        previous_state = track.hostility_state
        score = track.hostility_score
        if score >= 20:
            state = HostilityState.ATTACK_RECOMMENDED
        elif (hp_loss_detected and attack_detected) or score >= 16:
            state = HostilityState.HOSTILE_CONFIRMED
        elif score >= 12:
            state = HostilityState.HOSTILE_PROBABLE
        elif observation.approaching and track.approach_streak >= 2:
            state = HostilityState.FOLLOWING_ENTITY
        elif observation.approaching:
            state = HostilityState.APPROACHING_ENTITY
        elif track.movement_count > 0:
            state = HostilityState.MOBILE_ENTITY
        elif track.stationary_frame_count >= 2:
            state = HostilityState.STATIC_OVERLAY
        else:
            state = HostilityState.UNKNOWN_VISUAL
        track.hostility_state = state

        if state != previous_state:
            events.append(
                {
                    "event": "hostility_state_changed",
                    "track_id": track.track_id,
                    "from": previous_state.value,
                    "to": state.value,
                }
            )
        if state in {HostilityState.HOSTILE_CONFIRMED, HostilityState.ATTACK_RECOMMENDED}:
            events.append({"event": "enemy_confirmed", "track_id": track.track_id})
        if state == HostilityState.ATTACK_RECOMMENDED:
            observation.attack_recommended = True
            events.append(
                {
                    "event": "attack_recommended",
                    "track_id": track.track_id,
                    "score": score,
                    "reasons": list(track.hostility_reasons[-8:]),
                }
            )

        observation.hostility_score = track.hostility_score
        observation.hostility_state = state
        observation.hostility_reasons = list(reasons)
        return events
