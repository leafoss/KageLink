from __future__ import annotations

import time

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


def request_taijutsu_dojo_spar_single_click(
    game_title: str,
    *,
    dialog_delay_seconds: float = 5.0,
    dialog_find_timeout_seconds: float = 6.0,
    spawn_delay_seconds: float = 5.0,
    leader_threshold: float = 0.88,
    trainer_search_timeout_seconds: float = 90.0,
    interaction_attempts: int = 1,
    controller=None,
) -> TrainerClickTarget:
    """Find the trainer, click exactly once, then wait for and confirm the Dojo dialog.

    ``interaction_attempts`` remains in the signature for CLI compatibility, but is deliberately
    ignored. A missing dialog is a safe failure; it never authorizes a second trainer click.
    """

    del interaction_attempts

    from .pilot import WindowsGameController
    from pc_agent.windows import ensure_game_window_foreground

    owns_controller = controller is None
    controller = controller or WindowsGameController(recover_foreground=False)
    controller.repeat_keys = set()

    try:
        controller.activate()
        controller.release_all()

        target = search_trainer_until_visible(
            controller,
            timeout_seconds=trainer_search_timeout_seconds,
            leader_threshold=leader_threshold,
        )

        controller.release_all()
        clicked_at = time.monotonic()
        controller.click_normalized(target.normalized_x, target.normalized_y)
        controller.release_all()
        print(
            f"TRAINER_CLICK_ONCE score={target.score:.3f} d={target.grid_distance} "
            f"/ CLIQUE_UNICO_NO_TREINADOR"
        )

        # One click only. If the dialog does not appear, stop safely rather than clicking again.
        dialog = wait_for_dojo_dialog_with_ok(
            game_title,
            timeout_seconds=max(0.5, float(dialog_find_timeout_seconds)),
        )

        elapsed = time.monotonic() - clicked_at
        _interruptible_wait(max(0.0, float(dialog_delay_seconds) - elapsed))

        refreshed = find_dojo_dialog_with_ok(game_title)
        click_first_option_ok(refreshed or dialog)

        focus = ensure_game_window_foreground(game_title)
        if not focus.ok:
            raise DojoFightRequestError(focus.error or "GAME_REFOCUS_FAILED")

        _interruptible_wait(spawn_delay_seconds)
        return target
    finally:
        controller.release_all()
        if owns_controller:
            _close_owned_controller(controller)


__all__ = ["request_taijutsu_dojo_spar_single_click"]
