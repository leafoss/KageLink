from __future__ import annotations

import math
from typing import Iterable

from .entity_observer import (
    Candidate,
    EntityTrack,
    EntityTracker,
    FlowEstimate,
    ObserverConfig,
    score_enemy,
)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


class MeleeAwareEntityTracker(EntityTracker):
    """v0.3 tracker that preserves known entities inside the player exclusion zone.

    The player exclusion radius exists to stop the player's own motion contour from
    spawning a false ENTITY. It must not erase an already tracked opponent when that
    opponent closes to melee range or overlaps the player during contact/knockback.

    Matching therefore considers *all* candidates. The exclusion radius is applied
    only when deciding whether an unmatched candidate may create a brand-new track.
    """

    def __init__(self, config: ObserverConfig) -> None:
        super().__init__(config)

    def update(
        self,
        candidates: Iterable[Candidate],
        *,
        flow: FlowEstimate,
        player_center: tuple[float, float],
        now: float,
    ) -> tuple[EntityTrack, ...]:
        candidates = list(candidates)

        predicted = {
            track_id: track.predicted_center(flow)
            for track_id, track in self._tracks.items()
        }
        unmatched_tracks = set(self._tracks)
        unmatched_candidates = set(range(len(candidates)))
        matches: list[tuple[int, int]] = []

        pairs: list[tuple[float, int, int]] = []
        for track_id, point in predicted.items():
            for candidate_index, candidate in enumerate(candidates):
                distance = _distance(point, candidate.center)
                if distance <= self.config.track_match_distance:
                    pairs.append((distance, track_id, candidate_index))
        pairs.sort(key=lambda item: item[0])

        for _, track_id, candidate_index in pairs:
            if track_id not in unmatched_tracks or candidate_index not in unmatched_candidates:
                continue
            unmatched_tracks.remove(track_id)
            unmatched_candidates.remove(candidate_index)
            matches.append((track_id, candidate_index))

        for track_id, candidate_index in matches:
            track = self._tracks[track_id]
            track.observe(
                candidates[candidate_index],
                now=now,
                player_center=player_center,
                predicted_center=predicted[track_id],
            )

        for track_id in list(unmatched_tracks):
            track = self._tracks[track_id]
            track.shift_with_camera(flow)
            track.decay(now=now, player_center=player_center)
            if now - track.last_seen > self.config.track_ttl_seconds:
                del self._tracks[track_id]

        for candidate_index in sorted(unmatched_candidates):
            candidate = candidates[candidate_index]

            # Player exclusion is a spawn guard only. A known entity that enters
            # this zone has already been matched above and therefore survives.
            if _distance(candidate.center, player_center) <= self.config.player_exclusion_radius:
                continue

            track = EntityTrack(
                track_id=self._next_id,
                bbox=candidate.bbox,
                center=candidate.center,
                created_at=now,
                last_seen=now,
                motion_energy=candidate.motion_energy,
                edge_density=candidate.edge_density,
                shape_score=candidate.shape_score,
            )
            track.enemy_score = score_enemy(track, player_center)
            self._tracks[track.track_id] = track
            self._next_id += 1

        return self.tracks
