from __future__ import annotations

import os
from typing import Callable

from .domain import POST_OK_SETTLE_MS, START_RIGHT_PULSE_MS, START_RIGHT_SETTLE_MS

_INSTALLED = False


def control_mode_allows_post_ok_pulse() -> bool:
    """Only FULL_COMBAT may preserve PR25's external startup orientation pulse."""

    mode = os.environ.get("KAGE_PR26_CONTROL_MODE", "FULL_COMBAT").strip().upper()
    return mode == "FULL_COMBAT"


def perform_post_ok_right_pulse(
    controller,
    *,
    sleep_fn: Callable[[float], None],
    post_ok_settle_ms: int = POST_OK_SETTLE_MS,
    pulse_ms: int = START_RIGHT_PULSE_MS,
    settle_ms: int = START_RIGHT_SETTLE_MS,
) -> tuple[str, ...]:
    """Face RIGHT once, exclusively, after OK and before the spawn wait."""

    actions: list[str] = []
    controller.repeat_keys = set()
    controller.activate()
    controller.release_all()
    try:
        sleep_fn(max(0.0, float(post_ok_settle_ms) / 1000.0))
        actions.append(f"POST_OK_SETTLE_{int(post_ok_settle_ms)}MS")
        controller.apply_keys(("right",))
        sleep_fn(max(0.01, float(pulse_ms) / 1000.0))
        actions.append(f"STARTUP_RIGHT_PULSE_{int(pulse_ms)}MS")
    finally:
        controller.release_all()
    sleep_fn(max(0.0, float(settle_ms) / 1000.0))
    controller.release_all()
    actions.append(f"STARTUP_RIGHT_SETTLE_{int(settle_ms)}MS")
    return tuple(actions)


def install_post_ok_right_pulse() -> None:
    """Install one optional pulse after dialog OK/refocus and before baseline."""

    global _INSTALLED
    if _INSTALLED:
        return

    from pc_agent import windows as windows_module
    from pc_agent.kage_pilot import dojo_fight_v03i as request_module
    from pc_agent.kage_pilot.dojo_fight_v03e import (
        _close_owned_controller,
        _interruptible_wait,
    )
    from pc_agent.kage_pilot.pilot import WindowsGameController

    original_click_ok = request_module.click_first_option_ok
    original_focus = windows_module.ensure_game_window_foreground
    state = {"armed": False, "executed": 0, "blocked": 0}

    def click_ok_and_arm(*args, **kwargs):
        result = original_click_ok(*args, **kwargs)
        state["armed"] = True
        return result

    def focus_and_face_right(*args, **kwargs):
        result = original_focus(*args, **kwargs)
        if not bool(getattr(result, "ok", False)) or not state["armed"]:
            return result

        # Consume before input so exceptions/F12 can never cause a duplicate pulse.
        state["armed"] = False
        if not control_mode_allows_post_ok_pulse():
            state["blocked"] += 1
            mode = os.environ.get("KAGE_PR26_CONTROL_MODE", "PERCEPTION_ONLY").strip().upper()
            print(
                "STARTUP_RIGHT_PULSE blocked=true post_ok=true before_spawn=true "
                f"mode={mode} count={state['blocked']} reason=PR26_VALIDATION_MODE"
            )
            return result

        controller = WindowsGameController(recover_foreground=False)
        try:
            actions = perform_post_ok_right_pulse(
                controller,
                sleep_fn=_interruptible_wait,
            )
            state["executed"] += 1
            print(
                "STARTUP_RIGHT_PULSE post_ok=true before_spawn=true "
                f"count={state['executed']} actions={','.join(actions)}"
            )
        finally:
            try:
                controller.release_all()
            finally:
                _close_owned_controller(controller)
        return result

    request_module.click_first_option_ok = click_ok_and_arm
    windows_module.ensure_game_window_foreground = focus_and_face_right
    _INSTALLED = True


__all__ = [
    "control_mode_allows_post_ok_pulse",
    "install_post_ok_right_pulse",
    "perform_post_ok_right_pulse",
]
