from __future__ import annotations

from dataclasses import dataclass

from .domain import (
    EMERGENCY_STOP_KEY,
    FIRST_LIVE_TEST_MAX_SECONDS,
    HARD_LOST_SECONDS,
    H_COOLDOWN_SECONDS,
    H_PULSE_MS,
    POST_PULSE_OBSERVE_MS,
    R_KEYDOWN_HEARTBEAT_MS,
)


@dataclass(frozen=True, slots=True)
class LiveTestContract:
    """Conservative defaults for the first real combat integration."""

    window_title: str = "Shinobi Story Online"
    target_mode: str = "single_trainer"
    emergency_stop_key: str = EMERGENCY_STOP_KEY
    max_duration_seconds: float = FIRST_LIVE_TEST_MAX_SECONDS
    h_pulse_ms: int = H_PULSE_MS
    h_minimum_cooldown_seconds: float = H_COOLDOWN_SECONDS
    r_keydown_heartbeat_ms: int = R_KEYDOWN_HEARTBEAT_MS
    post_action_observe_ms: int = POST_PULSE_OBSERVE_MS
    hard_lost_seconds: float = HARD_LOST_SECONDS
    require_foreground_window: bool = True
    require_clean_visual_for_h: bool = True
    release_all_keys_on_exit: bool = True
    ignore_new_targets_after_ko: bool = True
    first_test_shadow_seconds: float = 10.0


DEFAULT_LIVE_TEST_CONTRACT = LiveTestContract()


def checklist_lines() -> tuple[str, ...]:
    c = DEFAULT_LIVE_TEST_CONTRACT
    return (
        "FIRST LIVE COMBAT CONTRACT",
        f"Window: {c.window_title}",
        f"Target mode: {c.target_mode}",
        f"Shadow validation before input: {c.first_test_shadow_seconds:.0f}s",
        f"Maximum armed duration: {c.max_duration_seconds:.0f}s",
        f"Emergency stop: {c.emergency_stop_key}",
        f"H: {c.h_pulse_ms}ms tap, minimum cooldown {c.h_minimum_cooldown_seconds:.1f}s",
        f"R: repeated key-down heartbeat every {c.r_keydown_heartbeat_ms}ms",
        f"Observe after each action: {c.post_action_observe_ms}ms",
        f"Hard lost timeout: {c.hard_lost_seconds:.1f}s",
        "H requires a clean target in the current frame and a cardinal aim direction.",
        "The first live test is single-target Trainer only.",
        "All keys must be released on KO, F12, timeout, focus loss, or process exit.",
        "This checklist does not itself send keyboard input.",
    )
