from __future__ import annotations

import math
import time
from typing import Any

from .hostility_gate import EntityState, HostilityState


_CAMERA_INSTALLED = False
_TARGET_INSTALLED = False
_PHASE_ALIAS_PERIOD_PX = 32.0
_PROVISIONAL_BODY_GRACE_SECONDS = 3.0


def nearest_phase_alias(
    value: float,
    accepted: float,
    *,
    period: float = _PHASE_ALIAS_PERIOD_PX,
) -> float:
    """Unwrap a periodic phase-correlation alias toward the accepted viewport.

    The dojo floor and the 64px grid contain repeating 32/64px structure. The
    physical PR26.16 run therefore produced raw estimates such as -64 and -96
    while the screen itself remained fixed. This helper changes only an exact
    periodic alias; ordinary small shifts remain untouched.
    """

    value = float(value)
    accepted = float(accepted)
    period = max(1.0, float(period))
    if not all(math.isfinite(item) for item in (value, accepted, period)):
        return value
    turns = round((accepted - value) / period)
    candidate = value + float(turns) * period
    if abs(candidate - accepted) + 0.25 < abs(value - accepted):
        return candidate
    return value


def valid_round_target_latch(gate: Any | None) -> bool:
    if gate is None:
        return False
    memory = getattr(gate, "_pr26_round_target_memory", None)
    if memory is None or getattr(memory, "last_raw_track_id", None) is None:
        return False
    track = getattr(memory, "track", None)
    return bool(
        track is not None
        and getattr(track, "entity_state", None) is EntityState.ENTITY_CONFIRMED
        and getattr(track, "hostility_state", None) is HostilityState.HOSTILE_CONFIRMED
    )


def provisional_body_hold_allowed(
    *,
    last_raw_at: float,
    now: float,
    valid_latch: bool,
    track_exists: bool,
    grace_seconds: float = _PROVISIONAL_BODY_GRACE_SECONDS,
) -> bool:
    return bool(
        not valid_latch
        and track_exists
        and math.isfinite(float(last_raw_at))
        and 0.0 <= float(now) - float(last_raw_at) <= float(grace_seconds)
    )


def install_prelatch_camera_retention() -> None:
    """Keep the captured viewport authoritative until a hostile body is latched.

    Before COMBAT_LOCK the physical controller can issue only isolated facing
    pulses. It cannot chase, so a large phase-correlation jump in this phase is
    necessarily an alias/noise event rather than legitimate camera travel.
    Exact baselines therefore remain alive instead of alternating 84 -> 0.
    """

    global _CAMERA_INSTALLED
    if _CAMERA_INSTALLED:
        return

    from .runtime_target_integrity import CameraStabilityGate

    original_evaluate = CameraStabilityGate.evaluate

    def retained_evaluate(self, dx, dy, response, raw_authoritative):
        try:
            from .runtime_tile_perception import current_hostility_gate

            gate = current_hostility_gate()
        except Exception:
            gate = None

        if not valid_round_target_latch(gate):
            if not bool(getattr(self, "initialized", False)):
                self.accepted = (0.0, 0.0)
                self.initialized = True
            self.pending = None
            self.pending_votes = 0
            self.reason = "PRELATCH_STATIC_VIEWPORT_HOLD"
            return (
                float(self.accepted[0]),
                float(self.accepted[1]),
                float(response),
                True,
            )

        accepted = (
            float(getattr(self, "accepted", (0.0, 0.0))[0]),
            float(getattr(self, "accepted", (0.0, 0.0))[1]),
        )
        normalized_dx = nearest_phase_alias(float(dx), accepted[0])
        normalized_dy = nearest_phase_alias(float(dy), accepted[1])
        alias_corrected = (
            abs(normalized_dx - float(dx)) >= 0.5
            or abs(normalized_dy - float(dy)) >= 0.5
        )
        result = original_evaluate(
            self,
            normalized_dx,
            normalized_dy,
            response,
            bool(raw_authoritative) or (alias_corrected and float(response) >= 0.035),
        )
        if alias_corrected and result[3]:
            self.reason = "PHASE_ALIAS_UNWRAPPED_32PX"
        return result[0], result[1], result[2], result[3]

    CameraStabilityGate.evaluate = retained_evaluate
    _CAMERA_INSTALLED = True
    print(
        "PR26.17 CAMERA ACQUISITION HOLD: before a valid hostile latch the viewport "
        "is fixed at the accepted pre-spawn transform; repeating 32px phase aliases "
        "cannot clear exact baselines"
    )


