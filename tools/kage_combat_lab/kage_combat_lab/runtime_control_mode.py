from __future__ import annotations

from .occupancy_tracking import PR26ControlMode


_INSTALLED = False


def install_runtime_control_mode() -> None:
    """Enforce PR26.3 safety modes at the final physical-input boundary."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import live_bridge as live_module

    CurrentPhysical = live_module.PhysicalCombatInput

    class PR26ModePhysicalCombatInput(CurrentPhysical):
        def execute(self, decision, *, confirm_aim=None):
            mode = PR26ControlMode.from_environment()
            if mode is PR26ControlMode.PERCEPTION_ONLY:
                self.controller.release_all()
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
                    return super().execute(decision, confirm_aim=confirm_aim)
                self.controller.release_all()
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
        "PERCEPTION_ONLY blocks TURN/MOVE/R/H, FACE_ONLY allows TURN only"
    )


__all__ = ["install_runtime_control_mode"]
