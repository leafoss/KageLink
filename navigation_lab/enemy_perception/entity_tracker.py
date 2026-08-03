from __future__ import annotations

from datetime import datetime, timezone

from .entity_features import EntityFeatureExtractor
from .models import EntityObservation, EntityTrack


class EntityTracker:
    """Greedy local tracker using position, appearance and shape continuity."""

    def __init__(
        self,
        ttl_frames: int = 10,
        min_similarity: float = 0.72,
        max_cell_distance: int = 2,
        interest_radius_cells: int | None = None,
        min_area_ratio: float = 0.25,
        min_width_ratio: float = 0.25,
        min_height_ratio: float = 0.35,
    ) -> None:
        self.ttl_frames = max(1, int(ttl_frames))
        self.min_similarity = float(min_similarity)
        self.max_cell_distance = int(max_cell_distance)
        self.interest_radius_cells = (
            None if interest_radius_cells is None else max(1, int(interest_radius_cells))
        )
        self.min_area_ratio = min(1.0, max(0.01, float(min_area_ratio)))
        self.min_width_ratio = min(1.0, max(0.01, float(min_width_ratio)))
        self.min_height_ratio = min(1.0, max(0.01, float(min_height_ratio)))
        self.tracks: dict[str, EntityTrack] = {}
        self._track_shapes: dict[str, tuple[float, float, float]] = {}
        self._next = 1

    @staticmethod
    def _distance(
        left: tuple[int, int] | None,
        right: tuple[int, int] | None,
    ) -> int:
        if left is None or right is None:
            return 99
        return abs(left[0] - right[0]) + abs(left[1] - right[1])

    @staticmethod
    def _observation_shape(
        observation: EntityObservation,
    ) -> tuple[float, float, float]:
        x0, y0, x1, y1 = observation.region.bounding_box_px
        width = float(max(1, x1 - x0))
        height = float(max(1, y1 - y0))
        return width, height, width * height

    @staticmethod
    def _ratio(left: float, right: float) -> float:
        larger = max(float(left), float(right), 1.0)
        return min(float(left), float(right)) / larger

    def _shape_compatible(
        self,
        track_id: str,
        observation: EntityObservation,
    ) -> tuple[bool, dict[str, float]]:
        previous = self._track_shapes.get(track_id)
        current = self._observation_shape(observation)
        if previous is None:
            return True, {
                "area_ratio": 1.0,
                "width_ratio": 1.0,
                "height_ratio": 1.0,
            }
        width_ratio = self._ratio(previous[0], current[0])
        height_ratio = self._ratio(previous[1], current[1])
        area_ratio = self._ratio(previous[2], current[2])
        compatible = bool(
            area_ratio >= self.min_area_ratio
            and width_ratio >= self.min_width_ratio
            and height_ratio >= self.min_height_ratio
        )
        return compatible, {
            "area_ratio": area_ratio,
            "width_ratio": width_ratio,
            "height_ratio": height_ratio,
        }

    def _remember_shape(
        self,
        track_id: str,
        observation: EntityObservation,
        alpha: float = 0.30,
    ) -> None:
        current = self._observation_shape(observation)
        previous = self._track_shapes.get(track_id)
        if previous is None:
            self._track_shapes[track_id] = current
            return
        self._track_shapes[track_id] = tuple(
            (1.0 - alpha) * old + alpha * new
            for old, new in zip(previous, current)
        )

    def update(
        self,
        observations: list[EntityObservation],
        frame_index: int,
        timestamp: str | None = None,
        player_world: tuple[int, int] | None = None,
    ) -> tuple[list[dict], list[EntityTrack]]:
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        available = set(self.tracks)
        events: list[dict] = []
        scoped: list[EntityObservation] = []

        for observation in observations:
            if self.interest_radius_cells is not None:
                distance = observation.distance_to_player
                if distance is None and player_world is not None:
                    anchor = observation.region.anchor_world_cell
                    if anchor is not None:
                        distance = self._distance(anchor, player_world)
                        observation.distance_to_player = distance
                if distance is None or distance > self.interest_radius_cells:
                    events.append(
                        {
                            "event": "track_skipped_outside_radius",
                            "distance": distance,
                            "anchor_world_cell": observation.region.anchor_world_cell,
                            "candidate_sources": observation.candidate_sources,
                        }
                    )
                    continue
            scoped.append(observation)

        for observation in scoped:
            best_id: str | None = None
            best_score = -1.0
            shape_rejections: list[dict] = []
            for track_id in list(available):
                track = self.tracks[track_id]
                distance = self._distance(
                    track.current_world_cell,
                    observation.region.anchor_world_cell,
                )
                if distance > self.max_cell_distance:
                    continue

                shape_ok, shape_metrics = self._shape_compatible(
                    track_id,
                    observation,
                )
                if not shape_ok:
                    shape_rejections.append(
                        {
                            "event": "track_match_rejected_shape",
                            "track_id": track_id,
                            "frame": frame_index,
                            "anchor_world_cell": observation.region.anchor_world_cell,
                            **shape_metrics,
                        }
                    )
                    continue

                visual = EntityFeatureExtractor.similarity(
                    track.feature,
                    observation.feature,
                )
                same_category = (
                    track.classification.category
                    == observation.classification.category
                )
                required = self.min_similarity - (0.12 if same_category else 0.0)
                if visual < required:
                    continue
                proximity = max(
                    0.0,
                    1.0 - distance / max(1, self.max_cell_distance + 1),
                )
                shape_score = (
                    shape_metrics["area_ratio"]
                    + shape_metrics["width_ratio"]
                    + shape_metrics["height_ratio"]
                ) / 3.0
                score = (
                    0.58 * visual
                    + 0.18 * proximity
                    + 0.10 * float(same_category)
                    + 0.14 * shape_score
                )
                if score > best_score:
                    best_score = score
                    best_id = track_id

            events.extend(shape_rejections)

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
                    candidate_sources=list(observation.candidate_sources),
                )
                self.tracks[track_id] = track
                self._remember_shape(track_id, observation, alpha=1.0)
                events.append(
                    {
                        "event": "entity_created",
                        "track_id": track_id,
                        "candidate_sources": observation.candidate_sources,
                    }
                )
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
                track.out_of_scope = False
                track.candidate_sources = sorted(
                    set(track.candidate_sources + observation.candidate_sources)
                )
                if len(track.feature) == len(observation.feature):
                    track.feature = [
                        0.7 * old + 0.3 * new
                        for old, new in zip(track.feature, observation.feature)
                    ]
                else:
                    track.feature = list(observation.feature)
                self._remember_shape(best_id, observation)
                if (
                    observation.classification.confidence
                    > track.classification.confidence
                ):
                    track.classification = observation.classification
                moved = (
                    previous is not None
                    and track.current_world_cell is not None
                    and previous != track.current_world_cell
                )
                if moved:
                    track.movement_count += 1
                    track.stationary_frame_count = 0
                    observation.movement_state = "moving"
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
                    observation.movement_state = "stationary"
                track.position_history.append(track.current_world_cell)
                track.position_history = track.position_history[-64:]

            observation.track_id = track.track_id
            observation.previous_world_cell = track.previous_world_cell
            observation.movement_detected = (
                track.previous_world_cell is not None
                and track.current_world_cell != track.previous_world_cell
            )
            if observation.movement_state == "unknown":
                observation.movement_state = (
                    "moving" if observation.movement_detected else "stationary"
                )

        expired: list[EntityTrack] = []
        for track_id, track in list(self.tracks.items()):
            outside = False
            if self.interest_radius_cells is not None and player_world is not None:
                outside = (
                    self._distance(track.current_world_cell, player_world)
                    > self.interest_radius_cells
                )
            if outside:
                track.out_of_scope = True
                expired.append(track)
                del self.tracks[track_id]
                self._track_shapes.pop(track_id, None)
                events.append(
                    {"event": "entity_out_of_scope", "track_id": track_id}
                )
            elif frame_index - track.last_seen_frame > self.ttl_frames:
                expired.append(track)
                del self.tracks[track_id]
                self._track_shapes.pop(track_id, None)
                events.append(
                    {"event": "entity_expired", "track_id": track_id}
                )
        return events, expired
