from __future__ import annotations

from dataclasses import replace

import numpy as np

from .grid_geometry_v351 import GridGeometry, emit_grid_geometry
from .guarded_observer_v03 import TargetEligibleObserver
from .grid_target_observer_v03 import _grid_distance
from .grid_target_observer_v03c import FrameAlignedGridTargetObserver


class TileCalibratedGridTargetObserver(FrameAlignedGridTargetObserver):
    """Logical-grid hybrid observer with confirmed local contact memory.

    Sprite artwork may span multiple cells; the grid represents navigation geometry.
    The tile lattice and distance metrics are anchored to character feet, never the
    centre or dimensions of a Trainer template.

    CONTACT MEMORY is intentionally local to PLAYER. A noisy adjacent contour must be
    observed in the same side/cell for multiple frames before it may open the contact
    latch. Once visual evidence is lost, that memory may preserve identity/facing only
    while the predicted target remains in the contact neighbourhood (d <= 1). It can
    never become a distant pursuit target by itself.
    """

    def __init__(
        self,
        config,
        *,
        tile_size: float = 32.0,
        contact_lock_seconds: float = 2.8,
        show_grid: bool = True,
        auto_align_grid: bool = True,
        grid_origin_x: float | None = None,
        grid_origin_y: float | None = None,
        contact_confirm_frames: int = 2,
    ) -> None:
        # Absolute physical invariant: the game grid has only 32px and 64px RAW
        # cells. PNG crops, sprite bboxes, display scaling and debug panels never
        # define navigation geometry. Validation intentionally happens before the
        # historical observer allocates state so invalid geometry cannot start combat.
        geometry = GridGeometry.from_cell_size(tile_size)
        super().__init__(
            config,
            tile_size=float(geometry.cell_size),
            contact_lock_seconds=contact_lock_seconds,
            show_grid=show_grid,
        )
        self.grid_geometry = geometry
        emit_grid_geometry(geometry)

        self.auto_align_grid = bool(auto_align_grid)
        self._grid_alignment_ready = grid_origin_x is not None and grid_origin_y is not None
        if grid_origin_x is not None:
            self.grid_origin_x = float(grid_origin_x) % self.tile_size
        if grid_origin_y is not None:
            self.grid_origin_y = float(grid_origin_y) % self.tile_size

        self.contact_confirm_frames = max(2, min(6, int(contact_confirm_frames)))
        self._contact_evidence: dict[tuple[str, tuple[int, int]], tuple[int, float]] = {}
        self._contact_confirmed_keys: set[tuple[str, tuple[int, int]]] = set()

    @property
    def grid_origin(self) -> tuple[float, float]:
        return float(self.grid_origin_x), float(self.grid_origin_y)

    def request_grid_realign(self) -> None:
        if self.auto_align_grid:
            self._grid_alignment_ready = False

    def reset(self) -> None:
        super().reset()
        self._contact_evidence.clear()
        self._contact_confirmed_keys.clear()

    def _align_grid_to_player(self, state) -> None:
        if self._grid_alignment_ready or not self.auto_align_grid:
            return
        x0, y0, _, _ = state.arena_rect
        player_x, player_y = self._player_anchor(state)
        full_player_x = float(x0) + float(player_x)
        full_player_y = float(y0) + float(player_y)
        half = self.tile_size / 2.0
        self.grid_origin_x = (full_player_x - half) % self.tile_size
        self.grid_origin_y = (full_player_y - half) % self.tile_size
        self._grid_alignment_ready = True

    def _character_like(self, track) -> bool:
        _, _, width, height = track.bbox
        width = max(1.0, float(width))
        height = max(1.0, float(height))
        aspect = height / width
        return (
            height >= 14.0
            and width <= self.tile_size * 1.25
            and 0.55 <= aspect <= 4.5
            and track.shape_score >= 0.22
        )

    def _contact_key(self, track) -> tuple[str, tuple[int, int]]:
        context = self.tracker.context_for(track.track_id)
        metrics = self._last_metrics[track.track_id]
        side = context.last_visible_side if context.last_visible_side != "-" else context.relative_side
        return side, metrics.cell

    def _update_contact_evidence(self, state) -> None:
        now = float(state.timestamp)
        seen: set[tuple[str, tuple[int, int]]] = set()
        for track in state.tracks:
            metrics = self._last_metrics.get(track.track_id)
            if metrics is None or metrics.grid_distance > 1:
                continue
            context = self.tracker.context_for(track.track_id)
            if context.state not in {"VISIBLE", "OCCLUDED"}:
                continue
            if not self._character_like(track):
                continue
            key = self._contact_key(track)
            seen.add(key)
            hits, previous_time = self._contact_evidence.get(key, (0, now))
            if now - previous_time > 0.55:
                hits = 0
            hits += 1
            self._contact_evidence[key] = (hits, now)
            if hits >= self.contact_confirm_frames:
                self._contact_confirmed_keys.add(key)

        stale = [
            key
            for key, (_, last_seen) in self._contact_evidence.items()
            if now - last_seen > 0.75 and key not in seen
        ]
        for key in stale:
            self._contact_evidence.pop(key, None)
            self._contact_confirmed_keys.discard(key)

    def _contact_confirmed(self, track) -> bool:
        return self._contact_key(track) in self._contact_confirmed_keys

    def _grid_eligible(self, track, state, *, for_keep: bool) -> bool:
        context = self.tracker.context_for(track.track_id)
        metrics = self._last_metrics[track.track_id]

        if metrics.grid_distance <= 1:
            if for_keep and self._grid_target_id == track.track_id:
                return context.state in {"VISIBLE", "OCCLUDED"}
            if context.state not in {"VISIBLE", "OCCLUDED"}:
                return False
            return self._contact_confirmed(track)

        return super()._grid_eligible(track, state, for_keep=for_keep)

    def _latch_contact(self, track, state) -> None:
        if self._grid_target_id == track.track_id or self._contact_confirmed(track):
            super()._latch_contact(track, state)

    def _contact_rebind(self, state) -> int | None:
        if state.timestamp > self._contact_latch_until:
            return None
        candidates = []
        for track in state.tracks:
            context = self.tracker.context_for(track.track_id)
            metrics = self._last_metrics[track.track_id]
            if context.state not in {"VISIBLE", "OCCLUDED"}:
                continue
            if metrics.grid_distance > 1 or not self._character_like(track):
                continue
            side = context.last_visible_side if context.last_visible_side != "-" else context.relative_side
            if not self._same_contact_side(side):
                continue
            candidates.append(track)
        selected = max(candidates, key=lambda item: item.enemy_score, default=None)
        return selected.track_id if selected is not None else None

    def _select_grid_target(self, state) -> int | None:
        """Select TARGET with a strict local-only CONTACT_MEMORY rule."""
        current_id = self._grid_target_id
        current = next((track for track in state.tracks if track.track_id == current_id), None)

        if current is not None:
            context = self.tracker.context_for(current.track_id)
            self._latch_contact(current, state)
            metrics = self._last_metrics[current.track_id]

            # Critical safety invariant: CONTACT_MEMORY exists only in the local melee
            # neighbourhood. If a LOST prediction drifts two or more cells away, do not
            # preserve it as TARGET and never let it become a pursuit command.
            if (
                context.state == "LOST"
                and state.timestamp <= self._contact_latch_until
                and metrics.grid_distance <= 1
            ):
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

        eligible = []
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

    def process(self, frame_bgr: np.ndarray, *, timestamp: float | None = None):
        state = TargetEligibleObserver.process(self, frame_bgr, timestamp=timestamp)
        self._align_grid_to_player(state)
        self._active_cells = self._aligned_active_cells(state)
        self._last_metrics = {track.track_id: self._metrics(track, state) for track in state.tracks}
        self._update_contact_evidence(state)

        selected_id = self._select_grid_target(state)
        self._grid_target_id = selected_id
        self._locked_target_id = selected_id
        if state.target_id == selected_id:
            return state
        return replace(state, target_id=selected_id)
