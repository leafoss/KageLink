from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from .domain import TargetState
from .facing_authority import FacingAuthority
from .player_facing_dataset import PlayerFacingDatasetCollector


def _orientation_state(decision) -> str:
    if decision.target_state in {
        TargetState.SEARCH,
        TargetState.ATTENTION,
        TargetState.OCCLUDED_COAST,
        TargetState.REID_LOCAL,
        TargetState.SUSPENDED,
        TargetState.ENDED,
    }:
        return decision.target_state.value
    if decision.turn_direction:
        return TargetState.TURN_ALIGN.value
    if decision.contact_deadzone_active and decision.r_authorized:
        return TargetState.CONTACT_LOCK.value
    if decision.r_authorized:
        return TargetState.LOCKED_ALIGNED.value
    return TargetState.LOCKED_UNALIGNED.value


class _RuntimeContext:
    def __init__(self) -> None:
        self.authority = FacingAuthority()
        self.latest_decision = None
        self.latest_candidate = None
        self.pending_turn = False
        self.pending_turn_direction: str | None = None
        self.just_confirmed_guard = 0
        self.startup_done = False
        self.startup_actions: tuple[str, ...] = ()
        self.turn_result: str | None = None
        self.dataset_pending: dict[str, Any] | None = None
        self.player_crop_saved = False
        self.player_crop_contamination: float | None = None
        self.previous_r_authorized = False
        self.previous_invalidation: str | None = None
        self.previous_stable_bearing: str | None = None

    def reset_target(self, *, preserve_startup: bool = False) -> None:
        startup = self.startup_done and preserve_startup
        self.authority.reset_round()
        if startup:
            self.authority.register_startup_right(now=time.monotonic())
        self.pending_turn = False
        self.pending_turn_direction = None
        self.just_confirmed_guard = 0
        self.turn_result = None
        self.dataset_pending = None
        self.player_crop_saved = False
        self.player_crop_contamination = None
        self.previous_r_authorized = False
        self.previous_invalidation = None
        self.previous_stable_bearing = None


_CONTEXT = _RuntimeContext()
_INSTALLED = False


def _selected_candidate(frame, decision):
    visual_track_id = getattr(decision, "visual_track_id", None)
    if visual_track_id is None:
        return None
    return next(
        (
            candidate
            for candidate in frame.candidates
            if int(candidate.track_id) == int(visual_track_id)
        ),
        None,
    )


