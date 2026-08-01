from __future__ import annotations

from dataclasses import dataclass

from .domain import (
    AIM_SETTLE_MS,
    EMERGENCY_STOP_KEY,
    FIRST_LIVE_TEST_MAX_SECONDS,
    HARD_LOST_SECONDS,
    H_COOLDOWN_SECONDS,
    H_PULSE_MS,
    LOCAL_REID_SECONDS,
    OCCLUDED_COAST_SECONDS,
    POST_PULSE_OBSERVE_MS,
    R_KEYDOWN_HEARTBEAT_MS,
)


@dataclass(frozen=True, slots=True)
class LiveTestContract:
    """Direct-input defaults for the real combat integration."""

    window_title: str = "Shinobi Story Online"
    target_mode: str = "single_trainer"
    emergency_stop_key: str = EMERGENCY_STOP_KEY
    max_duration_seconds: float = FIRST_LIVE_TEST_MAX_SECONDS
    h_pulse_ms: int = H_PULSE_MS
    h_minimum_cooldown_seconds: float = H_COOLDOWN_SECONDS
    r_keydown_heartbeat_ms: int = R_KEYDOWN_HEARTBEAT_MS
    post_action_observe_ms: int = POST_PULSE_OBSERVE_MS
    aim_settle_ms: int = AIM_SETTLE_MS
    occluded_coast_seconds: float = OCCLUDED_COAST_SECONDS
    local_reid_seconds: float = LOCAL_REID_SECONDS
    hard_lost_seconds: float = HARD_LOST_SECONDS
    require_foreground_window: bool = True
    require_clean_visual_for_h: bool = True
    require_fresh_cardinal_pulse_before_each_h: bool = True
    require_fresh_frame_confirmation_before_h: bool = True
    persistent_logical_target: bool = True
    target_capsule_enabled: bool = True
    negative_background_memory_enabled: bool = True
    event_video_enabled: bool = True
    release_all_keys_on_exit: bool = True
    ignore_new_targets_after_ko: bool = True
    shadow_mode_seconds: float = 0.0
    startup_countdown_seconds: float = 3.0
    direct_input_enabled: bool = True


DEFAULT_LIVE_TEST_CONTRACT = LiveTestContract()


def checklist_lines() -> tuple[str, ...]:
    c = DEFAULT_LIVE_TEST_CONTRACT
    return (
        "LIVE COMBAT CONTRACT",
        f"Window: {c.window_title}",
        f"Target mode: {c.target_mode}",
        "Shadow mode: DISABLED by explicit user decision",
        f"Direct input startup countdown: {c.startup_countdown_seconds:.0f}s",
        f"Maximum armed duration: {c.max_duration_seconds:.0f}s",
        f"Emergency stop: {c.emergency_stop_key}",
        f"H: {c.h_pulse_ms}ms tap, minimum cooldown {c.h_minimum_cooldown_seconds:.1f}s",
        (
            "H sequence: directional pulse -> "
            f"fresh capture after {c.aim_settle_ms}ms -> correction if needed -> H"
        ),
        "A failed aim confirmation does not consume the H cooldown.",
        f"R: repeated key-down heartbeat every {c.r_keydown_heartbeat_ms}ms",
        f"Observe after each action: {c.post_action_observe_ms}ms",
        f"Occluded coast: {c.occluded_coast_seconds:.2f}s, microchase only, no H",
        f"Local visual ReID: up to {c.local_reid_seconds:.1f}s",
        f"Hard lost timeout: {c.hard_lost_seconds:.1f}s",
        "Target identity uses a temporary per-round sprite capsule.",
        "Stable rejected regions become negative background evidence.",
        "Critical target/aim events save 5s-before/5s-after video clips.",
        "All keys are released on KO, F12, timeout, focus loss, exception, or process exit.",
        "Use -LiveInput to send real keyboard input.",
    )
