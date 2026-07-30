from __future__ import annotations

from typing import Any


MEDITATING = "MEDITATING"
EXITING_MEDITATION = "EXITING_MEDITATION"


def install_chakra_recovery_bridge(runtime: Any):
    """Restore the validated fast-Chakra side effect inside the 3.5.1 guard.

    The protected meditation guard intentionally owns V and returns early while a
    transition is active. The validated FastChakraVisualRecoveryEngine normally
    updates its Y toggle after ``super().step()``, so those early returns skipped
    the Y update completely. This bridge invokes only that inherited side effect;
    it does not make meditation-state or V decisions.
    """

    engine_type = runtime.ClosedLoopVisualRecoveryEngine
    if bool(getattr(engine_type, "_kagelink_v351_chakra_bridge", False)):
        return engine_type

    original_step = engine_type.step
    telemetry = runtime._telemetry

    def guarded_step_with_chakra(self, *args, **kwargs):
        decision = original_step(self, *args, **kwargs)
        guard = getattr(self, "meditation_guard", None)
        phase = str(getattr(guard, "phase", "") or "")
        updater = getattr(self, "_update_fast_chakra", None)
        pending_before = getattr(self, "pending_y_action", None)

        # The 3.5.1 guard bypasses FastChakraVisualRecoveryEngine.step while
        # meditating. Re-run only its inherited Y decision hook with the guarded
        # decision and current resource readings.
        if (
            phase == MEDITATING
            and str(getattr(decision, "state", "")) == MEDITATING
            and callable(updater)
        ):
            updater(decision)

        # The controller consumes pending Y actions on apply_keys(()) before it
        # processes decision.tap_v. Queue Y OFF first so a timeout or normal exit
        # cannot leave fast Chakra charging active after meditation closes.
        if (
            phase == EXITING_MEDITATION
            and bool(getattr(self, "y_fast_active", False))
            and getattr(self, "pending_y_action", None) is None
        ):
            self.pending_y_action = "off"

        pending_after = getattr(self, "pending_y_action", None)
        if pending_after is not None and pending_after != pending_before:
            telemetry(
                "DOJO_FAST_CHAKRA_ACTION_QUEUED",
                {
                    "action": pending_after,
                    "phase": phase or "-",
                    "hp": (
                        "-"
                        if getattr(decision, "health", None) is None
                        else f"{float(decision.health):.3f}"
                    ),
                    "chakra": (
                        "-"
                        if getattr(decision, "chakra", None) is None
                        else f"{float(decision.chakra):.3f}"
                    ),
                },
            )
        return decision

    engine_type.step = guarded_step_with_chakra
    engine_type._kagelink_v351_chakra_bridge = True
    telemetry(
        "DOJO_FAST_CHAKRA_BRIDGE_INSTALLED",
        {"engine": engine_type.__name__},
    )
    return engine_type


__all__ = ["install_chakra_recovery_bridge"]
