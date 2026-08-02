from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .domain import (
    BACKGROUND_REJECT_SCORE,
    R_KEYDOWN_HEARTBEAT_MS,
    VERY_SHORT_PULSE_MS,
    CandidateObservation,
    CombatDecision,
    CombatFrame,
    MovementPulseProfile,
    ObservationKind,
    TargetState,
)

ATTENTION_GRACE_SECONDS = 1.60
RUNTIME_OCCLUDED_COAST_SECONDS = 1.25
MOTION_SUPPORT_MIN_SCORE = 0.55
MOTION_SUPPORT_MIN_CONFIDENCE = 0.45
MOTION_SUPPORT_MAX_BACKGROUND = min(0.68, BACKGROUND_REJECT_SCORE - 0.01)


@dataclass(slots=True)
class AttentionGraceLatch:
    grace_seconds: float = ATTENTION_GRACE_SECONDS
    deadline: float = -1.0
    last_decision: CombatDecision | None = None

    def reset(self) -> None:
        self.deadline = -1.0
        self.last_decision = None

    def arm(self, decision: CombatDecision, *, now: float) -> None:
        self.last_decision = decision
        self.deadline = float(now) + max(0.25, float(self.grace_seconds))

    def active(self, *, now: float) -> bool:
        return self.last_decision is not None and float(now) <= self.deadline


def baseline_r_required(decision: CombatDecision) -> bool:
    """R is the basic combat stance, independent from H/facing authority."""

    return bool(
        decision.target_state is not TargetState.ENDED
        and not decision.r_authorized
        and decision.turn_direction is None
        and decision.h_cancel_reason != "TURN_CONFIRMATION_GUARD"
    )


def _motion_supported_candidate(
    frame: CombatFrame,
    attention: CombatDecision | None,
) -> CandidateObservation | None:
    """Bridge one strict clean hit with the same moving visual track.

    The bridge is intentionally conservative: same raw track, same local area,
    visible, independently moving, non-background and non-multicell. It does not
    authorize H; it only lets the existing two-hit acquisition complete.
    """

    if attention is None or attention.visual_track_id is None:
        return None
    expected_cell = attention.confirmed_cell
    valid: list[CandidateObservation] = []
    for candidate in frame.candidates:
        if int(candidate.track_id) != int(attention.visual_track_id):
            continue
        if not candidate.visible:
            continue
        if candidate.kind is ObservationKind.MULTI_CELL_BLOB:
            continue
        if candidate.background_probability >= MOTION_SUPPORT_MAX_BACKGROUND:
            continue
        if candidate.motion_score < MOTION_SUPPORT_MIN_SCORE:
            continue
        if candidate.confidence < MOTION_SUPPORT_MIN_CONFIDENCE:
            continue
        if len(candidate.cells_touched) > 4:
            continue
        if (
            expected_cell is not None
            and expected_cell.chebyshev_distance(candidate.anchor_cell) > 1
        ):
            continue
        valid.append(candidate)

    valid.sort(
        key=lambda candidate: (
            -candidate.motion_score,
            candidate.background_probability,
            -candidate.confidence,
        )
    )
    return valid[0] if valid else None


def _promote_motion_support(
    frame: CombatFrame,
    candidate: CandidateObservation,
) -> CombatFrame:
    promoted = replace(
        candidate,
        kind=ObservationKind.CLEAN_BODY,
        body_like=True,
        cells_touched=frozenset({candidate.anchor_cell}),
    )
    candidates = tuple(
        promoted if int(item.track_id) == int(candidate.track_id) else item
        for item in frame.candidates
    )
    return replace(frame, candidates=candidates)


