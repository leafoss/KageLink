from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from dataclasses import replace
import math

import cv2
import numpy as np

from .entity_observer import EntityTrack, ObserverState
from .guarded_observer_v03 import TargetEligibleObserver


@dataclass(frozen=True, slots=True)
class GridTrackMetrics:
    cell: tuple[int, int]
    player_cell: tuple[int, int]
    grid_distance: int
    unique_cells: int
    toward_steps: int
    away_steps: int
    net_closer: int
    approach_ratio: float
    background_strength: float

    @property
    def coherent_approach(self) -> bool:
        transitions = self.toward_steps + self.away_steps
        return (
            self.unique_cells >= 3
            and self.toward_steps >= 2
            and self.net_closer >= 1
            and transitions >= 2
            and self.approach_ratio >= 0.67
        )


def _cell_for(point: tuple[float, float], tile_size: float) -> tuple[int, int]:
    size = max(8.0, float(tile_size))
    return int(max(0.0, point[0]) // size), int(max(0.0, point[1]) // size)


def _grid_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    # Chebyshev distance matches an 8-neighbour tile grid: diagonal adjacency counts
    # as one cell of separation.
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _compress_cells(points, tile_size: float) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for point in points:
        cell = _cell_for(point, tile_size)
        if not cells or cells[-1] != cell:
            cells.append(cell)
    return cells


class GridTargetObserver(TargetEligibleObserver):
    """Hybrid contour + Lucas-Kanade + fixed-grid target observer.

    The contour tracker remains authoritative for identity and appearance. The grid is
    an additional behavioural signal: a distant target should move through successive
    map cells toward PLAYER instead of merely producing strong local animation.

    Contact is special. Once a validated target reaches PLAYER/OCCLUDED range, a short
    CONTACT MEMORY latch keeps the logical target alive through contour collapse or an
    ID swap. This exception is local to the player and therefore cannot rescue water
    or other distant animated scenery.
    """

    def __init__(
        self,
        config,
        *,
        tile_size: float = 32.0,
        contact_lock_seconds: float = 2.8,
        show_grid: bool = True,
    ) -> None:
        super().__init__(config)
        self.tile_size = max(16.0, min(64.0, float(tile_size)))
        self.contact_lock_seconds = max(0.5, min(8.0, float(contact_lock_seconds)))
        self.show_grid = bool(show_grid)
        self._grid_target_id: int | None = None
        self._contact_latch_until = 0.0
        self._contact_side = "-"
        self._last_metrics: dict[int, GridTrackMetrics] = {}
        self._active_cells: set[tuple[int, int]] = set()
        self._target_mode = "NONE"

    def reset(self) -> None:
        super().reset()
        self._grid_target_id = None
        self._contact_latch_until = 0.0
        self._contact_side = "-"
        self._last_metrics.clear()
        self._active_cells.clear()
        self._target_mode = "NONE"

    @property
    def active_grid_cells(self) -> int:
        return len(self._active_cells)

    @property
    def target_mode(self) -> str:
        return self._target_mode

    def metrics_for(self, track_id: int) -> GridTrackMetrics | None:
        return self._last_metrics.get(track_id)

    def _active_cells_from_mask(self, mask: np.ndarray | None) -> set[tuple[int, int]]:
        if mask is None or mask.size == 0:
            return set()
        height, width = mask.shape[:2]
        size = max(1, round(self.tile_size))
        active: set[tuple[int, int]] = set()
        for y in range(0, height, size):
            for x in range(0, width, size):
                patch = mask[y:min(height, y + size), x:min(width, x + size)]
                if patch.size == 0:
                    continue
                ratio = float(np.count_nonzero(patch)) / float(patch.size)
                if ratio >= 0.055:
                    active.add((x // size, y // size))
        return active

    def _metrics(self, track: EntityTrack, state: ObserverState) -> GridTrackMetrics:
        player_cell = _cell_for(state.player_center, self.tile_size)
        cells = _compress_cells(track.history, self.tile_size)
        if not cells:
            cells = [_cell_for(track.center, self.tile_size)]
        current_cell = _cell_for(track.center, self.tile_size)
        if cells[-1] != current_cell:
            cells.append(current_cell)
        cells = cells[-10:]

        distances = [_grid_distance(cell, player_cell) for cell in cells]
        toward = 0
        away = 0
        for previous, current in zip(distances, distances[1:]):
            if current < previous:
                toward += 1
            elif current > previous:
                away += 1
        transitions = toward + away
        approach_ratio = float(toward) / float(max(1, transitions))
        net_closer = distances[0] - distances[-1] if distances else 0

        tracker = self.tracker
        strength = 0.0
        background = getattr(tracker, "background", None)
        if background is not None and hasattr(background, "region_strength_bbox"):
            strength = float(background.region_strength_bbox(track.bbox))

        return GridTrackMetrics(
            cell=current_cell,
            player_cell=player_cell,
            grid_distance=_grid_distance(current_cell, player_cell),
            unique_cells=len(set(cells)),
            toward_steps=toward,
            away_steps=away,
            net_closer=net_closer,
            approach_ratio=approach_ratio,
            background_strength=strength,
        )

    def _same_contact_side(self, side: str) -> bool:
        return self._contact_side == "-" or side == "-" or side == self._contact_side

    def _grid_eligible(self, track: EntityTrack, state: ObserverState, *, for_keep: bool) -> bool:
        tracker = self.tracker
        context = tracker.context_for(track.track_id)
        metrics = self._last_metrics[track.track_id]

        if context.state == "OCCLUDED":
            return True
        if context.state != "VISIBLE":
            return False

        target_eligible = getattr(tracker, "target_eligible", None)
        if callable(target_eligible) and not target_eligible(
            track.track_id,
            player_center=state.player_center,
            now=state.timestamp,
            for_keep=for_keep,
        ):
            return False

        # Strong animated-background evidence is a hard block away from actual contact.
        # A real opponent crossing such a region can still qualify by traversing several
        # grid cells coherently toward PLAYER.
        if metrics.background_strength >= 0.34 and metrics.grid_distance > 1:
            if not metrics.coherent_approach:
                return False

        # Immediate neighbour/contact cells are allowed after the tracker persistence
        # gate. This is the only geometry-only path to TARGET.
        if metrics.grid_distance <= 1:
            return True

        # Two cells away still needs at least one real approach indication and a
        # character-like tracked shape. This protects against animated water fragments.
        if metrics.grid_distance == 2:
            return (
                track.observations >= 5
                and track.shape_score >= 0.38
                and (metrics.toward_steps >= 1 or track.approaching_player)
            )

        # Beyond melee neighbourhood, cell-to-cell approach is mandatory.
        return metrics.coherent_approach

    def _latch_contact(self, track: EntityTrack, state: ObserverState) -> None:
        context = self.tracker.context_for(track.track_id)
        metrics = self._last_metrics[track.track_id]
        if context.state == "OCCLUDED" or metrics.grid_distance <= 1:
            self._contact_latch_until = max(
                self._contact_latch_until,
                state.timestamp + self.contact_lock_seconds,
            )
            if context.last_visible_side != "-":
                self._contact_side = context.last_visible_side
            elif context.relative_side != "-":
                self._contact_side = context.relative_side

    def _contact_rebind(self, state: ObserverState) -> int | None:
        if state.timestamp > self._contact_latch_until:
            return None
        candidates: list[EntityTrack] = []
        for track in state.tracks:
            context = self.tracker.context_for(track.track_id)
            metrics = self._last_metrics[track.track_id]
            if context.state not in {"VISIBLE", "OCCLUDED"}:
                continue
            if metrics.grid_distance > 1:
                continue
            side = context.last_visible_side if context.last_visible_side != "-" else context.relative_side
            if not self._same_contact_side(side):
                continue
            candidates.append(track)
        return max(candidates, key=lambda item: item.enemy_score, default=None).track_id if candidates else None

    def _select_grid_target(self, state: ObserverState) -> int | None:
        current_id = self._grid_target_id
        current = next((track for track in state.tracks if track.track_id == current_id), None)

        if current is not None:
            context = self.tracker.context_for(current.track_id)
            self._latch_contact(current, state)
            if context.state == "LOST" and state.timestamp <= self._contact_latch_until:
                self._target_mode = "CONTACT_MEMORY"
                return current.track_id
            if self._grid_eligible(current, state, for_keep=True):
                self._target_mode = context.state
                return current.track_id

        rebound_id = self._contact_rebind(state)
        if rebound_id is not None:
            rebound = next(track for track in state.tracks if track.track_id == rebound_id)
            self._latch_contact(rebound, state)
            self._target_mode = "CONTACT_REBIND"
            return rebound_id

        eligible: list[EntityTrack] = []
        for track in state.tracks:
            if not self._grid_eligible(track, state, for_keep=False):
                continue
            if track.enemy_score >= self.config.target_acquire_threshold:
                eligible.append(track)

        selected = max(eligible, key=lambda item: item.enemy_score, default=None)
        if selected is None:
            self._target_mode = "NONE"
            return None
        self._latch_contact(selected, state)
        context = self.tracker.context_for(selected.track_id)
        self._target_mode = context.state
        return selected.track_id

    def process(self, frame_bgr: np.ndarray, *, timestamp: float | None = None) -> ObserverState:
        state = super().process(frame_bgr, timestamp=timestamp)
        self._active_cells = self._active_cells_from_mask(state.motion_mask)
        self._last_metrics = {track.track_id: self._metrics(track, state) for track in state.tracks}

        selected_id = self._select_grid_target(state)
        self._grid_target_id = selected_id
        self._locked_target_id = selected_id
        if state.target_id == selected_id:
            return state
        return replace(state, target_id=selected_id)

    def draw_grid_overlay(self, preview: np.ndarray, state: ObserverState) -> np.ndarray:
        if not self.show_grid:
            return preview
        x0, y0, x1, y1 = state.arena_rect
        size = max(1, round(self.tile_size))

        # Subtle fixed map-cell grid.
        for x in range(x0, x1 + 1, size):
            cv2.line(preview, (x, y0), (x, y1), (65, 65, 65), 1)
        for y in range(y0, y1 + 1, size):
            cv2.line(preview, (x0, y), (x1, y), (65, 65, 65), 1)

        # Motion-active cells are outlined, not filled, so sprites stay readable.
        for cell_x, cell_y in self._active_cells:
            left = x0 + cell_x * size
            top = y0 + cell_y * size
            cv2.rectangle(
                preview,
                (left, top),
                (min(x1, left + size), min(y1, top + size)),
                (90, 90, 90),
                1,
            )

        player_cell = _cell_for(state.player_center, self.tile_size)
        px = x0 + player_cell[0] * size
        py = y0 + player_cell[1] * size
        cv2.rectangle(preview, (px, py), (px + size, py + size), (255, 255, 255), 1)

        if state.target_id is not None:
            metrics = self._last_metrics.get(state.target_id)
            if metrics is not None:
                tx = x0 + metrics.cell[0] * size
                ty = y0 + metrics.cell[1] * size
                cv2.rectangle(preview, (tx, ty), (tx + size, ty + size), (0, 220, 255), 2)
        return preview
