from __future__ import annotations

from .grid_target_observer_v03d import TileCalibratedGridTargetObserver


class ParticleSafeGridTargetObserver(TileCalibratedGridTargetObserver):
    """Live-control observer that rejects tiny/non-character-like distant pursuit targets.

    The normal v0.3 observer intentionally exposes many small contour candidates for
    diagnostics. That is useful in read-only mode, but real movement needs a stricter
    authority boundary: outside local melee contact, a target must also have a plausible
    character-like bounding shape before it may drive navigation.
    """

    def _grid_eligible(self, track, state, *, for_keep: bool) -> bool:
        metrics = self._last_metrics[track.track_id]
        if metrics.grid_distance > 1 and not self._character_like(track):
            return False
        return super()._grid_eligible(track, state, for_keep=for_keep)