def install_runtime_engagement_recovery(full_round_module: Any | None = None) -> None:
    """Restore immediate R engagement while preserving strict H/facing gates."""

    from . import live_bridge as live_module
    from . import strategy as strategy_module

    if bool(getattr(strategy_module, "_PR25_ENGAGEMENT_RECOVERY_INSTALLED", False)):
        return

    CurrentStrategy = strategy_module.GridFocusStrategy
    CurrentPhysical = live_module.PhysicalCombatInput

    class EngagementRecoveryStrategy(CurrentStrategy):
        def __init__(self, *args, **kwargs) -> None:
            requested_coast = float(kwargs.get("occluded_coast_seconds", 0.0) or 0.0)
            kwargs["occluded_coast_seconds"] = max(
                RUNTIME_OCCLUDED_COAST_SECONDS,
                requested_coast,
            )
            super().__init__(*args, **kwargs)
            self._attention_grace = AttentionGraceLatch()

        def reset_round(self) -> None:
            super().reset_round()
            self._attention_grace.reset()

        def update(self, frame: CombatFrame) -> CombatDecision:
            now = frame.effective_time_seconds
            target_locked = getattr(self, "logical_target_id", None) is not None
            clean_present = any(candidate.is_clean_body for candidate in frame.candidates)
            promoted_by_motion = False

            if not target_locked and self._attention_grace.active(now=now):
                support = _motion_supported_candidate(
                    frame,
                    self._attention_grace.last_decision,
                )
                if support is not None and not clean_present:
                    frame = _promote_motion_support(frame, support)
                    clean_present = True
                    promoted_by_motion = True

                if not clean_present:
                    previous = self._attention_grace.last_decision
                    assert previous is not None
                    return replace(
                        previous,
                        frame_index=frame.frame_index,
                        press_h=False,
                        h_authorized=False,
                        h_pulse_ms=None,
                        move=None,
                        move_pulse_profile=None,
                        move_pulse_ms=None,
                        reason=(
                            f"{previous.reason}; attention retained through one noisy "
                            f"visual gap until {self._attention_grace.deadline:.2f}s"
                        ),
                    )

            decision = super().update(frame)

            if decision.target_state is TargetState.ATTENTION:
                self._attention_grace.arm(decision, now=now)
            elif decision.combat_target_id is not None:
                self._attention_grace.reset()
            elif not self._attention_grace.active(now=now):
                self._attention_grace.reset()

            if promoted_by_motion:
                decision = replace(
                    decision,
                    reason=(
                        f"{decision.reason}; acquisition completed by same-track "
                        "independent-motion support"
                    ),
                )

            if decision.target_state is TargetState.OCCLUDED_COAST:
                direction = decision.stable_target_bearing or decision.face
                if direction is not None:
                    decision = replace(
                        decision,
                        face=direction,
                        move=direction.lower(),
                        move_pulse_profile=MovementPulseProfile.VERY_SHORT,
                        move_pulse_ms=VERY_SHORT_PULSE_MS,
                        hold_r=True,
                        r_keydown_heartbeat_ms=R_KEYDOWN_HEARTBEAT_MS,
                        press_h=False,
                        h_pulse_ms=None,
                        r_authorized=True,
                        h_authorized=False,
                        h_cancel_reason="OCCLUDED_COAST_NO_H",
                        reason=(
                            f"{decision.reason}; bounded coast restored for low-FPS "
                            f"capture window <= {RUNTIME_OCCLUDED_COAST_SECONDS:.2f}s"
                        ),
                    )
            return decision

    class EngagementRecoveryPhysical(CurrentPhysical):
        def start_combat_hold(self) -> None:
            super().start_combat_hold()
            self.controller.apply_keys(("r",))
            print(
                "R_BASELINE_STARTED heartbeat=250ms phase=COMBAT_ARMED "
                "H_AUTHORIZED=False until target/facing lock"
            )

        def execute(self, decision, *, confirm_aim=None):
            if baseline_r_required(decision):
                self.controller.apply_keys(("r",))
                return (
                    "R_BASELINE",
                    "H_BLOCKED_WAITING_FOR_TARGET_OR_ALIGNMENT",
                )
            return super().execute(decision, confirm_aim=confirm_aim)

    strategy_module.GridFocusStrategy = EngagementRecoveryStrategy
    live_module.PhysicalCombatInput = EngagementRecoveryPhysical
    strategy_module._PR25_ENGAGEMENT_RECOVERY_INSTALLED = True

    if full_round_module is not None:
        original_write_log = full_round_module._write_log

        def engagement_write_log(handle, payload: dict[str, Any]) -> None:
            if payload.get("phase") == "combat":
                actions = tuple(payload.get("actions") or ())
                payload["r_baseline_active"] = any(
                    action in {"R_BASELINE", "R_AUTHORIZED"}
                    for action in actions
                )
                payload["engagement_policy"] = (
                    "ALIGNED_AUTHORITY"
                    if "R_AUTHORIZED" in actions
                    else "BASELINE_R_H_BLOCKED"
                    if "R_BASELINE" in actions
                    else "EXCLUSIVE_TURN_OR_STOP"
                )
            original_write_log(handle, payload)

        full_round_module._write_log = engagement_write_log


__all__ = [
    "ATTENTION_GRACE_SECONDS",
    "RUNTIME_OCCLUDED_COAST_SECONDS",
    "AttentionGraceLatch",
    "baseline_r_required",
    "install_runtime_engagement_recovery",
]
