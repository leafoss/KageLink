from __future__ import annotations

import math

from .entity_observer import Candidate, ObserverConfig
from .entity_tracker_v03 import _blend_signature, appearance_similarity
from .water_filter_v03 import OccupancyDynamicBackground, _OccupancyCell, _distance
from .water_filter_v03b import CombatSelectiveWaterAwareEntityTracker


class TemporalRecurrenceDynamicBackground(OccupancyDynamicBackground):
    """Learn animated scenery from repeated regional occupancy over time.

    Real BYOND validation showed that animated water contours are often spread across
    a wide band instead of forming three close neighbors in every frame. The previous
    learner therefore never accumulated a single mature cell even after thousands of
    frames.

    This revision learns a cell when motion keeps returning to that region. A busy
    frame is useful supporting evidence, but local same-frame clustering is no longer
    required. Character-shaped candidates remain harder to suppress than scenery-like
    contours, and combat-like tracks are still protected by the owning tracker.
    """

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

        player_guard = float(getattr(self.config, "background_player_guard", 78.0))
        min_frame_candidates = int(getattr(self.config, "background_min_neighbors", 3))
        similarity_threshold = float(getattr(self.config, "background_similarity", 0.88))

        remote_indices = [
            index
            for index, candidate in enumerate(candidates)
            if _distance(candidate.center, player_center) >= player_guard
        ]
        busy_frame = len(remote_indices) >= min_frame_candidates

        # One hit per occupied cell per frame. Unlike the previous implementation,
        # local neighbor density is not required. Wide animated bands such as water
        # therefore accumulate evidence even when contour centers are far apart.
        frame_cells: dict[tuple[int, int], list[tuple[float, ...]]] = {}
        for index in remote_indices:
            candidate = candidates[index]
            signature = signatures[index]
            scenery_like = not self._looks_vertical_character(candidate)
            if not busy_frame and not scenery_like:
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
                cell.hits *= math.exp(-elapsed / 8.0)
                cell.hits += 1.0
                cell.last_seen = now
                if sample:
                    cell.appearance = _blend_signature(cell.appearance, sample, alpha=0.06)

        stale_after = float(getattr(self.config, "background_memory_ttl", 12.0))
        for key in list(self.cells):
            if now - self.cells[key].last_seen > stale_after:
                del self.cells[key]

        filtered_candidates: list[Candidate] = []
        filtered_signatures: list[tuple[float, ...]] = []
        suppressed = 0

        for candidate, signature in zip(candidates, signatures):
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

            # Scenery-like contours are suppressed primarily by repeated occupancy;
            # exact appearance is intentionally not required because water animation
            # changes shape between frames.
            scenery_background = (not looks_character) and mature_coverage >= 0.30

            # Character-shaped contours require much stronger regional evidence plus
            # some appearance agreement. This protects real enemies crossing water.
            character_background = (
                looks_character
                and strong_coverage >= 0.55
                and best_similarity >= max(0.52, similarity_threshold - 0.28)
            )

            # A very strongly occupied region may still suppress arbitrary contour
            # fragments on globally busy frames, but protected combat tracks bypass
            # this rule above.
            saturated_background = busy_frame and strong_coverage >= 0.70

            if scenery_background or character_background or saturated_background:
                suppressed += 1
                continue

            filtered_candidates.append(candidate)
            filtered_signatures.append(signature)

        self.suppressed_last_frame = suppressed
        return filtered_candidates, filtered_signatures


class TemporalRecurrenceWaterAwareEntityTracker(CombatSelectiveWaterAwareEntityTracker):
    """Combat-selective tracker using the temporal-recurrence water learner."""

    def __init__(self, config: ObserverConfig) -> None:
        super().__init__(config)
        self.background = TemporalRecurrenceDynamicBackground(config)
