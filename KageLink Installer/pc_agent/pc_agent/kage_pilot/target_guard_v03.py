from __future__ import annotations

from .entity_observer import FlowEstimate, ObserverConfig
from .entity_tracker_v03 import _distance
from .water_filter_v03 import _path_efficiency
from .water_filter_v03c import TemporalRecurrenceWaterAwareEntityTracker


class TargetGuardWaterAwareEntityTracker(TemporalRecurrenceWaterAwareEntityTracker):
    """Temporal-recurrence tracker with conservative TARGET eligibility.

    Enemy Score remains useful diagnostics, but it is no longer sufficient by itself
    to acquire TARGET. Real BYOND validation showed animated water producing large
    scores despite already being recognized as dynamic scenery.

    TARGET eligibility is intentionally stricter than ENTITY tracking:
    - LOST identities remain tracked/reacquirable but are never active TARGETs;
    - OCCLUDED player contact remains targetable;
    - a visible entity close to PLAYER may be targetable after a small persistence gate;
    - a distant entity must show sustained coherent approach behaviour;
    - a far entity inside a mature dynamic-background region is never targetable;
    - very young/noisy tracks cannot acquire TARGET immediately.
    """

    def __init__(self, config: ObserverConfig) -> None:
        # Keep environmental memory long enough that the same water strip is not
        # repeatedly relearned while the player remains in the same map area.
        if hasattr(config, "background_memory_ttl"):
            config.background_memory_ttl = max(30.0, float(config.background_memory_ttl))
        super().__init__(config)
        self.target_min_age_seconds = 0.70
        self.target_min_observations = 4
        self.target_near_distance = 145.0
        self.target_far_max_distance = 280.0
        self.target_dynamic_region_strength = 0.42

    def _coherent_approach(self, track_id: int) -> bool:
        track = self._tracks[track_id]
        coherence = _path_efficiency(track.history)
        return (
            track.approaching_player
            and track.approach_speed >= 5.0
            and track.residual_speed >= 8.0
            and coherence >= 0.62
            and track.hostility_memory >= 0.12
            and track.observations >= 5
        )

    def target_eligible(
        self,
        track_id: int,
        *,
        player_center: tuple[float, float],
        now: float,
        for_keep: bool = False,
    ) -> bool:
        """Return whether an ENTITY may currently act as active TARGET.

        Tracking identity and target selection are deliberately separate. LOST tracks
        can remain in memory for reacquisition while exposing no active combat lock.
        """

        track = self._tracks.get(track_id)
        context = self._contexts.get(track_id)
        if track is None or context is None:
            return False

        if context.state == "LOST":
            return False

        if context.state == "OCCLUDED":
            # Known contact at PLAYER boundary is direct combat evidence.
            return True

        if context.state != "VISIBLE":
            return False

        age = max(0.0, now - track.created_at)
        if age < self.target_min_age_seconds or track.observations < self.target_min_observations:
            return False

        distance = _distance(track.center, player_center)
        region_strength = self.background.region_strength_bbox(track.bbox)

        # Once the environment model strongly recognizes a far region as animated
        # scenery, no numerical Enemy Score can turn that region into TARGET. A real
        # opponent crossing that region becomes eligible again when it closes on the
        # player; OCCLUDED contact is handled above.
        if region_strength >= self.target_dynamic_region_strength and distance > self.target_near_distance:
            return False

        # Nearby visible candidates are allowed after the persistence gate. This is
        # the normal Dojo/melee case and does not depend on perfect Enemy Score.
        if distance <= self.target_near_distance:
            return True

        # Distant entities must actually travel coherently toward PLAYER. This is much
        # harder for animated water to satisfy than a one-frame motion spike.
        if distance <= self.target_far_max_distance and self._coherent_approach(track_id):
            return True

        return False

    def _apply_target_guard(self, *, player_center: tuple[float, float], now: float) -> None:
        """Keep scores readable while target_eligible() provides the hard safety gate."""

        acquire = float(getattr(self.config, "target_acquire_threshold", self.config.enemy_threshold))
        keep = float(getattr(self.config, "target_keep_threshold", max(0.0, acquire - 15.0)))

        for track_id, track in self._tracks.items():
            context = self._contexts.get(track_id)
            if context is None:
                continue

            if context.state == "OCCLUDED":
                continue

            if context.state == "LOST":
                # LOST may remain as ENTITY memory but must never numerically look like
                # an active target candidate either.
                track.enemy_score = min(track.enemy_score, max(0.0, keep - 8.0))
                continue

            if not self.target_eligible(
                track_id,
                player_center=player_center,
                now=now,
                for_keep=False,
            ):
                # Preserve diagnostic ranking but keep ineligible tracks below acquire.
                track.enemy_score = min(track.enemy_score, max(0.0, acquire - 1.0))

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
