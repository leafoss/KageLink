from __future__ import annotations

from .entity_observer import FlowEstimate, ObserverConfig
from .entity_tracker_v03 import _distance
from .water_filter_v03 import _path_efficiency
from .water_filter_v03c import TemporalRecurrenceWaterAwareEntityTracker


class TargetGuardWaterAwareEntityTracker(TemporalRecurrenceWaterAwareEntityTracker):
    """Temporal-recurrence tracker with conservative TARGET scoring.

    Real BYOND validation showed that animated water could still accumulate a high
    Enemy Score and even remain selected while the track state was LOST. The
    observer's generic hysteresis only sees numeric score, so this layer converts
    tracking context into a safer score before target selection runs.

    Rules:
    - a LOST track is capped below acquire threshold;
    - a recently-lost current identity may remain just above keep threshold for a
      short grace period, allowing brief contour drop-outs without an immediate ID
      switch;
    - old LOST tracks fall below keep threshold;
    - mature dynamic-background regions cap non-combat-like tracks below acquire;
    - very young tracks cannot become TARGET immediately;
    - OCCLUDED contact is intentionally preserved because it is strong combat
      evidence and already uses the player-boundary guard.
    """

    def __init__(self, config: ObserverConfig) -> None:
        # Longer environmental memory avoids repeatedly relearning the same animated
        # water strip while the player remains in the same area.
        if hasattr(config, "background_memory_ttl"):
            config.background_memory_ttl = max(30.0, float(config.background_memory_ttl))
        super().__init__(config)
        self.target_lost_grace_seconds = 0.8

    def _combat_like_for_target(self, track_id: int, player_center: tuple[float, float]) -> bool:
        track = self._tracks[track_id]
        context = self._contexts.get(track_id)
        guard = float(getattr(self.config, "background_player_guard", 78.0))
        distance = _distance(track.center, player_center)
        coherence = _path_efficiency(track.history)

        if context is not None and context.state == "OCCLUDED":
            return True
        if distance <= guard + 55.0:
            return True

        approaching_coherently = (
            track.approaching_player
            and track.residual_speed >= 8.0
            and coherence >= 0.45
        )
        established_hostile_motion = (
            track.hostility_memory >= 0.25
            and track.residual_speed >= 12.0
            and coherence >= 0.55
        )
        return approaching_coherently or established_hostile_motion

    def _apply_target_guard(self, *, player_center: tuple[float, float], now: float) -> None:
        acquire = float(getattr(self.config, "target_acquire_threshold", self.config.enemy_threshold))
        keep = float(getattr(self.config, "target_keep_threshold", max(0.0, acquire - 15.0)))
        guard = float(getattr(self.config, "background_player_guard", 78.0))

        for track_id, track in self._tracks.items():
            context = self._contexts.get(track_id)
            if context is None:
                continue

            # Prevent one or two noisy observations from immediately becoming a
            # target even if instantaneous motion produces a large Enemy Score.
            age = max(0.0, now - track.created_at)
            if context.state != "OCCLUDED" and (age < 0.45 or track.observations < 3):
                track.enemy_score = min(track.enemy_score, max(0.0, acquire - 1.0))

            if context.state == "LOST":
                since_seen = max(0.0, now - track.last_seen)
                if since_seen <= self.target_lost_grace_seconds:
                    # Can keep an already-selected target, but cannot be newly
                    # acquired because this ceiling stays below acquire threshold.
                    track.enemy_score = min(track.enemy_score, min(acquire - 1.0, keep + 2.0))
                else:
                    track.enemy_score = min(track.enemy_score, max(0.0, keep - 8.0))
                continue

            if context.state == "OCCLUDED":
                # Contact with PLAYER is valid combat evidence. Do not let the
                # background model suppress it.
                continue

            region_strength = self.background.region_strength_bbox(track.bbox)
            distance = _distance(track.center, player_center)
            inside_dynamic_region = region_strength >= 0.48 and distance > guard + 45.0
            if inside_dynamic_region and not self._combat_like_for_target(track_id, player_center):
                track.enemy_score = min(track.enemy_score, max(0.0, keep - 5.0))

    def update(
        self,
        candidates,
        *,
        flow: FlowEstimate,
        player_center: tuple[float, float],
        now: float,
    ):
        super().update(candidates, flow=flow, player_center=player_center, now=now)
        self._apply_target_guard(player_center=player_center, now=now)
        return self.tracks
