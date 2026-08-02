from __future__ import annotations

from .occupancy_tracking import PR26ControlMode


_INSTALLED = False


def install_runtime_control_mode() -> None:
    """Enforce PR26.3 safety modes at the outermost physical-input boundary."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import live_bridge as live_module

    CurrentPhysical = live_module.PhysicalCombatInput

    class PR26ModePhysicalCombatInput(CurrentPhysical):
        def _stop_validation_input(self) -> None:
            # Fail closed even when an inherited PR25 wrapper configured R as a
            # repeat key or started the baseline hold before this call.
            self.controller.repeat_keys = set()
            self.controller.release_all()

        def activate(self) -> None:
            super().activate()
            mode = PR26ControlMode.from_environment()
            if mode is not PR26ControlMode.FULL_COMBAT:
                self._stop_validation_input()
                print(
                    "PR26_VALIDATION_INPUT_ARMED "
                    f"mode={mode.value} repeat_keys=EMPTY physical_keys=RELEASED"
                )

        def start_combat_hold(self) -> None:
            mode = PR26ControlMode.from_environment()
            if mode is PR26ControlMode.FULL_COMBAT:
                return super().start_combat_hold()
            self._stop_validation_input()
            print(
                "R_BASELINE_BLOCKED "
                f"mode={mode.value} phase=COMBAT_ARMED repeat_keys=EMPTY"
            )
            return None

        def execute(self, decision, *, confirm_aim=None):
            mode = PR26ControlMode.from_environment()
            if mode is PR26ControlMode.PERCEPTION_ONLY:
                self._stop_validation_input()
                return (
                    "RELEASE_ALL",
                    "PR26_PERCEPTION_ONLY_TURN_MOVE_R_H_BLOCKED",
                )
            if mode is PR26ControlMode.FACE_ONLY:
                # The facing-authority wrapper performs an exclusive turn when
                # turn_direction is present and r_authorized is false. That is
                # the only physical action allowed in FACE_ONLY.
                if bool(getattr(decision, "turn_direction", None)) and not bool(
                    getattr(decision, "r_authorized", False)
                ):
                    self.controller.repeat_keys = set()
                    return super().execute(decision, confirm_aim=confirm_aim)
                self._stop_validation_input()
                return (
                    "RELEASE_ALL",
                    "PR26_FACE_ONLY_MOVE_R_H_BLOCKED",
                )
            return super().execute(decision, confirm_aim=confirm_aim)

    live_module.PhysicalCombatInput = PR26ModePhysicalCombatInput
    _INSTALLED = True
    print(
        "PR26.3 CONTROL MODE: "
        f"{PR26ControlMode.from_environment().value}; "
        "outermost boundary blocks startup/baseline R and all disallowed keys"
    )


__all__ = ["install_runtime_control_mode"]
