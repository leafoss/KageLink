from __future__ import annotations

from types import SimpleNamespace


def main(argv: list[str] | None = None) -> int:
    # Install the same shared strategy/input authority before live_input imports
    # its class aliases. Unlike FullLoop, this isolated mode performs its own
    # startup RIGHT pulse because there is no outer dialog/OK process.
    dummy_round = SimpleNamespace(_write_log=lambda handle, payload: None)
    from .runtime_engagement_recovery import install_runtime_engagement_recovery
    from .runtime_facing_patch import _CONTEXT, install_runtime_facing_patch

    install_runtime_facing_patch(dummy_round)
    install_runtime_engagement_recovery(dummy_round)

    from . import live_input as live_module

    original_write = live_module._write_log

    def facing_write(handle, payload):
        decision = _CONTEXT.latest_decision
        if decision is not None and "frame" in payload:
            state = (
                "TURN_ALIGN"
                if decision.turn_direction
                else "CONTACT_LOCK"
                if decision.contact_deadzone_active and decision.r_authorized
                else "LOCKED_ALIGNED"
                if decision.r_authorized
                else "LOCKED_UNALIGNED"
                if decision.target_state.value == "LOCKED"
                else decision.target_state.value
            )
            actions = tuple(payload.get("actions") or ())
            payload.update(
                {
                    "target_state": payload.get("state"),
                    "state": state,
                    "raw_target_bearing": decision.raw_target_bearing,
                    "stable_target_bearing": decision.stable_target_bearing,
                    "commanded_facing": decision.commanded_facing,
                    "confirmed_facing": decision.confirmed_facing,
                    "facing_source": decision.facing_source,
                    "facing_confidence": decision.facing_confidence,
                    "turn_attempt": decision.turn_attempt,
                    "r_authorized": decision.r_authorized,
                    "r_baseline_active": any(
                        action in {"R_BASELINE", "R_AUTHORIZED"}
                        for action in actions
                    ),
                    "h_authorized": decision.h_authorized,
                    "orientation_invalidated_reason": decision.orientation_invalidated_reason,
                    "contact_deadzone_active": decision.contact_deadzone_active,
                    "h_cancel_reason": decision.h_cancel_reason,
                }
            )
        original_write(handle, payload)

    live_module._write_log = facing_write
    print("LIVE INPUT: explicit Facing Authority enabled")
    print("LIVE INPUT: startup RIGHT -> R baseline -> acquire -> align -> H authority")
    return int(live_module.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
