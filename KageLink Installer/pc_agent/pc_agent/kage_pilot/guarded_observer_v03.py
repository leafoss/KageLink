from __future__ import annotations

from dataclasses import replace

import numpy as np

from .entity_observer import ObserverState
from .observer_runtime_v03 import StableTargetObserver


class TargetEligibleObserver(StableTargetObserver):
    """Stable observer whose active TARGET must pass tracker eligibility.

    The tracker is allowed to remember many ENTITY identities for diagnostics and
    reacquisition. Active TARGET is deliberately stricter: a high Enemy Score alone
    cannot create a combat lock when the tracker says the identity is LOST or belongs
    to a strong dynamic-background region.
    """

    def process(self, frame_bgr: np.ndarray, *, timestamp: float | None = None) -> ObserverState:
        state = super().process(frame_bgr, timestamp=timestamp)
        tracker = self.tracker
        eligibility = getattr(tracker, "target_eligible", None)
        if not callable(eligibility):
            return state

        current_id = self._locked_target_id
        eligible_tracks = []
        for track in state.tracks:
            if eligibility(
                track.track_id,
                player_center=state.player_center,
                now=state.timestamp,
                for_keep=(track.track_id == current_id),
            ):
                eligible_tracks.append(track)

        eligible_by_id = {track.track_id: track for track in eligible_tracks}
        current = eligible_by_id.get(current_id) if current_id is not None else None

        if current is not None and current.enemy_score >= self.config.target_keep_threshold:
            selected_id = current.track_id
        else:
            candidate = max(eligible_tracks, key=lambda track: track.enemy_score, default=None)
            selected_id = (
                candidate.track_id
                if candidate is not None and candidate.enemy_score >= self.config.target_acquire_threshold
                else None
            )

        self._locked_target_id = selected_id
        if state.target_id == selected_id:
            return state
        return replace(state, target_id=selected_id)
