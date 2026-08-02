from __future__ import annotations

from dataclasses import dataclass

from .domain import (
    D0_AXIS_SWITCH_MARGIN_PX,
    D0_DEADZONE_PX,
    D0_DIRECTION_CONFIRM_FRAMES,
    HARD_LOST_SECONDS,
    H_COOLDOWN_SECONDS,
    H_PULSE_MS,
    LOCAL_REID_SECONDS,
    MAX_H_RANGE_CELLS,
    OCCLUDED_COAST_SECONDS,
    POST_PULSE_OBSERVE_MS,
    R_KEYDOWN_HEARTBEAT_MS,
    CandidateObservation,
    CombatDecision,
    CombatFrame,
    GridCell,
    MovementPulseProfile,
    ObservationKind,
    TargetState,
    cardinal_face,
)


@dataclass(slots=True)
class _AttentionHypothesis:
    cell: GridCell
    hits: int
    last_frame: int


class GridFocusStrategy:
    """Persistent logical-target policy on the immutable 64px grid.

    Track IDs are disposable evidence. The logical combat target survives short
    occlusion and local re-identification, while every H request requires a
    current target bearing and a closed-loop physical confirmation.
    """

    def __init__(
        self,
        *,
        acquire_hits: int = 2,
        occluded_coast_seconds: float = OCCLUDED_COAST_SECONDS,
        local_reid_seconds: float = LOCAL_REID_SECONDS,
        hard_lost_seconds: float = HARD_LOST_SECONDS,
        h_cooldown_seconds: float = H_COOLDOWN_SECONDS,
        d0_deadzone_px: float = D0_DEADZONE_PX,
        d0_axis_switch_margin_px: float = D0_AXIS_SWITCH_MARGIN_PX,
        d0_direction_confirm_frames: int = D0_DIRECTION_CONFIRM_FRAMES,
    ) -> None:
        self.acquire_hits = max(2, int(acquire_hits))
        self.occluded_coast_seconds = max(0.1, float(occluded_coast_seconds))
        self.local_reid_seconds = max(
            self.occluded_coast_seconds + 0.1,
            float(local_reid_seconds),
        )
        self.hard_lost_seconds = max(
            self.local_reid_seconds,
            float(hard_lost_seconds),
        )
        self.h_cooldown_seconds = max(H_COOLDOWN_SECONDS, float(h_cooldown_seconds))
        self.d0_deadzone_px = max(4.0, float(d0_deadzone_px))
        self.d0_axis_switch_margin_px = max(0.0, float(d0_axis_switch_margin_px))
        self.d0_direction_confirm_frames = max(1, int(d0_direction_confirm_frames))
        self.reset_round()

    def reset_round(self) -> None:
        self._state = TargetState.SEARCH
        self._next_target_id = 1
        self._target_id: int | None = None
        self._visual_track_id: int | None = None
        self._confirmed_cell: GridCell | None = None
        self._predicted_cell: GridCell | None = None
        self._attention: _AttentionHypothesis | None = None
        self._last_clean_at: float | None = None
        self._last_face: str | None = None
        self._pending_face: str | None = None
        self._pending_face_hits = 0
        self._last_h_at: float | None = None
        self._pending_h_requested_at: float | None = None
        self._pending_h_previous: float | None = None
        self._last_candidate: CandidateObservation | None = None

    def end_combat(self) -> None:
        self._state = TargetState.ENDED
        self._target_id = None
        self._visual_track_id = None
        self._confirmed_cell = None
        self._predicted_cell = None
        self._attention = None
        self._last_clean_at = None
        self._last_face = None
        self._pending_face = None
        self._pending_face_hits = 0
        self._last_h_at = None
        self._pending_h_requested_at = None
        self._pending_h_previous = None
        self._last_candidate = None

    @property
    def logical_target_id(self) -> int | None:
        return self._target_id

    @property
    def visual_track_id(self) -> int | None:
        return self._visual_track_id

    def resolve_h_request(self, *, fired: bool) -> None:
        """Commit or roll back the cooldown reservation made by ``update``.

        The live adapter calls this after closed-loop aim verification. A failed
        alignment does not consume the five-second H cooldown.
        """

        if self._pending_h_requested_at is None:
            return
        if not fired:
            self._last_h_at = self._pending_h_previous
        self._pending_h_requested_at = None
        self._pending_h_previous = None

    def _focused_cells(self) -> set[GridCell] | None:
        if self._confirmed_cell is None:
            return None

        origins = {self._confirmed_cell}
        if self._predicted_cell is not None:
            origins.add(self._predicted_cell)
        radius = 2 if self._state in {
            TargetState.OCCLUDED_COAST,
            TargetState.REID_LOCAL,
        } else 1
        focused: set[GridCell] = set()
        for origin in origins:
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    focused.add(GridCell(origin.x + dx, origin.y + dy))
        return focused

    @staticmethod
    def _best_target(
        candidates: tuple[CandidateObservation, ...],
        *,
        player_cell: GridCell,
        confirmed_cell: GridCell | None,
        allowed_cells: set[GridCell] | None,
        acquisition: bool,
    ) -> CandidateObservation | None:
        if acquisition:
            valid = [candidate for candidate in candidates if candidate.is_clean_body]
        else:
            valid = [
                candidate
                for candidate in candidates
                if candidate.is_target_body
                and (allowed_cells is None or candidate.anchor_cell in allowed_cells)
            ]

        identity_origin = confirmed_cell or player_cell
        valid.sort(
            key=lambda candidate: (
                candidate.background_probability,
                -float(candidate.identity_score),
                identity_origin.chebyshev_distance(candidate.anchor_cell),
                player_cell.chebyshev_distance(candidate.anchor_cell),
                -float(candidate.appearance_score),
                -float(candidate.confidence),
                candidate.anchor_cell.x,
                candidate.anchor_cell.y,
                candidate.track_id,
            )
        )
        return valid[0] if valid else None

    @staticmethod
    def _axis(face: str | None) -> str | None:
        if face in {"LEFT", "RIGHT"}:
            return "H"
        if face in {"UP", "DOWN"}:
            return "V"
        return None

    def _proposed_d0_face(
        self,
        candidate: CandidateObservation,
    ) -> tuple[str | None, bool]:
        offset = candidate.relative_offset_px
        if offset is None:
            proposed = candidate.face_hint
            if proposed is None:
                return self._last_face, False
            if self._last_face is None or proposed == self._last_face:
                self._last_face = proposed
                self._pending_face = None
                self._pending_face_hits = 0
                return proposed, True
            if self._pending_face == proposed:
                self._pending_face_hits += 1
            else:
                self._pending_face = proposed
                self._pending_face_hits = 1
            if self._pending_face_hits >= self.d0_direction_confirm_frames:
                self._last_face = proposed
                self._pending_face = None
                self._pending_face_hits = 0
                return proposed, True
            return self._last_face, False
        dx, dy = float(offset[0]), float(offset[1])
        if max(abs(dx), abs(dy)) < self.d0_deadzone_px:
            self._pending_face = None
            self._pending_face_hits = 0
            return self._last_face, False

        previous_axis = self._axis(self._last_face)
        if (
            previous_axis == "H"
            and abs(dx) + self.d0_axis_switch_margin_px >= abs(dy)
            and dx != 0
        ):
            proposed = "RIGHT" if dx > 0 else "LEFT"
        elif (
            previous_axis == "V"
            and abs(dy) + self.d0_axis_switch_margin_px >= abs(dx)
            and dy != 0
        ):
            proposed = "DOWN" if dy > 0 else "UP"
        elif abs(dx) >= abs(dy):
            proposed = "RIGHT" if dx > 0 else "LEFT"
        else:
            proposed = "DOWN" if dy > 0 else "UP"

        if self._last_face is None or proposed == self._last_face:
            self._last_face = proposed
            self._pending_face = None
            self._pending_face_hits = 0
            return proposed, True

        if self._pending_face == proposed:
            self._pending_face_hits += 1
        else:
            self._pending_face = proposed
            self._pending_face_hits = 1

        if self._pending_face_hits >= self.d0_direction_confirm_frames:
            self._last_face = proposed
            self._pending_face = None
            self._pending_face_hits = 0
            return proposed, True

        # Opposite/axis-changing microcorrections need a second consistent frame.
        return self._last_face, False

    def _update_face(
        self,
        frame: CombatFrame,
        candidate: CandidateObservation | None,
    ) -> tuple[str | None, bool]:
        if candidate is None:
            return self._last_face, False
        if candidate.anchor_cell == frame.player_cell:
            return self._proposed_d0_face(candidate)

        self._pending_face = None
        self._pending_face_hits = 0
        self._last_face = cardinal_face(frame.player_cell, candidate.anchor_cell, None)
        return self._last_face, self._last_face is not None

    def _h_remaining(self, now: float) -> float:
        if self._last_h_at is None:
            return 0.0
        return max(0.0, self.h_cooldown_seconds - (now - self._last_h_at))

    def _request_h_if_ready(self, now: float, *, allowed: bool) -> bool:
        if (
            not allowed
            or self._pending_h_requested_at is not None
            or self._h_remaining(now) > 0.0
        ):
            return False
        self._pending_h_previous = self._last_h_at
        self._pending_h_requested_at = now
        self._last_h_at = now
        return True

    @staticmethod
    def _chase(
        *,
        direction: str | None,
        distance: int,
        direction_confident: bool,
    ) -> tuple[str | None, MovementPulseProfile | None]:
        if direction is None or not direction_confident:
            return None, None
        profile = (
            MovementPulseProfile.VERY_SHORT
            if distance == 0
            else MovementPulseProfile.APPROACH
        )
        return direction.lower(), profile

    def _decision(
        self,
        frame: CombatFrame,
        *,
        candidate: CandidateObservation | None,
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
            sequence.append(f"AIM_CLOSED_LOOP_{self._last_face}")
            sequence.append(f"H_TAP_{H_PULSE_MS}MS_AFTER_CONFIRM")
        if move is not None and move_pulse_profile is not None:
            sequence.append(f"CHASE_{move.upper()}_{move_pulse_ms}MS")
        if press_h or move is not None:
            sequence.append(f"OBSERVE_{POST_PULSE_OBSERVE_MS}MS")

        evidence = candidate or self._last_candidate
        return CombatDecision(
            frame_index=frame.frame_index,
            target_state=self._state,
            combat_target_id=self._target_id,
            visual_track_id=(candidate.track_id if candidate is not None else self._visual_track_id),
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
            identity_score=float(evidence.identity_score) if evidence is not None else 0.0,
            appearance_score=float(evidence.appearance_score) if evidence is not None else 0.0,
            background_probability=(
                float(evidence.background_probability) if evidence is not None else 0.0
            ),
            reidentified=bool(evidence.reidentified) if evidence is not None else False,
            aim_requires_confirmation=press_h,
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
                candidate=None,
                move=None,
                move_pulse_profile=None,
                press_h=False,
                reason="KO confirmed; release R and disable all combat authority",
            )

        if self._state is TargetState.ENDED:
            return self._decision(
                frame,
                candidate=None,
                move=None,
                move_pulse_profile=None,
                press_h=False,
                reason="combat already ended",
            )

        candidate = self._best_target(
            frame.candidates,
            player_cell=frame.player_cell,
            confirmed_cell=self._confirmed_cell,
            allowed_cells=self._focused_cells(),
            acquisition=self._target_id is None,
        )

        if self._target_id is None:
            if candidate is None:
                self._state = TargetState.SEARCH
                self._attention = None
                self._last_face = None
                return self._decision(
                    frame,
                    candidate=None,
                    move=None,
                    move_pulse_profile=None,
                    press_h=False,
                    reason="global discovery: no clean single-cell body",
                )

            if self._attention is not None and self._attention.cell == candidate.anchor_cell:
                self._attention.hits += 1
                self._attention.last_frame = frame.frame_index
            else:
                self._attention = _AttentionHypothesis(
                    candidate.anchor_cell,
                    1,
                    frame.frame_index,
                )

            if self._attention.hits < self.acquire_hits:
                self._state = TargetState.ATTENTION
                self._confirmed_cell = candidate.anchor_cell
                self._predicted_cell = candidate.anchor_cell
                self._visual_track_id = candidate.track_id
                self._last_candidate = candidate
                return self._decision(
                    frame,
                    candidate=candidate,
                    move=None,
                    move_pulse_profile=None,
                    press_h=False,
                    reason=f"attention hypothesis {self._attention.hits}/{self.acquire_hits}",
                )

            self._target_id = self._next_target_id
            self._next_target_id += 1
            self._confirmed_cell = candidate.anchor_cell
            self._predicted_cell = candidate.anchor_cell
            self._visual_track_id = candidate.track_id
            self._last_clean_at = now
            self._state = TargetState.LOCKED
            self._attention = None
            self._last_candidate = candidate
        elif candidate is not None:
            previous = self._confirmed_cell
            assert previous is not None
            max_jump = 2 if candidate.reidentified else 1
            if previous.chebyshev_distance(candidate.anchor_cell) > max_jump:
                candidate = None
            else:
                self._confirmed_cell = candidate.anchor_cell
                self._predicted_cell = previous.step_toward(candidate.anchor_cell)
                self._last_clean_at = now
                self._state = TargetState.LOCKED
                self._visual_track_id = candidate.track_id
                self._last_candidate = candidate

        if candidate is None and self._target_id is not None:
            assert self._last_clean_at is not None
            missing_seconds = now - self._last_clean_at
            if missing_seconds >= self.hard_lost_seconds:
                old_id = self._target_id
                self._target_id = None
                self._visual_track_id = None
                self._confirmed_cell = None
                self._predicted_cell = None
                self._attention = None
                self._last_clean_at = None
                self._last_face = None
                self._last_candidate = None
                self._state = TargetState.SEARCH
                return self._decision(
                    frame,
                    candidate=None,
                    move=None,
                    move_pulse_profile=None,
                    press_h=False,
                    reason=f"target #{old_id} hard lost after {missing_seconds:.2f}s",
                )

            if missing_seconds <= self.occluded_coast_seconds:
                self._state = TargetState.OCCLUDED_COAST
                coast_move = self._last_face.lower() if self._last_face is not None else None
                coast_profile = (
                    MovementPulseProfile.VERY_SHORT if coast_move is not None else None
                )
                return self._decision(
                    frame,
                    candidate=None,
                    move=coast_move,
                    move_pulse_profile=coast_profile,
                    press_h=False,
                    reason=(
                        f"target occluded for {missing_seconds:.2f}s; predicted micro-chase only, "
                        "H forbidden"
                    ),
                )

            self._state = TargetState.REID_LOCAL
            return self._decision(
                frame,
                candidate=None,
                move=None,
                move_pulse_profile=None,
                press_h=False,
                reason=(
                    f"target locally re-identifying for {missing_seconds:.2f}s/"
                    f"{self.local_reid_seconds:.2f}s; logical identity retained"
                ),
            )

        assert candidate is not None
        assert self._confirmed_cell is not None
        distance = frame.player_cell.chebyshev_distance(self._confirmed_cell)
        current_face, direction_confident = self._update_face(frame, candidate)
        move, pulse = self._chase(
            direction=current_face,
            distance=distance,
            direction_confident=direction_confident,
        )
        press_h = self._request_h_if_ready(
            now,
            allowed=(
                distance <= MAX_H_RANGE_CELLS
                and current_face is not None
                and direction_confident
                and candidate.visible
            ),
        )

        if current_face is None or not direction_confident:
            reason = (
                f"D={distance}: target inside D0 deadzone or direction change awaiting "
                f"{self.d0_direction_confirm_frames} consistent frames; hold stable"
                if distance == 0
                else f"D={distance}: current direction is not trustworthy; fail closed"
            )
            return self._decision(
                frame,
                candidate=candidate,
                move=None,
                move_pulse_profile=None,
                press_h=False,
                reason=reason,
            )

        source = "REID" if candidate.reidentified else "CLEAN"
        return self._decision(
            frame,
            candidate=candidate,
            move=move,
            move_pulse_profile=pulse,
            press_h=press_h,
            reason=(
                f"D={distance}: CHASE_ALWAYS_ON source={source} identity="
                f"{candidate.identity_score:.2f} bg={candidate.background_probability:.2f}; "
                f"H={'request closed-loop aim' if press_h else ('out of range' if distance > MAX_H_RANGE_CELLS else f'cooldown {self._h_remaining(now):.2f}s')}"
            ),
        )
