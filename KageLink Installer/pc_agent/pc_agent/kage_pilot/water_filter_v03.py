from __future__ import annotations

import math
from dataclasses import dataclass

from .entity_observer import Candidate, FlowEstimate, ObserverConfig
from .entity_tracker_v03 import (
    MeleeAwareEntityTracker,
    _blend_signature,
    appearance_similarity,
)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass(slots=True)
class _OccupancyCell:
    first_seen: float
    last_seen: float
    hits: float = 0.0
    appearance: tuple[float, ...] = ()


class OccupancyDynamicBackground:
    """Temporal occupancy memory for animated scenery such as water.

    The first v0.3 background filter depended heavily on the exact visual
    signature of each moving contour. Animated water changes shape too much for
    that assumption. This version learns *where dense motion keeps returning*
    and uses appearance only as supporting evidence.

    Established combat tracks near/approaching the player can be protected by
    the owning tracker so an enemy crossing an animated region is not erased.
    """

    def __init__(self, config: ObserverConfig) -> None:
        self.config = config
        self.cells: dict[tuple[int, int], _OccupancyCell] = {}
        self.suppressed_last_frame = 0
        self.protected_centers: tuple[tuple[float, float], ...] = ()

    def reset(self) -> None:
        self.cells.clear()
        self.suppressed_last_frame = 0
        self.protected_centers = ()

    def _cell_size(self) -> float:
        return max(12.0, float(getattr(self.config, "background_cell_size", 32.0)))

    def _keys_for_bbox(self, bbox: tuple[int, int, int, int]) -> tuple[tuple[int, int], ...]:
        x, y, w, h = bbox
        size = self._cell_size()
        x0 = int(max(0.0, float(x)) // size)
        y0 = int(max(0.0, float(y)) // size)
        x1 = int(max(0.0, float(x + max(1, w - 1))) // size)
        y1 = int(max(0.0, float(y + max(1, h - 1))) // size)
        keys: list[tuple[int, int]] = []
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                keys.append((cx, cy))
        return tuple(keys[:48])

    def _mature(self, cell: _OccupancyCell) -> bool:
        min_hits = float(getattr(self.config, "background_min_dense_hits", 8.0))
        min_age = float(getattr(self.config, "background_min_age", 0.8))
        return cell.hits >= min_hits and cell.last_seen - cell.first_seen >= min_age

    def _strong(self, cell: _OccupancyCell) -> bool:
        min_hits = float(getattr(self.config, "background_min_dense_hits", 8.0))
        min_age = float(getattr(self.config, "background_min_age", 0.8))
        return cell.hits >= min_hits * 1.75 and cell.last_seen - cell.first_seen >= min_age * 1.5

    @property
    def mature_cells(self) -> int:
        return sum(1 for cell in self.cells.values() if self._mature(cell))

    @property
    def strong_cells(self) -> int:
        return sum(1 for cell in self.cells.values() if self._strong(cell))

    def _candidate_cells(self, candidate: Candidate) -> list[_OccupancyCell]:
        return [self.cells[key] for key in self._keys_for_bbox(candidate.bbox) if key in self.cells]

    def region_strength_bbox(self, bbox: tuple[int, int, int, int]) -> float:
        keys = self._keys_for_bbox(bbox)
        if not keys:
            return 0.0
        min_hits = max(1.0, float(getattr(self.config, "background_min_dense_hits", 8.0)))
        strengths = []
        for key in keys:
            cell = self.cells.get(key)
            if cell is None:
                strengths.append(0.0)
                continue
            strengths.append(min(1.0, cell.hits / (min_hits * 1.75)))
        return sum(strengths) / max(1, len(strengths))

    def _protected(self, center: tuple[float, float]) -> bool:
        radius = max(42.0, self._cell_size() * 1.6)
        return any(_distance(center, point) <= radius for point in self.protected_centers)

    @staticmethod
    def _looks_vertical_character(candidate: Candidate) -> bool:
        _, _, w, h = candidate.bbox
        aspect = float(h) / max(1.0, float(w))
        return 1.25 <= aspect <= 4.2 and h >= 18 and w <= 55

    def observe_and_filter(
        self,
        candidates: list[Candidate],
        signatures: list[tuple[float, ...]],
        *,
        player_center: tuple[float, float],
        now: float,
    ) -> tuple[list[Candidate], list[tuple[float, ...]]]:
        if not bool(getattr(self.config, "dynamic_background_enabled", True)):
            self.suppressed_last_frame = 0
            return candidates, signatures

        neighbor_radius = float(getattr(self.config, "background_neighbor_radius", 58.0))
        min_neighbors = int(getattr(self.config, "background_min_neighbors", 3))
        player_guard = float(getattr(self.config, "background_player_guard", 78.0))
        similarity_threshold = float(getattr(self.config, "background_similarity", 0.88))

        neighbor_counts: list[int] = []
        for index, candidate in enumerate(candidates):
            count = 0
            for other_index, other in enumerate(candidates):
                if index != other_index and _distance(candidate.center, other.center) <= neighbor_radius:
                    count += 1
            neighbor_counts.append(count)

        # One temporal hit per cell per frame. This prevents a single noisy frame
        # from instantly becoming background while allowing a wide animated band
        # (water) to mature even when individual contour centers jump around.
        frame_cells: dict[tuple[int, int], list[tuple[float, ...]]] = {}
        for candidate, signature, neighbors in zip(candidates, signatures, neighbor_counts):
            if neighbors < min_neighbors:
                continue
            if _distance(candidate.center, player_center) < player_guard:
                continue
            for key in self._keys_for_bbox(candidate.bbox):
                frame_cells.setdefault(key, []).append(signature)

        for key, cell_signatures in frame_cells.items():
            sample = next((sig for sig in cell_signatures if sig), ())
            cell = self.cells.get(key)
            if cell is None:
                self.cells[key] = _OccupancyCell(
                    first_seen=now,
                    last_seen=now,
                    hits=1.0,
                    appearance=sample,
                )
            else:
                elapsed = max(0.0, now - cell.last_seen)
                cell.hits *= math.exp(-elapsed / 6.0)
                cell.hits += 1.0
                cell.last_seen = now
                if sample:
                    cell.appearance = _blend_signature(cell.appearance, sample, alpha=0.08)

        stale_after = float(getattr(self.config, "background_memory_ttl", 12.0))
        for key in list(self.cells):
            if now - self.cells[key].last_seen > stale_after:
                del self.cells[key]

        filtered_candidates: list[Candidate] = []
        filtered_signatures: list[tuple[float, ...]] = []
        suppressed = 0

        for candidate, signature, neighbors in zip(candidates, signatures, neighbor_counts):
            if _distance(candidate.center, player_center) < player_guard or self._protected(candidate.center):
                filtered_candidates.append(candidate)
                filtered_signatures.append(signature)
                continue

            cells = self._candidate_cells(candidate)
            if not cells:
                filtered_candidates.append(candidate)
                filtered_signatures.append(signature)
                continue

            mature = [cell for cell in cells if self._mature(cell)]
            strong = [cell for cell in cells if self._strong(cell)]
            mature_coverage = len(mature) / max(1, len(cells))
            strong_coverage = len(strong) / max(1, len(cells))
            best_similarity = max(
                (appearance_similarity(cell.appearance, signature) for cell in mature),
                default=0.0,
            )

            looks_character = self._looks_vertical_character(candidate)
            dense = neighbors >= min_neighbors

            # Soft rule: mature region + reasonably similar appearance.
            soft_similarity = max(0.58, similarity_threshold - 0.18)
            soft_background = mature_coverage >= 0.40 and best_similarity >= soft_similarity

            # Strong occupancy rule: highly persistent dense motion can be ignored
            # even if the animation changes appearance. Vertical character-shaped
            # candidates need extra visual support unless they are already protected.
            strong_background = (
                strong_coverage >= 0.45
                and dense
                and (not looks_character or best_similarity >= 0.68)
            )

            if soft_background or strong_background:
                suppressed += 1
                continue

            filtered_candidates.append(candidate)
            filtered_signatures.append(signature)

        self.suppressed_last_frame = suppressed
        return filtered_candidates, filtered_signatures


def _path_efficiency(history) -> float:
    points = list(history)[-14:]
    if len(points) < 3:
        return 1.0
    path = sum(_distance(first, second) for first, second in zip(points, points[1:]))
    if path < 1.0:
        return 0.0
    return _distance(points[0], points[-1]) / path


class WaterAwareEntityTracker(MeleeAwareEntityTracker):
    """Melee-aware tracker with aggressive animated-background cleanup."""

    def __init__(self, config: ObserverConfig) -> None:
        super().__init__(config)
        self.background = OccupancyDynamicBackground(config)
        self.background_pruned_last_frame = 0

    def reset_tracking(self, *, preserve_background: bool = False) -> None:
        self._tracks.clear()
        self._next_id = 1
        self._contexts.clear()
        self._dormant.clear()
        self._frame_gray = None
        self.background_pruned_last_frame = 0
        if not preserve_background:
            self.background.reset()

    def reset(self) -> None:
        self.reset_tracking(preserve_background=False)

    def _update_protected_centers(self, player_center: tuple[float, float]) -> None:
        guard = float(getattr(self.config, "background_player_guard", 78.0))
        protected: list[tuple[float, float]] = []
        for track_id, track in self._tracks.items():
            context = self._contexts.get(track_id)
            close_to_player = _distance(track.center, player_center) <= guard + 55.0
            behavioral = track.approaching_player or track.hostility_memory >= 0.10
            contact = context is not None and context.state == "OCCLUDED"
            if close_to_player or behavioral or contact:
                protected.append(track.center)
        self.background.protected_centers = tuple(protected)

    def _prune_background_tracks(self, player_center: tuple[float, float]) -> None:
        guard = float(getattr(self.config, "background_player_guard", 78.0))
        pruned = 0
        for track_id in list(self._tracks):
            track = self._tracks[track_id]
            context = self._contexts.get(track_id)
            if _distance(track.center, player_center) <= guard + 30.0:
                continue
            if context is not None and context.state == "OCCLUDED":
                continue
            if track.approaching_player or track.hostility_memory >= 0.10:
                continue

            region_strength = self.background.region_strength_bbox(track.bbox)
            if region_strength < 0.62:
                continue

            coherence = _path_efficiency(track.history)
            background_like_motion = coherence < 0.52 or track.residual_speed < 11.0
            if not background_like_motion:
                continue

            if context is not None:
                context.state = "BACKGROUND_DYNAMIC"
            del self._tracks[track_id]
            self._contexts.pop(track_id, None)
            self._dormant.pop(track_id, None)
            pruned += 1

        self.background_pruned_last_frame = pruned

    def update(
        self,
        candidates,
        *,
        flow: FlowEstimate,
        player_center: tuple[float, float],
        now: float,
    ):
        self._update_protected_centers(player_center)
        super().update(candidates, flow=flow, player_center=player_center, now=now)
        self._prune_background_tracks(player_center)
        return self.tracks
