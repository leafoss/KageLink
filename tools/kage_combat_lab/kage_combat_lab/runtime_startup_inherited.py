from __future__ import annotations

import os
import time


def install_inherited_post_ok_startup() -> None:
    """Inherit startup facing only when FULL_COMBAT actually sent the pulse."""

    from . import live_bridge as live_module
    from .runtime_facing_patch import _CONTEXT

    physical_class = live_module.PhysicalCombatInput

    def start_combat_hold(self) -> None:
        self.controller.release_all()
        mode = os.environ.get("KAGE_PR26_CONTROL_MODE", "FULL_COMBAT").strip().upper()
        if mode != "FULL_COMBAT":
            _CONTEXT.startup_done = False
            _CONTEXT.startup_actions = (
                f"STARTUP_RIGHT_PULSE_BLOCKED_{mode}",
            )
            print(
                "STARTUP_RIGHT_PULSE inherited=false duplicate=false "
                f"blocked=true mode={mode} facing_source=UNKNOWN"
            )
            return

        # The real RIGHT pulse already happened in the outer request process,
        # immediately after OK/refocus and before baseline capture. The child
        # must never send a duplicate pulse or start holding R during SEARCH.
        _CONTEXT.authority.register_startup_right(now=time.monotonic())
        _CONTEXT.startup_done = True
        _CONTEXT.startup_actions = ("STARTUP_RIGHT_PULSE_INHERITED_POST_OK",)
        print(
            "STARTUP_RIGHT_PULSE inherited=true duplicate=false "
            "commanded_facing=RIGHT facing_source=STARTUP_RIGHT_PULSE"
        )

    physical_class.start_combat_hold = start_combat_hold


__all__ = ["install_inherited_post_ok_startup"]