def install_runtime_facing_patch(full_round_module: Any) -> None:
    """Install orientation authority without replacing the validated round loop."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import event_recorder as event_module
    from . import live_bridge as live_module
    from . import strategy as strategy_module
    from . import target_memory as target_module

    OriginalStrategy = strategy_module.GridFocusStrategy
    OriginalPhysical = live_module.PhysicalCombatInput
    OriginalMemory = target_module.TargetCapsuleMemory
    OriginalRecorder = event_module.CombatEventVideoRecorder
    original_write_log = full_round_module._write_log

    class FacingGridFocusStrategy:
        def __init__(self, *args, **kwargs) -> None:
            self._base = OriginalStrategy(*args, **kwargs)
            _CONTEXT.reset_target(preserve_startup=False)

        def __getattr__(self, name: str):
            return getattr(self._base, name)

        def reset_round(self) -> None:
            self._base.reset_round()
            _CONTEXT.reset_target(preserve_startup=False)

        def end_combat(self) -> None:
            self._base.end_combat()
            _CONTEXT.authority.invalidate("COMBAT_ENDED")

        def resolve_h_request(self, *, fired: bool) -> None:
            self._base.resolve_h_request(fired=fired)

        def update(self, frame):
            raw = self._base.update(frame)
            candidate = _selected_candidate(frame, raw)
            now = frame.effective_time_seconds
            _CONTEXT.turn_result = None

            if _CONTEXT.pending_turn:
                attempted = _CONTEXT.pending_turn_direction
                observed = (
                    _CONTEXT.authority.probe_bearing(
                        raw,
                        candidate,
                        attempted=attempted or "",
                    )
                    if attempted is not None
                    else None
                )
                success = _CONTEXT.authority.resolve_turn(
                    observed_bearing=observed,
                    target_visible=bool(
                        candidate is not None
                        and candidate.visible
                        and candidate.is_target_body
                    ),
                    now=now,
                    knockback_detected=False,
                )
                _CONTEXT.pending_turn = False
                _CONTEXT.pending_turn_direction = None
                _CONTEXT.turn_result = "TURN_ALIGN_CONFIRMED" if success else "TURN_ALIGN_FAILED"
                if success:
                    _CONTEXT.just_confirmed_guard = 1
                    _CONTEXT.dataset_pending = {
                        "direction": _CONTEXT.authority.confirmed_facing,
                        "confidence": _CONTEXT.authority.facing_confidence,
                        "source": _CONTEXT.authority.facing_source,
                        "frame_index": frame.frame_index,
                    }
                    print(
                        f"TURN_CONFIRMED facing={_CONTEXT.authority.confirmed_facing} "
                        "R_AUTHORIZED=False H_AUTHORIZED=False until next frame"
                    )
                else:
                    print("TURN_ALIGN_FAILED H remains blocked; cooldown preserved")

            authorized = _CONTEXT.authority.apply(raw, candidate, now=now)
            orientation = _orientation_state(authorized)

            if raw.press_h and not authorized.press_h:
                self._base.resolve_h_request(fired=False)

            if _CONTEXT.just_confirmed_guard > 0 and authorized.r_authorized:
                if raw.press_h:
                    self._base.resolve_h_request(fired=False)
                authorized = replace(
                    authorized,
                    hold_r=False,
                    r_keydown_heartbeat_ms=None,
                    press_h=False,
                    h_pulse_ms=None,
                    r_authorized=False,
                    h_authorized=False,
                    move=None,
                    move_pulse_profile=None,
                    move_pulse_ms=None,
                    h_cancel_reason="TURN_CONFIRMATION_GUARD",
                    reason=f"{authorized.reason}; one-frame guard after turn confirmation",
                )
                _CONTEXT.just_confirmed_guard -= 1

            # Keep the target-recognition state LOCKED so the validated Target
            # Capsule continues receiving clean exemplars. Orientation has its
            # own explicit state in telemetry and physical authority fields.
            authorized = replace(
                authorized,
                target_state=raw.target_state,
            )
            _CONTEXT.latest_decision = authorized
            _CONTEXT.latest_candidate = candidate

            if authorized.r_authorized != _CONTEXT.previous_r_authorized:
                print(f"R_AUTHORIZED={authorized.r_authorized}")
            if authorized.h_authorized:
                print("H_AUTHORIZED=True")
            if (
                authorized.orientation_invalidated_reason
                and authorized.orientation_invalidated_reason
                != _CONTEXT.previous_invalidation
            ):
                print(
                    "FACING_INVALIDATED reason="
                    f"{authorized.orientation_invalidated_reason}"
                )

            _CONTEXT.previous_r_authorized = authorized.r_authorized
            _CONTEXT.previous_invalidation = authorized.orientation_invalidated_reason
            _CONTEXT.previous_stable_bearing = authorized.stable_target_bearing
            return authorized

    class FacingPhysicalCombatInput(OriginalPhysical):
        def start_combat_hold(self) -> None:
            actions = self.startup_face_right()
            _CONTEXT.authority.register_startup_right(now=time.monotonic())
            _CONTEXT.startup_done = True
            _CONTEXT.startup_actions = actions
            print(
                "STARTUP_RIGHT_PULSE duration=90ms commanded_facing=RIGHT "
                "facing_source=STARTUP_RIGHT_PULSE"
            )

        def execute(self, decision, *, confirm_aim=None):
            if decision.turn_direction and not decision.r_authorized:
                if _CONTEXT.authority.begin_turn(
                    decision.turn_direction,
                    now=time.monotonic(),
                ):
                    print(
                        f"TURN_ALIGN direction={decision.turn_direction} "
                        f"attempt={_CONTEXT.authority.telemetry_turn_attempt} "
                        "R_AUTHORIZED=False H_AUTHORIZED=False"
                    )
                    actions = self.execute_turn(decision.turn_direction)
                    _CONTEXT.pending_turn = True
                    _CONTEXT.pending_turn_direction = decision.turn_direction
                    return actions
                self.controller.release_all()
                return ("RELEASE_ALL", "TURN_RETRY_BACKOFF")
            return super().execute(decision)

    class FacingTargetCapsuleMemory(OriginalMemory):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            root = Path(self.root) if self.root is not None else None
            report_root = root.parents[1] if root is not None and len(root.parents) >= 2 else Path.cwd()
            self._facing_dataset = PlayerFacingDatasetCollector(
                report_root / "player_facing_dataset"
            )

        def observe_selected(self, *args, **kwargs) -> None:
            super().observe_selected(*args, **kwargs)
            pending = _CONTEXT.dataset_pending
            if not pending:
                return
            direction = pending.get("direction")
            if not direction:
                _CONTEXT.dataset_pending = None
                return
            frame_bgr = kwargs.get("frame_bgr")
            state = kwargs.get("state")
            candidate = kwargs.get("candidate")
            if frame_bgr is None or state is None:
                return
            root_name = Path(self.root).name if self.root is not None else "round"
            saved, contamination, _ = self._facing_dataset.save_if_trustworthy(
                frame_bgr=frame_bgr,
                state=state,
                candidate=candidate,
                direction=direction,
                round_name=root_name,
                frame_index=int(pending.get("frame_index", 0)),
                confidence=float(pending.get("confidence", 0.0)),
                source=str(pending.get("source", "UNKNOWN")),
            )
            _CONTEXT.player_crop_saved = saved
            _CONTEXT.player_crop_contamination = contamination
            _CONTEXT.dataset_pending = None

    class FacingEventRecorder(OriginalRecorder):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._facing_previous_r = False
            self._facing_previous_invalid = None
            self._facing_previous_bearing = None
            self._startup_recorded = False

        def push(self, frame_bgr, *, decision, candidate, actions, events=(), **kwargs) -> None:
            inferred = list(events)
            if _CONTEXT.startup_done and not self._startup_recorded:
                inferred.append("STARTUP_RIGHT_PULSE")
                self._startup_recorded = True
            if decision.turn_direction:
                inferred.append("TURN_ALIGN_STARTED")
            if _CONTEXT.turn_result:
                inferred.append(_CONTEXT.turn_result)
                if _CONTEXT.turn_result == "TURN_ALIGN_FAILED":
                    inferred.append("AIM_UNCONFIRMED")
            if (
                decision.orientation_invalidated_reason
                and decision.orientation_invalidated_reason != self._facing_previous_invalid
            ):
                inferred.append("FACING_INVALIDATED")
            if decision.r_authorized != self._facing_previous_r:
                inferred.append("R_AUTHORITY_CHANGED")
            if (
                decision.grid_distance == 0
                and self._facing_previous_bearing
                and decision.stable_target_bearing
                and decision.stable_target_bearing != self._facing_previous_bearing
            ):
                inferred.append("CONTACT_SIDE_SWITCH")
            self._facing_previous_r = decision.r_authorized
            self._facing_previous_invalid = decision.orientation_invalidated_reason
            self._facing_previous_bearing = decision.stable_target_bearing
            super().push(
                frame_bgr,
                decision=decision,
                candidate=candidate,
                actions=actions,
                events=inferred,
                **kwargs,
            )

    def facing_write_log(handle, payload: dict[str, Any]) -> None:
        decision = _CONTEXT.latest_decision
        if payload.get("phase") == "combat" and decision is not None:
            target_state = payload.get("state")
            payload.update(
                {
                    "target_state": target_state,
                    "state": _orientation_state(decision),
                    "startup_right_pulse": _CONTEXT.startup_done,
                    "startup_right_duration_ms": 90 if _CONTEXT.startup_done else 0,
                    "raw_target_bearing": decision.raw_target_bearing,
                    "stable_target_bearing": decision.stable_target_bearing,
                    "bearing_confirmation_frames": decision.bearing_confirmation_frames,
                    "commanded_facing": decision.commanded_facing,
                    "confirmed_facing": decision.confirmed_facing,
                    "facing_source": decision.facing_source,
                    "facing_confidence": round(decision.facing_confidence, 4),
                    "facing_age_seconds": round(decision.facing_age_seconds, 4),
                    "turn_attempt": decision.turn_attempt,
                    "turn_confirmed": decision.turn_confirmed,
                    "r_authorized": decision.r_authorized,
                    "h_authorized": decision.h_authorized,
                    "orientation_invalidated_reason": decision.orientation_invalidated_reason,
                    "contact_deadzone_active": decision.contact_deadzone_active,
                    "side_crossing_frames": decision.side_crossing_frames,
                    "player_crop_saved": _CONTEXT.player_crop_saved,
                    "player_crop_contamination_score": _CONTEXT.player_crop_contamination,
                    "h_cancel_reason": decision.h_cancel_reason,
                }
            )
            _CONTEXT.player_crop_saved = False
            _CONTEXT.player_crop_contamination = None
        original_write_log(handle, payload)

    strategy_module.GridFocusStrategy = FacingGridFocusStrategy
    live_module.PhysicalCombatInput = FacingPhysicalCombatInput
    target_module.TargetCapsuleMemory = FacingTargetCapsuleMemory
    event_module.CombatEventVideoRecorder = FacingEventRecorder
    full_round_module._write_log = facing_write_log
    _INSTALLED = True


__all__ = ["install_runtime_facing_patch"]
