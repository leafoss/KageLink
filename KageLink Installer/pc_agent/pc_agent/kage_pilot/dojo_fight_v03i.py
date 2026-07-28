from __future__ import annotations

from .dojo_fight_v03e import (
    DojoFightRequestError,
    TrainerClickTarget,
    _close_owned_controller,
    _interruptible_wait,
)
from .dojo_fight_v03f import (
    click_first_option_ok,
    find_dojo_dialog_with_ok,
    search_trainer_until_visible,
    wait_for_dojo_dialog_with_ok,
)


class DojoRoundWithoutCombatError(DojoFightRequestError):
    """Recoverable request failure that consumes one round without starting combat."""

    def __init__(
        self,
        reason: str,
        *,
        trainer_clicks: int,
        dialog_attempts: int,
    ) -> None:
        self.reason = str(reason or "UNEXPECTED_ERROR")
        self.trainer_clicks = max(0, int(trainer_clicks))
        self.dialog_attempts = max(0, int(dialog_attempts))
        super().__init__(self.reason)


def _round_prefix(round_number: int | None) -> str:
    if round_number is None:
        return ""
    return f"ROUND {max(1, int(round_number))}: "


def _error_code(error: BaseException) -> str:
    return str(error).split(":", 1)[0].strip() or type(error).__name__


def _current_validated_dialog(game_title: str):
    """Re-enumerate the dialog immediately before BM_CLICK.

    ``find_dojo_dialog_with_ok`` validates game process ownership, #32770 identity,
    ListBox geometry/count and the visible enabled OK control. Returning the fresh
    match prevents reuse of stale HWNDs or old coordinates.
    """

    from pc_agent.game_window import find_exact_game_window

    if find_exact_game_window(game_title) is None:
        raise DojoFightRequestError("GAME_WINDOW_NOT_AVAILABLE")
    match = find_dojo_dialog_with_ok(game_title)
    if match is None:
        raise DojoFightRequestError("DOJO_DIALOG_INVALID:REVALIDATION_FAILED")
    return match


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
    """Click the trainer once, then retry only the already-requested dialog gate.

    There is one initial wait/check plus ``dialog_retries`` additional wait/checks.
    No path after ``TRAINER_CLICK_ONCE`` may move, search for or click the trainer again.
    """

    del interaction_attempts

    from .pilot import WindowsGameController
    from pc_agent.windows import ensure_game_window_foreground

    owns_controller = controller is None
    controller = controller or WindowsGameController(recover_foreground=False)
    controller.repeat_keys = set()
    prefix = _round_prefix(round_number)
    retry_count = max(0, min(10, int(dialog_retries)))
    total_checks = 1 + retry_count
    delay = max(0.0, float(dialog_delay_seconds))
    find_timeout = max(0.5, float(dialog_find_timeout_seconds))

    try:
        controller.activate()
        controller.release_all()

        target = search_trainer_until_visible(
            controller,
            timeout_seconds=trainer_search_timeout_seconds,
            leader_threshold=leader_threshold,
        )

        controller.release_all()
        try:
            controller.click_normalized(target.normalized_x, target.normalized_y)
        except Exception as error:
            controller.release_all()
            raise DojoRoundWithoutCombatError(
                "TRAINER_CLICK_FAILED",
                trainer_clicks=1,
                dialog_attempts=0,
            ) from error
        controller.release_all()
        print(
            f"{prefix}TRAINER_CLICK_ONCE score={target.score:.3f} d={target.grid_distance} "
            f"/ CLIQUE_UNICO_NO_TREINADOR"
        )

        last_reason = "DOJO_DIALOG_NOT_FOUND"
        checks_performed = 0
        for attempt in range(1, total_checks + 1):
            wait_marker = "DOJO_DIALOG_WAIT" if attempt == 1 else "DOJO_DIALOG_RETRY_WAIT"
            print(
                f"{prefix}{wait_marker} attempt={attempt}/{total_checks} delay={delay:.1f}"
            )
            controller.release_all()
            _interruptible_wait(delay)
            controller.release_all()
            checks_performed = attempt

            try:
                dialog = wait_for_dojo_dialog_with_ok(
                    game_title,
                    timeout_seconds=find_timeout,
                )
            except DojoFightRequestError as error:
                code = _error_code(error)
                if code == "F12_STOP":
                    raise
                if code == "DOJO_DIALOG_NOT_FOUND":
                    last_reason = code
                    print(
                        f"{prefix}DOJO_DIALOG_NOT_FOUND attempt={attempt}/{total_checks}"
                    )
                    continue
                raise

            try:
                refreshed = _current_validated_dialog(game_title)
            except DojoFightRequestError as error:
                code = _error_code(error)
                if code == "F12_STOP":
                    raise
                if code == "GAME_WINDOW_NOT_AVAILABLE":
                    raise
                last_reason = "DOJO_DIALOG_INVALID"
                print(
                    f"{prefix}DOJO_DIALOG_INVALID attempt={attempt}/{total_checks} "
                    f"detail={code}"
                )
                continue

            print(
                f"{prefix}DOJO_DIALOG_CONFIRMED attempt={attempt}/{total_checks} "
                f"hwnd={refreshed.dialog_hwnd}"
            )
            try:
                click_first_option_ok(refreshed)
            except DojoFightRequestError as error:
                code = _error_code(error)
                if code == "F12_STOP":
                    raise
                last_reason = "DIALOG_OK_CLICK_FAILED"
                print(
                    f"{prefix}DIALOG_OK_CLICK_FAILED attempt={attempt}/{total_checks} "
                    f"detail={code}"
                )
                continue

            controller.release_all()
            print(
                f"{prefix}DOJO_DIALOG_OK_CLICKED attempt={attempt}/{total_checks} "
                f"hwnd={refreshed.dialog_hwnd}"
            )
            print(
                f"{prefix}DOJO_REQUEST_OK trainer_clicks=1 dialog_attempts={attempt}"
            )

            focus = ensure_game_window_foreground(game_title)
            if not focus.ok:
                raise DojoFightRequestError(focus.error or "GAME_REFOCUS_FAILED")

            spawn_delay = max(0.0, float(spawn_delay_seconds))
            print(f"{prefix}WAITING_FOR_SPAWN delay={spawn_delay:.1f}")
            controller.release_all()
            _interruptible_wait(spawn_delay)
            controller.release_all()
            return target

        controller.release_all()
        raise DojoRoundWithoutCombatError(
            last_reason,
            trainer_clicks=1,
            dialog_attempts=checks_performed,
        )
    finally:
        controller.release_all()
        if owns_controller:
            _close_owned_controller(controller)


__all__ = [
    "DojoRoundWithoutCombatError",
    "request_taijutsu_dojo_spar_single_click",
]
