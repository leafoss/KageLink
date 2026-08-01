from __future__ import annotations

import time


def install_inherited_post_ok_startup() -> None:
    """Make the child inherit the already-completed outer post-OK RIGHT pulse."""

    from . import live_bridge as live_module
    from .runtime_facing_patch import _CONTEXT

    physical_class = live_module.PhysicalCombatInput

    def start_combat_hold(self) -> None:
        # The real RIGHT pulse already happened in the outer request process,
        # immediately after OK/refocus and before WAITING_FOR_SPAWN. The child
        # must never send a duplicate pulse or start holding R during SEARCH.
        self.controller.release_all()
        _CONTEXT.authority.register_startup_right(now=time.monotonic())
        _CONTEXT.startup_done = True
        _CONTEXT.startup_actions = ("STARTUP_RIGHT_PULSE_INHERITED_POST_OK",)
        print(
            "STARTUP_RIGHT_PULSE inherited=true duplicate=false "
            "commanded_facing=RIGHT facing_source=STARTUP_RIGHT_PULSE"
        )

    physical_class.start_combat_hold = start_combat_hold


__all__ = ["install_inherited_post_ok_startup"]
