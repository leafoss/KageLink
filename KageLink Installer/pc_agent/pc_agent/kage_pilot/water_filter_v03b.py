from __future__ import annotations

from .entity_observer import ObserverConfig
from .entity_tracker_v03 import _distance
from .water_filter_v03 import WaterAwareEntityTracker, _path_efficiency


class CombatSelectiveWaterAwareEntityTracker(WaterAwareEntityTracker):
    """Protect only coherent combat-like tracks from aggressive water filtering."""

    def __init__(self, config: ObserverConfig) -> None:
        super().__init__(config)

    def _combat_like(self, track_id: int, player_center: tuple[float, float]) -> bool:
        track = self._tracks[track_id]
        context = self._contexts.get(track_id)
        guard = float(getattr(self.config, "background_player_guard", 78.0))
        distance = _distance(track.center, player_center)
        coherence = _path_efficiency(track.history)

        if distance <= guard + 55.0:
            return True
        if context is not None and context.state == "OCCLUDED":
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

    def _update_protected_centers(self, player_center: tuple[float, float]) -> None:
        self.background.protected_centers = tuple(
            track.center
            for track_id, track in self._tracks.items()
            if self._combat_like(track_id, player_center)
        )

    def _prune_background_tracks(self, player_center: tuple[float, float]) -> None:
        pruned = 0
        for track_id in list(self._tracks):
            track = self._tracks[track_id]
            if self._combat_like(track_id, player_center):
                continue

            region_strength = self.background.region_strength_bbox(track.bbox)
            if region_strength < 0.55:
                continue

            coherence = _path_efficiency(track.history)
            background_like_motion = coherence < 0.65 or track.residual_speed < 14.0
            if not background_like_motion:
                continue

            context = self._contexts.get(track_id)
            if context is not None:
                context.state = "BACKGROUND_DYNAMIC"
            del self._tracks[track_id]
            self._contexts.pop(track_id, None)
            self._dormant.pop(track_id, None)
            pruned += 1

        self.background_pruned_last_frame = pruned
