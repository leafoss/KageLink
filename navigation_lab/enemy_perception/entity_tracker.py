from __future__ import annotations

from datetime import datetime, timezone

from .entity_features import EntityFeatureExtractor
from .models import EntityObservation, EntityTrack


class EntityTracker:
    """Greedy explainable tracker using world-cell proximity and masked visual similarity."""

    def __init__(
        self,
        ttl_frames: int = 10,
        min_similarity: float = 0.72,
        max_cell_distance: int = 2,
    ) -> None:
        self.ttl_frames = max(1, int(ttl_frames))
        self.min_similarity = float(min_similarity)
        self.max_cell_distance = int(max_cell_distance)
        self.tracks: dict[str, EntityTrack] = {}
        self._next = 1

    @staticmethod
    def _distance(
        left: tuple[int, int] | None,
        right: tuple[int, int] | None,
    ) -> int:
        if left is None or right is None:
            return 99
        return abs(left[0] - right[0]) + abs(left[1] - right[1])

    def update(
        self,
        observations: list[EntityObservation],
        frame_index: int,
        timestamp: str | None = None,
    ) -> tuple[list[dict], list[EntityTrack]]:
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        available = set(self.tracks)
        events: list[dict] = []

        for observation in observations:
            best_id: str | None = None
            best_score = -1.0
            for track_id in list(available):
                track = self.tracks[track_id]
                distance = self._distance(
                    track.current_world_cell,
                    observation.region.anchor_world_cell,
                )
                if distance > self.max_cell_distance:
                    continue
                visual = EntityFeatureExtractor.similarity(
                    track.feature,
                    observation.feature,
                )
                if visual < self.min_similarity:
                    continue
                proximity = max(
                    0.0,
                    1.0 - distance / max(1, self.max_cell_distance + 1),
                )
                score = 0.8 * visual + 0.2 * proximity
                if score > best_score:
                    best_score = score
                    best_id = track_id

            if best_id is None:
                track_id = f"ENT-{self._next:06d}"
                self._next += 1
                track = EntityTrack(
                    track_id=track_id,
                    feature=list(observation.feature),
                    classification=observation.classification,
                    first_seen_frame=frame_index,
                    last_seen_frame=frame_index,
                    first_seen_at=timestamp,
                    last_seen_at=timestamp,
                    current_screen_cell=observation.region.anchor_screen_cell,
                    current_world_cell=observation.region.anchor_world_cell,
                    covered_cells=list(observation.region.covered_cells),
                    position_history=[observation.region.anchor_world_cell],
                )
                self.tracks[track_id] = track
                events.append({"event": "entity_created", "track_id": track_id})
            else:
                available.remove(best_id)
                track = self.tracks[best_id]
                previous = track.current_world_cell
                track.previous_world_cell = previous
                track.current_world_cell = observation.region.anchor_world_cell
                track.current_screen_cell = observation.region.anchor_screen_cell
                track.covered_cells = list(observation.region.covered_cells)
                track.last_seen_frame = frame_index
                track.last_seen_at = timestamp
                if len(track.feature) == len(observation.feature):
                    track.feature = [
                        0.7 * old + 0.3 * new
                        for old, new in zip(track.feature, observation.feature)
                    ]
                else:
                    track.feature = list(observation.feature)
                if observation.classification.confidence > track.classification.confidence:
                    track.classification = observation.classification
                moved = (
                    previous is not None
                    and track.current_world_cell is not None
                    and previous != track.current_world_cell
                )
                if moved:
                    track.movement_count += 1
                    track.stationary_frame_count = 0
                    events.append(
                        {
                            "event": "entity_moved",
                            "track_id": track.track_id,
                            "from": previous,
                            "to": track.current_world_cell,
                        }
                    )
                else:
                    track.stationary_frame_count += 1
                track.position_history.append(track.current_world_cell)
                track.position_history = track.position_history[-64:]

            observation.track_id = track.track_id
            observation.previous_world_cell = track.previous_world_cell
            observation.movement_detected = (
                track.previous_world_cell is not None
                and track.current_world_cell != track.previous_world_cell
            )

        expired: list[EntityTrack] = []
        for track_id, track in list(self.tracks.items()):
            if frame_index - track.last_seen_frame > self.ttl_frames:
                expired.append(track)
                del self.tracks[track_id]
                events.append({"event": "entity_expired", "track_id": track_id})
        return events, expired