def install_provisional_body_target_retention() -> None:
    """Retain the first body-bound target through short raw-detector dropouts.

    This is deliberately not a combat latch. MOVE/H stay blocked until the same
    target receives the existing 2-of-3 raw-confirmed contact votes. The grace
    only prevents a raw-less scenery/NPC component from replacing the real body
    between those votes.
    """

    global _TARGET_INSTALLED
    if _TARGET_INSTALLED:
        return

    from .occupancy_tracking import PR26OccupancyTracker

    original_active = PR26OccupancyTracker._active

    def retained_active(self):
        now = time.monotonic()
        memory_valid = valid_round_target_latch(self)
        provisional_id = getattr(self, "_pr26_provisional_body_track_id", None)
        provisional_last_raw_at = float(
            getattr(self, "_pr26_provisional_body_last_raw_at", -1e9)
        )
        provisional = (
            self._tracks.get(provisional_id)
            if provisional_id is not None
            else None
        )

        if memory_valid:
            if provisional_id is not None:
                self._emit(
                    f"PR26_PROVISIONAL_BODY_RELEASED id={provisional_id} "
                    "reason=ROUND_TARGET_LATCHED"
                )
            self._pr26_provisional_body_track_id = None
            self._pr26_provisional_body_last_raw_at = -1e9
            return original_active(self)

        hold = provisional_body_hold_allowed(
            last_raw_at=provisional_last_raw_at,
            now=now,
            valid_latch=False,
            track_exists=provisional is not None,
        )

        # Let the existing sticky selector see the provisional body as a
        # selection candidate, but restore truthful visibility immediately after
        # selection. This preserves identity without pretending a current body
        # exists or authorizing an orientation/chase/H action.
        provisional_was_visible = None
        if (
            hold
            and provisional is not None
            and provisional.entity_state is EntityState.ENTITY_CONFIRMED
        ):
            provisional_was_visible = bool(provisional.visible)
            if not provisional_was_visible:
                provisional.visible = True
            self._pr26_selected_track_id = provisional.track_id

        selected = original_active(self)

        if provisional_was_visible is False and provisional is not None:
            provisional.visible = False

        current_body = bool(
            selected is not None
            and selected.visible
            and selected.raw_track_ids
            and selected.entity_state is EntityState.ENTITY_CONFIRMED
        )
        if current_body:
            previous_id = getattr(self, "_pr26_provisional_body_track_id", None)
            self._pr26_provisional_body_track_id = selected.track_id
            self._pr26_provisional_body_last_raw_at = now
            if previous_id != selected.track_id:
                self._emit(
                    f"PR26_PROVISIONAL_BODY_LATCH id={selected.track_id} "
                    f"raw_ids={sorted(selected.raw_track_ids)} "
                    f"grace={_PROVISIONAL_BODY_GRACE_SECONDS:.1f}s "
                    "combat_authority=BLOCKED_UNTIL_2_OF_3"
                )
            return selected

        provisional_id = getattr(self, "_pr26_provisional_body_track_id", None)
        provisional = (
            self._tracks.get(provisional_id)
            if provisional_id is not None
            else None
        )
        hold = provisional_body_hold_allowed(
            last_raw_at=float(
                getattr(self, "_pr26_provisional_body_last_raw_at", -1e9)
            ),
            now=now,
            valid_latch=False,
            track_exists=provisional is not None,
        )
        if hold and provisional is not None:
            if selected is not None and selected.track_id != provisional.track_id:
                selected.attention_lock = False
                selected.face_only_lock = False
                selected.combat_lock = False
            provisional.attention_lock = True
            provisional.face_only_lock = True
            provisional.combat_lock = False
            if provisional.hostility_state is HostilityState.HOSTILE_CONFIRMED:
                provisional.hostility_state = HostilityState.OBSERVE_HOSTILITY
            provisional.reason = (
                "provisional body identity retained; waiting for current raw body vote"
            )
            self._pr26_selected_track_id = provisional.track_id
            marker = (
                provisional.track_id,
                int((now - float(self._pr26_provisional_body_last_raw_at)) * 10.0),
            )
            if getattr(self, "_pr26_last_provisional_coast_marker", None) != marker:
                self._pr26_last_provisional_coast_marker = marker
                self._emit(
                    f"PR26_PROVISIONAL_BODY_COAST id={provisional.track_id} "
                    f"age={now-float(self._pr26_provisional_body_last_raw_at):.2f}s "
                    "rawless_challenger=BLOCKED MOVE=BLOCKED H=BLOCKED"
                )
            return provisional

        if provisional_id is not None:
            self._emit(
                f"PR26_PROVISIONAL_BODY_RELEASED id={provisional_id} "
                "reason=RAW_BODY_GRACE_EXPIRED"
            )
        self._pr26_provisional_body_track_id = None
        self._pr26_provisional_body_last_raw_at = -1e9
        return selected

    PR26OccupancyTracker._active = retained_active
    _TARGET_INSTALLED = True
    print(
        "PR26.17 PROVISIONAL BODY TARGET: the first exact-cell raw body remains the "
        "selected identity for 3.0s across detector gaps; raw-less challengers cannot "
        "replace it, while MOVE/H still require the original 2-of-3 COMBAT_LOCK"
    )


__all__ = [
    "install_prelatch_camera_retention",
    "install_provisional_body_target_retention",
    "nearest_phase_alias",
    "provisional_body_hold_allowed",
    "valid_round_target_latch",
]
