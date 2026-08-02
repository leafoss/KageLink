from __future__ import annotations

from dataclasses import replace

from .domain import (
    D0_AXIS_SWITCH_MARGIN_PX,
    D0_DEADZONE_PX,
    D0_SIDE_SWITCH_CONFIRM_FRAMES,
    D0_SIDE_SWITCH_THRESHOLD_PX,
    MAX_TURN_ATTEMPTS,
    R_KEYDOWN_HEARTBEAT_MS,
    CandidateObservation,
    CombatDecision,
    FacingSource,
    TargetState,
)

_CARDINAL = {"LEFT", "RIGHT", "UP", "DOWN"}
_NON_COMBAT_STATES = {
    TargetState.SEARCH,
    TargetState.ATTENTION,
    TargetState.OCCLUDED_COAST,
    TargetState.REID_LOCAL,
    TargetState.SUSPENDED,
    TargetState.ENDED,
}
_OPPOSITE = {
    ("LEFT", "RIGHT"),
    ("RIGHT", "LEFT"),
    ("UP", "DOWN"),
    ("DOWN", "UP"),
}


class FacingAuthority:
    """Own target bearing, commanded facing and confirmed facing separately.

    Sending a direction is never treated as proof by itself. Startup and turn
    transactions must be reported explicitly after their physical settle window.
    """

    def __init__(
        self,
        *,
        d0_deadzone_px: float = D0_DEADZONE_PX,
        d0_side_switch_threshold_px: float = D0_SIDE_SWITCH_THRESHOLD_PX,
        d0_side_switch_confirm_frames: int = D0_SIDE_SWITCH_CONFIRM_FRAMES,
        d0_axis_switch_margin_px: float = D0_AXIS_SWITCH_MARGIN_PX,
        max_turn_attempts: int = MAX_TURN_ATTEMPTS,
        turn_retry_delay_seconds: float = 0.35,
    ) -> None:
        self.d0_deadzone_px = max(4.0, float(d0_deadzone_px))
        self.d0_side_switch_threshold_px = max(
            self.d0_deadzone_px,
            float(d0_side_switch_threshold_px),
        )
        self.d0_side_switch_confirm_frames = max(
            2,
            int(d0_side_switch_confirm_frames),
        )
        self.d0_axis_switch_margin_px = max(0.0, float(d0_axis_switch_margin_px))
        self.max_turn_attempts = max(1, int(max_turn_attempts))
        self.turn_retry_delay_seconds = max(0.1, float(turn_retry_delay_seconds))
        self.reset_round()

    def reset_round(self) -> None:
        self.commanded_facing: str | None = None
        self.confirmed_facing: str | None = None
        self.facing_source = FacingSource.UNKNOWN.value
        self.facing_confidence = 0.0
        self._facing_confirmed_at: float | None = None

        self.raw_target_bearing: str | None = None
        self.stable_target_bearing: str | None = None
        self.bearing_confirmation_frames = 0
        self._pending_bearing: str | None = None
        self._pending_bearing_hits = 0
        self.side_crossing_frames = 0
        self.contact_deadzone_active = False

        self.turn_attempt = 0
        self._last_turn_attempt = 0
        self.turn_confirmed = False
        self.turn_direction: str | None = None
        self._turn_retry_after = 0.0
        self._turn_pending = False
        self._aim_unconfirmed_streak = 0

        self.orientation_invalidated_reason: str | None = None
        self._last_candidate_cell = None
        self._last_relative_offset: tuple[float, float] | None = None
        self._startup_right_pulse = False

    @property
    def telemetry_turn_attempt(self) -> int:
        return self.turn_attempt or self._last_turn_attempt

    @staticmethod
    def _normalize(direction: str | None) -> str | None:
        if direction is None:
            return None
        value = str(direction).upper()
        return value if value in _CARDINAL else None

    @staticmethod
    def _axis(direction: str | None) -> str | None:
        if direction in {"LEFT", "RIGHT"}:
            return "H"
        if direction in {"UP", "DOWN"}:
            return "V"
        return None

    def register_startup_right(self, *, now: float) -> None:
        """Accept the completed exclusive post-OK RIGHT transaction."""

        self.commanded_facing = "RIGHT"
        self.confirmed_facing = "RIGHT"
        self.facing_source = FacingSource.STARTUP_RIGHT_PULSE.value
        self.facing_confidence = 0.80
        self._facing_confirmed_at = float(now)
        self.turn_confirmed = True
        self.turn_attempt = 0
        self.turn_direction = None
        self._turn_pending = False
        self.orientation_invalidated_reason = None
        self._startup_right_pulse = True

    def invalidate(self, reason: str) -> None:
        self.confirmed_facing = None
        self.facing_source = FacingSource.UNKNOWN.value
        self.facing_confidence = 0.0
        self._facing_confirmed_at = None
        self.turn_confirmed = False
        self.orientation_invalidated_reason = str(reason)

    def begin_turn(self, direction: str, *, now: float) -> bool:
        normalized = self._normalize(direction)
        if normalized is None or float(now) < self._turn_retry_after:
            return False
        if self.turn_attempt >= self.max_turn_attempts:
            return False
        self.turn_attempt += 1
        self._last_turn_attempt = self.turn_attempt
        self.commanded_facing = normalized
        self.turn_direction = normalized
        self.turn_confirmed = False
        self._turn_pending = True
        return True

    def resolve_turn(
        self,
        *,
        observed_bearing: str | None,
        target_visible: bool,
        now: float,
        knockback_detected: bool = False,
    ) -> bool:
        attempted = self._normalize(self.turn_direction or self.commanded_facing)
        observed = self._normalize(observed_bearing)
        success = (
            attempted is not None
            and target_visible
            and observed == attempted
            and not knockback_detected
        )
        self._turn_pending = False

        if success:
            self.confirmed_facing = attempted
            self.facing_source = FacingSource.EXCLUSIVE_TURN_TRANSACTION.value
            self.facing_confidence = 0.86
            self._facing_confirmed_at = float(now)
            self.turn_confirmed = True
            self.orientation_invalidated_reason = None
            self._aim_unconfirmed_streak = 0
            self.turn_direction = None
            self.turn_attempt = 0
            return True

        self._aim_unconfirmed_streak += 1
        self.invalidate("AIM_UNCONFIRMED")
        if knockback_detected:
            self.orientation_invalidated_reason = "KNOCKBACK"
        if self.turn_attempt >= self.max_turn_attempts:
            self._turn_retry_after = float(now) + self.turn_retry_delay_seconds
            self.turn_attempt = 0
        self.turn_direction = None
        return False

    def _bearing_from_candidate(
        self,
        decision: CombatDecision,
        candidate: CandidateObservation | None,
    ) -> str | None:
        self.contact_deadzone_active = False
        if candidate is None:
            return None

        if decision.grid_distance != 0:
            return self._normalize(decision.face)

        offset = candidate.relative_offset_px
        if offset is None:
            return self._normalize(candidate.face_hint or decision.face)

        dx, dy = float(offset[0]), float(offset[1])
        if max(abs(dx), abs(dy)) < self.d0_deadzone_px:
            self.contact_deadzone_active = True
            return None

        previous_axis = self._axis(self.stable_target_bearing or self.confirmed_facing)
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

        current = self.stable_target_bearing or self.confirmed_facing
        if current is not None and proposed != current:
            dominant = abs(dx) if proposed in {"LEFT", "RIGHT"} else abs(dy)
            if dominant < self.d0_side_switch_threshold_px:
                return None
        return proposed

    def probe_bearing(
        self,
        decision: CombatDecision,
        candidate: CandidateObservation | None,
        *,
        attempted: str,
    ) -> str | None:
        raw = self._bearing_from_candidate(decision, candidate)
        if raw is None and self.contact_deadzone_active:
            stable = self.stable_target_bearing or self.confirmed_facing
            if stable == self._normalize(attempted):
                return stable
        return raw

    def _update_stable_bearing(
        self,
        *,
        raw: str | None,
        decision: CombatDecision,
    ) -> bool:
        if self.stable_target_bearing is None and self.confirmed_facing is not None:
            self.stable_target_bearing = self.confirmed_facing
            self.bearing_confirmation_frames = max(1, self.bearing_confirmation_frames)
        previous = self.stable_target_bearing
        self.raw_target_bearing = raw

        if self.contact_deadzone_active:
            self._pending_bearing = None
            self._pending_bearing_hits = 0
            self.side_crossing_frames = 0
            if self.stable_target_bearing is None:
                self.stable_target_bearing = self.confirmed_facing
            self.bearing_confirmation_frames = max(
                self.bearing_confirmation_frames,
                1 if self.stable_target_bearing else 0,
            )
            return previous != self.stable_target_bearing

        if raw is None:
            self.bearing_confirmation_frames = 0
            self.side_crossing_frames = 0
            return False

        required = self.d0_side_switch_confirm_frames if decision.grid_distance == 0 else 1
        if raw == self.stable_target_bearing:
            self._pending_bearing = None
            self._pending_bearing_hits = 0
            self.side_crossing_frames = 0
            self.bearing_confirmation_frames = min(
                99,
                max(1, self.bearing_confirmation_frames + 1),
            )
            return False

        if self._pending_bearing == raw:
            self._pending_bearing_hits += 1
        else:
            self._pending_bearing = raw
            self._pending_bearing_hits = 1
        self.side_crossing_frames = self._pending_bearing_hits if decision.grid_distance == 0 else 0

        if self._pending_bearing_hits < required:
            self.bearing_confirmation_frames = self._pending_bearing_hits
            return False

        self.stable_target_bearing = raw
        self.bearing_confirmation_frames = self._pending_bearing_hits
        self._pending_bearing = None
        self._pending_bearing_hits = 0
        return previous != self.stable_target_bearing

    def _detect_orientation_invalidation(
        self,
        *,
        candidate: CandidateObservation | None,
        bearing_changed: bool,
    ) -> str | None:
        reason = None
        if candidate is not None:
            if self._last_candidate_cell is not None:
                jump = self._last_candidate_cell.chebyshev_distance(candidate.anchor_cell)
                if jump > 1 and not candidate.reidentified:
                    reason = "BEARING_JUMP"
            offset = candidate.relative_offset_px
            if offset is not None and self._last_relative_offset is not None:
                dx = float(offset[0]) - float(self._last_relative_offset[0])
                dy = float(offset[1]) - float(self._last_relative_offset[1])
                if max(abs(dx), abs(dy)) >= 72.0 and not candidate.reidentified:
                    reason = "KNOCKBACK"
            self._last_candidate_cell = candidate.anchor_cell
            self._last_relative_offset = offset

        if (
            reason is None
            and bearing_changed
            and self.confirmed_facing is not None
            and self.stable_target_bearing is not None
            and self.confirmed_facing != self.stable_target_bearing
        ):
            if (self.confirmed_facing, self.stable_target_bearing) in _OPPOSITE:
                reason = "TARGET_CROSSED_PLAYER"
            else:
                reason = "BEARING_JUMP"
        return reason

    def apply(
        self,
        decision: CombatDecision,
        candidate: CandidateObservation | None,
        *,
        now: float,
    ) -> CombatDecision:
        now = float(now)
        raw = self._bearing_from_candidate(decision, candidate)
        bearing_changed = self._update_stable_bearing(raw=raw, decision=decision)
        invalidation = self._detect_orientation_invalidation(
            candidate=candidate,
            bearing_changed=bearing_changed,
        )
        if invalidation is not None:
            self.invalidate(invalidation)

        target_visible = bool(
            candidate is not None
            and candidate.visible
            and candidate.is_target_body
            and decision.combat_target_id is not None
        )
        stable = self.stable_target_bearing
        facing_age = (
            max(0.0, now - self._facing_confirmed_at)
            if self._facing_confirmed_at is not None
            else 0.0
        )

        if decision.target_state in _NON_COMBAT_STATES or not target_visible:
            return replace(
                decision,
                face=stable,
                move=None,
                move_pulse_profile=None,
                move_pulse_ms=None,
                hold_r=False,
                r_keydown_heartbeat_ms=None,
                press_h=False,
                h_pulse_ms=None,
                aim_requires_confirmation=False,
                raw_target_bearing=raw,
                stable_target_bearing=stable,
                bearing_confirmation_frames=self.bearing_confirmation_frames,
                commanded_facing=self.commanded_facing,
                confirmed_facing=self.confirmed_facing,
                facing_source=self.facing_source,
                facing_confidence=self.facing_confidence,
                facing_age_seconds=facing_age,
                turn_attempt=self.telemetry_turn_attempt,
                turn_confirmed=self.turn_confirmed,
                turn_direction=None,
                r_authorized=False,
                h_authorized=False,
                orientation_invalidated_reason=self.orientation_invalidated_reason,
                contact_deadzone_active=self.contact_deadzone_active,
                side_crossing_frames=self.side_crossing_frames,
                startup_right_pulse=self._startup_right_pulse,
                startup_right_duration_ms=90 if self._startup_right_pulse else 0,
                h_cancel_reason=("NO_COMBAT_AUTHORITY" if decision.press_h else None),
                reason=f"{decision.reason}; R/H blocked without aligned visible target",
            )

        aligned = (
            stable is not None
            and self.confirmed_facing is not None
            and self.confirmed_facing == stable
            and not self._turn_pending
        )

        if not aligned:
            can_turn = stable is not None and now >= self._turn_retry_after
            state = TargetState.TURN_ALIGN if can_turn else TargetState.LOCKED_UNALIGNED
            turn_direction = stable if can_turn else None
            return replace(
                decision,
                target_state=state,
                face=stable,
                move=None,
                move_pulse_profile=None,
                move_pulse_ms=None,
                hold_r=False,
                r_keydown_heartbeat_ms=None,
                press_h=False,
                h_pulse_ms=None,
                aim_requires_confirmation=False,
                raw_target_bearing=raw,
                stable_target_bearing=stable,
                bearing_confirmation_frames=self.bearing_confirmation_frames,
                commanded_facing=self.commanded_facing,
                confirmed_facing=self.confirmed_facing,
                facing_source=self.facing_source,
                facing_confidence=self.facing_confidence,
                facing_age_seconds=facing_age,
                turn_attempt=self.telemetry_turn_attempt,
                turn_confirmed=False,
                turn_direction=turn_direction,
                r_authorized=False,
                h_authorized=False,
                orientation_invalidated_reason=self.orientation_invalidated_reason,
                contact_deadzone_active=self.contact_deadzone_active,
                side_crossing_frames=self.side_crossing_frames,
                startup_right_pulse=self._startup_right_pulse,
                startup_right_duration_ms=90 if self._startup_right_pulse else 0,
                h_cancel_reason=("FACING_NOT_CONFIRMED" if decision.press_h else None),
                reason=f"{decision.reason}; TURN_ALIGN required before R/H",
            )

        state = TargetState.CONTACT_LOCK if self.contact_deadzone_active else TargetState.LOCKED_ALIGNED
        h_authorized = bool(decision.press_h)
        move = None if self.contact_deadzone_active else decision.move
        move_profile = None if self.contact_deadzone_active else decision.move_pulse_profile
        move_ms = None if self.contact_deadzone_active else decision.move_pulse_ms
        return replace(
            decision,
            target_state=state,
            face=stable,
            move=move,
            move_pulse_profile=move_profile,
            move_pulse_ms=move_ms,
            hold_r=True,
            r_keydown_heartbeat_ms=R_KEYDOWN_HEARTBEAT_MS,
            press_h=h_authorized,
            h_pulse_ms=decision.h_pulse_ms if h_authorized else None,
            aim_requires_confirmation=False,
            raw_target_bearing=raw,
            stable_target_bearing=stable,
            bearing_confirmation_frames=self.bearing_confirmation_frames,
            commanded_facing=self.commanded_facing,
            confirmed_facing=self.confirmed_facing,
            facing_source=self.facing_source,
            facing_confidence=self.facing_confidence,
            facing_age_seconds=facing_age,
            turn_attempt=self.telemetry_turn_attempt,
            turn_confirmed=self.turn_confirmed,
            turn_direction=None,
            r_authorized=True,
            h_authorized=h_authorized,
            orientation_invalidated_reason=self.orientation_invalidated_reason,
            contact_deadzone_active=self.contact_deadzone_active,
            side_crossing_frames=self.side_crossing_frames,
            startup_right_pulse=self._startup_right_pulse,
            startup_right_duration_ms=90 if self._startup_right_pulse else 0,
            h_cancel_reason=None,
            reason=f"{decision.reason}; facing aligned by {self.facing_source}",
        )


__all__ = ["FacingAuthority"]
