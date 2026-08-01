from __future__ import annotations

from dataclasses import dataclass

from .domain import (
    HARD_LOST_SECONDS,
    H_COOLDOWN_SECONDS,
    H_PULSE_MS,
    MAX_H_RANGE_CELLS,
    MOVEMENT_REPEAT_INTERVAL_SECONDS,
    POST_PULSE_OBSERVE_MS,
    R_KEYDOWN_HEARTBEAT_MS,
    SHORT_OCCLUSION_SECONDS,
    CandidateObservation,
    CombatDecision,
    CombatFrame,
    GridCell,
    MovementPulseProfile,
    ObservationKind,
    TargetState,
    cardinal_face,
    cardinal_move,
)


@dataclass(slots=True)
class _AttentionHypothesis:
    cell: GridCell
    hits: int
    last_frame: int


class GridFocusStrategy:
    """Deterministic combat policy whose identity authority is the 64px grid."""

    def __init__(
        self,
        *,
        acquire_hits: int = 2,
        short_occlusion_seconds: float = SHORT_OCCLUSION_SECONDS,
        hard_lost_seconds: float = HARD_LOST_SECONDS,
        h_cooldown_seconds: float = H_COOLDOWN_SECONDS,
    ) -> None:
        self.acquire_hits = max(2, int(acquire_hits))
        self.short_occlusion_seconds = max(0.1, float(short_occlusion_seconds))
        self.hard_lost_seconds = max(
            self.short_occlusion_seconds + 0.1,
            float(hard_lost_seconds),
        )
        self.h_cooldown_seconds = max(H_COOLDOWN_SECONDS, float(h_cooldown_seconds))
        self.reset_round()

    def reset_round(self) -> None:
        self._state = TargetState.SEARCH
        self._next_target_id = 1
        self._target_id: int | None = None
        self._confirmed_cell: GridCell | None = None
        self._predicted_cell: GridCell | None = None
        self._attention: _AttentionHypothesis | None = None
        self._last_clean_at: float | None = None
        self._last_face: str | None = None
        self._last_h_at: float | None = None
        self._last_move_at: float | None = None

    def end_combat(self) -> None:
        self._state = TargetState.ENDED
        self._target_id = None
        self._confirmed_cell = None
        self._predicted_cell = None
        self._attention = None
        self._last_clean_at = None
        self._last_face = None
        self._last_h_at = None
        self._last_move_at = None

    def _focused_cells(self) -> set[GridCell] | None:
        if self._confirmed_cell is None:
            return None

        # A clean target may move one canonical 64px cell between frames. The
        # identity focus therefore follows a bounded 3x3 neighbourhood around
        # the confirmed/predicted cells instead of freezing on the old cell.
        origins = {self._confirmed_cell}
        if self._predicted_cell is not None:
            origins.add(self._predicted_cell)
        focused: set[GridCell] = set()
        for origin in origins:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    focused.add(GridCell(origin.x + dx, origin.y + dy))
        return focused

    @staticmethod
    def _best_clean(
        candidates: tuple[CandidateObservation, ...],
        *,
        player_cell: GridCell,
        confirmed_cell: GridCell | None,
        allowed_cells: set[GridCell] | None,
    ) -> CandidateObservation | None:
        valid = [
            candidate
            for candidate in candidates
            if candidate.is_clean_body
            and (allowed_cells is None or candidate.anchor_cell in allowed_cells)
        ]
        identity_origin = confirmed_cell or player_cell
        valid.sort(
            key=lambda candidate: (
                identity_origin.chebyshev_distance(candidate.anchor_cell),
                player_cell.chebyshev_distance(candidate.anchor_cell),
                -float(candidate.confidence),
                candidate.anchor_cell.x,
                candidate.anchor_cell.y,
                candidate.track_id,
            )
        )
        return valid[0] if valid else None

    def _update_face(self, frame: CombatFrame, clean: CandidateObservation | None) -> str | None:
        """Recompute aim exclusively from the current clean visual frame.

        A previous direction is never allowed to authorize H. In D=0 the
        same-cell visual must provide a fresh face_hint. In every other cell,
        cardinal direction is recalculated from current player/target cells.
        """

        if clean is None:
            self._last_face = None
            return None
        if clean.anchor_cell == frame.player_cell:
            self._last_face = clean.face_hint
            return self._last_face
        self._last_face = cardinal_face(frame.player_cell, clean.anchor_cell, None)
        return self._last_face

    def _movement_due(self, now: float) -> bool:
        return (
            self._last_move_at is None
            or now - self._last_move_at >= MOVEMENT_REPEAT_INTERVAL_SECONDS
        )

    def _h_remaining(self, now: float) -> float:
        if self._last_h_at is None:
            return 0.0
        return max(0.0, self.h_cooldown_seconds - (now - self._last_h_at))

    def _consume_h_if_ready(self, now: float, *, allowed: bool) -> bool:
        if not allowed or self._h_remaining(now) > 0.0:
            return False
        self._last_h_at = now
        return True

    def _consume_move_if_ready(
        self,
        now: float,
        *,
        direction: str | None,
        profile: MovementPulseProfile,
    ) -> tuple[str | None, MovementPulseProfile | None]:
        if direction is None or not self._movement_due(now):
            return None, None
        self._last_move_at = now
        return direction.lower(), profile

    def _decision(
        self,
        frame: CombatFrame,
        *,
        move: str | None,
        move_pulse_profile: MovementPulseProfile | None,
        press_h: bool,
        reason: str,
    ) -> CombatDecision:
        now = frame.effective_time_seconds
        distance = (
            frame.player_cell.chebyshev_distance(self._confirmed_cell)
            if self._confirmed_cell is not None
            else None
        )
        hold_r = self._state is not TargetState.ENDED
        move_pulse_ms = (
            move_pulse_profile.duration_ms if move_pulse_profile is not None else None
        )
        sequence: list[str] = []
        if hold_r:
            sequence.append(f"R_KEYDOWN_HEARTBEAT_{R_KEYDOWN_HEARTBEAT_MS}MS")
        if press_h and self._last_face is not None:
            sequence.append(f"AIM_CURRENT_{self._last_face}_50MS")
            sequence.append(f"H_TAP_{H_PULSE_MS}MS")
        if move is not None and move_pulse_profile is not None:
            sequence.append(f"MOVE_{move.upper()}_{move_pulse_ms}MS")
        if press_h or move is not None:
            sequence.append(f"OBSERVE_{POST_PULSE_OBSERVE_MS}MS")
        return CombatDecision(
            frame_index=frame.frame_index,
            target_state=self._state,
            combat_target_id=self._target_id,
            confirmed_cell=self._confirmed_cell,
            predicted_cell=self._predicted_cell,
            grid_distance=distance,
            face=self._last_face,
            move=move,
            move_pulse_profile=move_pulse_profile,
            move_pulse_ms=move_pulse_ms,
            post_pulse_observe_ms=POST_PULSE_OBSERVE_MS,
            hold_r=hold_r,
            r_keydown_heartbeat_ms=R_KEYDOWN_HEARTBEAT_MS if hold_r else None,
            press_h=press_h,
            h_pulse_ms=H_PULSE_MS if press_h else None,
            h_cooldown_remaining_seconds=self._h_remaining(now),
            action_sequence=tuple(sequence),
            reason=reason,
        )

    def update(self, frame: CombatFrame) -> CombatDecision:
        now = frame.effective_time_seconds

        if frame.ko_confirmed or any(
            candidate.kind is ObservationKind.KO for candidate in frame.candidates
        ):
            self.end_combat()
            return self._decision(
                frame,
                move=None,
                move_pulse_profile=None,
                press_h=False,
                reason="KO confirmed; release R and disable all combat authority",
            )

        if self._state is TargetState.ENDED:
            return self._decision(
                frame,
                move=None,
                move_pulse_profile=None,
                press_h=False,
                reason="combat already ended",
            )

        allowed = self._focused_cells()
        clean = self._best_clean(
            frame.candidates,
            player_cell=frame.player_cell,
            confirmed_cell=self._confirmed_cell,
            allowed_cells=allowed,
        )

        if self._target_id is None:
            if clean is None:
                self._state = TargetState.SEARCH
                self._attention = None
                self._update_face(frame, None)
                return self._decision(
                    frame,
                    move=None,
                    move_pulse_profile=None,
                    press_h=False,
                    reason="global discovery: no clean single-cell body",
                )

            self._update_face(frame, clean)
            if self._attention is not None and self._attention.cell == clean.anchor_cell:
                self._attention.hits += 1
                self._attention.last_frame = frame.frame_index
            else:
                self._attention = _AttentionHypothesis(clean.anchor_cell, 1, frame.frame_index)

            if self._attention.hits < self.acquire_hits:
                self._state = TargetState.ATTENTION
                self._confirmed_cell = clean.anchor_cell
                self._predicted_cell = clean.anchor_cell
                return self._decision(
                    frame,
                    move=None,
                    move_pulse_profile=None,
                    press_h=False,
                    reason=f"attention hypothesis {self._attention.hits}/{self.acquire_hits}",
                )

            self._target_id = self._next_target_id
            self._next_target_id += 1
            self._confirmed_cell = clean.anchor_cell
            self._predicted_cell = clean.anchor_cell
            self._last_clean_at = now
            self._state = TargetState.LOCKED
            self._attention = None
        elif clean is not None:
            previous = self._confirmed_cell
            assert previous is not None
            if previous.chebyshev_distance(clean.anchor_cell) > 1:
                clean = None
                self._update_face(frame, None)
            else:
                self._confirmed_cell = clean.anchor_cell
                self._predicted_cell = previous.step_toward(clean.anchor_cell)
                self._last_clean_at = now
                self._state = TargetState.LOCKED
                self._update_face(frame, clean)

        if clean is None and self._target_id is not None:
            self._update_face(frame, None)
            assert self._last_clean_at is not None
            missing_seconds = now - self._last_clean_at
            if missing_seconds >= self.hard_lost_seconds:
                old_id = self._target_id
                self._target_id = None
                self._confirmed_cell = None
                self._predicted_cell = None
                self._attention = None
                self._last_clean_at = None
                self._state = TargetState.SEARCH
                return self._decision(
                    frame,
                    move=None,
                    move_pulse_profile=None,
                    press_h=False,
                    reason=f"target #{old_id} hard lost after {missing_seconds:.2f}s",
                )
            self._state = TargetState.SUSPENDED
            phase = (
                "short occlusion"
                if missing_seconds <= self.short_occlusion_seconds
                else "bounded local recovery"
            )
            return self._decision(
                frame,
                move=None,
                move_pulse_profile=None,
                press_h=False,
                reason=f"target suspended ({phase}) for {missing_seconds:.2f}s; no H or movement",
            )

        assert clean is not None
        assert self._confirmed_cell is not None
        distance = frame.player_cell.chebyshev_distance(self._confirmed_cell)
        current_face = self._last_face
        in_h_range = distance <= MAX_H_RANGE_CELLS
        press_h = self._consume_h_if_ready(
            now,
            allowed=in_h_range and current_face is not None,
        )

        if distance in {0, 1}:
            if press_h:
                return self._decision(
                    frame,
                    move=None,
                    move_pulse_profile=None,
                    press_h=True,
                    reason=(
                        f"D={distance}: clean target; mandatory current-frame {current_face} "
                        "orientation pulse, then H 50ms"
                    ),
                )
            move, pulse = self._consume_move_if_ready(
                now,
                direction=current_face,
                profile=MovementPulseProfile.VERY_SHORT,
            )
            return self._decision(
                frame,
                move=move,
                move_pulse_profile=pulse,
                press_h=False,
                reason=(
                    f"D={distance}: H cooldown {self._h_remaining(now):.2f}s; "
                    "VERY_SHORT current-target direction pulse"
                    if move is not None
                    else f"D={distance}: waiting for fresh direction or H cooldown {self._h_remaining(now):.2f}s"
                ),
            )

        if distance == 2:
            return self._decision(
                frame,
                move=None,
                move_pulse_profile=None,
                press_h=press_h,
                reason=(
                    f"D=2: mandatory current-frame {current_face} orientation pulse, then H 50ms"
                    if press_h
                    else f"D=2: hold with clean target; H cooldown {self._h_remaining(now):.2f}s"
                ),
            )

        if 3 <= distance <= MAX_H_RANGE_CELLS:
            direction = cardinal_move(
                frame.player_cell,
                self._confirmed_cell,
                None,
            )
            move, pulse = self._consume_move_if_ready(
                now,
                direction=direction,
                profile=MovementPulseProfile.APPROACH,
            )
            return self._decision(
                frame,
                move=move,
                move_pulse_profile=pulse,
                press_h=press_h,
                reason=(
                    f"D={distance}: clean target; mandatory current-frame {current_face} aim, "
                    f"H={'fire' if press_h else f'cooldown {self._h_remaining(now):.2f}s'}, "
                    "then APPROACH 100ms toward D=2"
                ),
            )

        direction = cardinal_move(
            frame.player_cell,
            self._confirmed_cell,
            None,
        )
        move, pulse = self._consume_move_if_ready(
            now,
            direction=direction,
            profile=MovementPulseProfile.APPROACH,
        )
        return self._decision(
            frame,
            move=move,
            move_pulse_profile=pulse,
            press_h=False,
            reason=f"D={distance}: outside H range D=50; approach 100ms with clean visual confirmation",
        )
