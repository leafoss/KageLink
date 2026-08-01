from __future__ import annotations

from dataclasses import dataclass

from .domain import (
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
        suspend_frames: int = 3,
        hard_lost_frames: int = 8,
    ) -> None:
        self.acquire_hits = max(2, int(acquire_hits))
        self.suspend_frames = max(1, int(suspend_frames))
        self.hard_lost_frames = max(self.suspend_frames + 1, int(hard_lost_frames))
        self.reset_round()

    def reset_round(self) -> None:
        self._state = TargetState.SEARCH
        self._next_target_id = 1
        self._target_id: int | None = None
        self._confirmed_cell: GridCell | None = None
        self._predicted_cell: GridCell | None = None
        self._attention: _AttentionHypothesis | None = None
        self._last_clean_frame: int | None = None
        self._last_face: str | None = None

    def end_combat(self) -> None:
        self._state = TargetState.ENDED
        self._target_id = None
        self._confirmed_cell = None
        self._predicted_cell = None
        self._attention = None
        self._last_clean_frame = None
        self._last_face = None

    def _focused_cells(self) -> set[GridCell] | None:
        if self._confirmed_cell is None:
            return None
        focused = {self._confirmed_cell}
        if self._predicted_cell is not None:
            focused.add(self._predicted_cell)
        if self._state is TargetState.SUSPENDED:
            origin = self._predicted_cell or self._confirmed_cell
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    focused.add(GridCell(origin.x + dx, origin.y + dy))
        return focused

    @staticmethod
    def _best_clean(
        candidates: tuple[CandidateObservation, ...],
        *,
        player_cell: GridCell,
        allowed_cells: set[GridCell] | None,
    ) -> CandidateObservation | None:
        valid = [
            candidate
            for candidate in candidates
            if candidate.is_clean_body
            and (allowed_cells is None or candidate.anchor_cell in allowed_cells)
        ]
        valid.sort(
            key=lambda candidate: (
                player_cell.chebyshev_distance(candidate.anchor_cell),
                -float(candidate.confidence),
                candidate.anchor_cell.x,
                candidate.anchor_cell.y,
                candidate.track_id,
            )
        )
        return valid[0] if valid else None

    def _update_face(self, frame: CombatFrame, clean: CandidateObservation | None) -> None:
        if clean is None:
            return
        if clean.anchor_cell == frame.player_cell:
            if clean.face_hint is not None:
                self._last_face = clean.face_hint
            return
        current = cardinal_face(frame.player_cell, clean.anchor_cell, self._last_face)
        if current is not None:
            self._last_face = current

    def _decision(
        self,
        frame: CombatFrame,
        *,
        move: str | None,
        move_pulse_profile: MovementPulseProfile | None,
        press_h: bool,
        reason: str,
    ) -> CombatDecision:
        distance = (
            frame.player_cell.chebyshev_distance(self._confirmed_cell)
            if self._confirmed_cell is not None
            else None
        )
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
            press_h=press_h,
            reason=reason,
        )

    def update(self, frame: CombatFrame) -> CombatDecision:
        if frame.ko_confirmed or any(
            candidate.kind is ObservationKind.KO for candidate in frame.candidates
        ):
            self.end_combat()
            return self._decision(
                frame,
                move=None,
                move_pulse_profile=None,
                press_h=False,
                reason="KO confirmed; combat authority disabled",
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
            allowed_cells=allowed,
        )

        if self._target_id is None:
            if clean is None:
                self._state = TargetState.SEARCH
                self._attention = None
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
            self._last_clean_frame = frame.frame_index
            self._state = TargetState.LOCKED
            self._attention = None
        elif clean is not None:
            previous = self._confirmed_cell
            assert previous is not None
            if previous.chebyshev_distance(clean.anchor_cell) > 1:
                clean = None
            else:
                self._confirmed_cell = clean.anchor_cell
                self._predicted_cell = previous.step_toward(clean.anchor_cell)
                self._last_clean_frame = frame.frame_index
                self._state = TargetState.LOCKED
                self._update_face(frame, clean)

        if clean is None and self._target_id is not None:
            assert self._last_clean_frame is not None
            missing = frame.frame_index - self._last_clean_frame
            if missing >= self.hard_lost_frames:
                old_id = self._target_id
                self._target_id = None
                self._confirmed_cell = None
                self._predicted_cell = None
                self._attention = None
                self._last_clean_frame = None
                self._state = TargetState.SEARCH
                return self._decision(
                    frame,
                    move=None,
                    move_pulse_profile=None,
                    press_h=False,
                    reason=f"target #{old_id} hard lost after {missing} frames",
                )
            self._state = TargetState.SUSPENDED
            return self._decision(
                frame,
                move=None,
                move_pulse_profile=None,
                press_h=False,
                reason=f"target suspended; local 3x3 recovery frame {missing}",
            )

        assert clean is not None
        assert self._confirmed_cell is not None
        distance = frame.player_cell.chebyshev_distance(self._confirmed_cell)

        if distance in {0, 1}:
            direction = self._last_face
            return self._decision(
                frame,
                move=direction.lower() if direction is not None else None,
                move_pulse_profile=(
                    MovementPulseProfile.VERY_SHORT if direction is not None else None
                ),
                press_h=False,
                reason=(
                    f"D={distance}: one VERY_SHORT direction pulse toward confirmed target; H forbidden"
                    if direction is not None
                    else f"D={distance}: target confirmed but no visual direction; hold fail-closed"
                ),
            )

        if distance == 2:
            return self._decision(
                frame,
                move=None,
                move_pulse_profile=None,
                press_h=True,
                reason="D=2: hold position and press H with current clean visual confirmation",
            )

        if distance == 3:
            return self._decision(
                frame,
                move=cardinal_move(frame.player_cell, self._confirmed_cell),
                move_pulse_profile=MovementPulseProfile.APPROACH,
                press_h=True,
                reason="D=3: press H with clean visual confirmation and approach toward D=2",
            )

        return self._decision(
            frame,
            move=None,
            move_pulse_profile=None,
            press_h=False,
            reason=f"D={distance}: rule not defined; hold fail-closed",
        )
