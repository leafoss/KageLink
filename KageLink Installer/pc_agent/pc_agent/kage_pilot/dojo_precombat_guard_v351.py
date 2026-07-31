from __future__ import annotations

import threading
from typing import Any, Callable

from . import dojo_fight_v03i as legacy_request
from .dojo_fight_v03e import (
    DojoFightRequestError,
    TrainerClickTarget,
    _close_owned_controller,
)
from .dojo_fight_v03i import DojoRoundWithoutCombatError


PRECOMBAT_GUARD_PULSE_SECONDS = 0.08
_REQUEST_PATCH_LOCK = threading.RLock()
_ROUND_BRIDGE_INSTALLED = False


class _GuardedRequestController:
    """Keep defensive R active after OK while the normal spawn timer runs."""

    def __init__(
        self,
        controller: Any,
        *,
        wait_fn: Callable[[float], None],
        pulse_seconds: float = PRECOMBAT_GUARD_PULSE_SECONDS,
    ) -> None:
        self._controller = controller
        self._wait_fn = wait_fn
        self._pulse_seconds = max(0.03, min(0.20, float(pulse_seconds)))
        self._guard_armed = False

    def __getattr__(self, name: str):
        return getattr(self._controller, name)

    @property
    def repeat_keys(self):
        return getattr(self._controller, "repeat_keys", set())

    @repeat_keys.setter
    def repeat_keys(self, value) -> None:
        setattr(self._controller, "repeat_keys", set(value or ()))

    def release_all(self) -> None:
        # The validated request provider deliberately releases inputs at every
        # dialog boundary. Once OK has been accepted, those releases must retain
        # defensive R until the spawn wait completes.
        if self._guard_armed:
            self._controller.apply_keys(("r",))
            return
        self._controller.release_all()

    def arm_after_ok(self) -> None:
        repeat_keys = {
            str(key).strip().lower()
            for key in getattr(self._controller, "repeat_keys", set())
            if str(key).strip()
        }
        repeat_keys.add("r")
        self._controller.repeat_keys = repeat_keys

        self._controller.apply_keys(("ctrl", "right"))
        print(
            "DOJO_PRECOMBAT_GUARD_PULSE keys=ctrl+right "
            f"duration={self._pulse_seconds:.3f}s count=1"
        )
        self._wait_fn(self._pulse_seconds)

        self._controller.apply_keys(("r",))
        self._guard_armed = True
        print("DOJO_PRECOMBAT_R_HOLD state=armed source=request")

    def finish(self) -> None:
        self._guard_armed = False
        self._controller.release_all()


def request_taijutsu_dojo_spar_single_click(
    game_title: str,
    *,
    dialog_delay_seconds: float = 5.0,
    dialog_find_timeout_seconds: float = 6.0,
    dialog_retries: int = 3,
    spawn_delay_seconds: float = 5.0,
    leader_threshold: float = 0.88,
    trainer_search_timeout_seconds: float = 90.0,
    interaction_attempts: int = 1,
    round_number: int | None = None,
    controller=None,
) -> TrainerClickTarget:
    """Run the validated request with one immediate defensive startup sequence.

    Exact order after the validated OK click:

    1. one Ctrl+Right Arrow pulse;
    2. begin BYOND repeat-held R;
    3. preserve R through the existing spawn timer;
    4. return to the unchanged isolated combat runtime.
    """

    from .pilot import WindowsGameController

    owns_controller = controller is None
    underlying = controller or WindowsGameController(recover_foreground=False)
    guarded = _GuardedRequestController(
        underlying,
        wait_fn=legacy_request._interruptible_wait,
    )

    with _REQUEST_PATCH_LOCK:
        original_click_ok = legacy_request.click_first_option_ok

        def guarded_click_ok(match) -> None:
            original_click_ok(match)
            guarded.arm_after_ok()

        legacy_request.click_first_option_ok = guarded_click_ok
        try:
            return legacy_request.request_taijutsu_dojo_spar_single_click(
                game_title,
                dialog_delay_seconds=dialog_delay_seconds,
                dialog_find_timeout_seconds=dialog_find_timeout_seconds,
                dialog_retries=dialog_retries,
                spawn_delay_seconds=spawn_delay_seconds,
                leader_threshold=leader_threshold,
                trainer_search_timeout_seconds=trainer_search_timeout_seconds,
                interaction_attempts=interaction_attempts,
                round_number=round_number,
                controller=guarded,
            )
        finally:
            legacy_request.click_first_option_ok = original_click_ok
            guarded.finish()
            if owns_controller:
                _close_owned_controller(underlying)


def install_round_precombat_r_hold(controller_type=None) -> None:
    """Hold repeat-R during the round process's existing startup delay.

    The base runtime calls ``activate()`` followed immediately by one defensive
    ``release_all()`` before sleeping. This bridge changes only that first release:
    it clears stale input and then starts repeat-held R. Every later release keeps
    its original semantics, including victory, F12, errors and post-combat.
    """

    global _ROUND_BRIDGE_INSTALLED

    if controller_type is None:
        if _ROUND_BRIDGE_INSTALLED:
            return
        from .pilot import WindowsGameController

        controller_type = WindowsGameController

    if bool(getattr(controller_type, "_kagelink_precombat_r_bridge", False)):
        if controller_type.__module__.startswith("pc_agent."):
            _ROUND_BRIDGE_INSTALLED = True
        return

    original_activate = controller_type.activate
    original_release_all = controller_type.release_all

    def guarded_activate(self, *args, **kwargs):
        result = original_activate(self, *args, **kwargs)
        self._dojo_precombat_first_release_pending = True
        return result

    def guarded_release_all(self, *args, **kwargs):
        if bool(getattr(self, "_dojo_precombat_first_release_pending", False)):
            self._dojo_precombat_first_release_pending = False
            result = original_release_all(self, *args, **kwargs)
            repeat_keys = {
                str(key).strip().lower()
                for key in getattr(self, "repeat_keys", set())
                if str(key).strip()
            }
            repeat_keys.add("r")
            self.repeat_keys = repeat_keys
            self.apply_keys(("r",))
            print("DOJO_PRECOMBAT_R_HOLD state=armed source=round_startup")
            return result
        return original_release_all(self, *args, **kwargs)

    controller_type.activate = guarded_activate
    controller_type.release_all = guarded_release_all
    controller_type._kagelink_precombat_r_bridge = True

    if controller_type.__module__.startswith("pc_agent."):
        _ROUND_BRIDGE_INSTALLED = True
        print("DOJO_PRECOMBAT_R_BRIDGE_INSTALLED")


__all__ = [
    "DojoFightRequestError",
    "DojoRoundWithoutCombatError",
    "PRECOMBAT_GUARD_PULSE_SECONDS",
    "TrainerClickTarget",
    "install_round_precombat_r_hold",
    "request_taijutsu_dojo_spar_single_click",
]
