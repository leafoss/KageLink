from __future__ import annotations

from dataclasses import dataclass

from .domain import (
    D0_DEADZONE_PX,
    D0_SIDE_SWITCH_CONFIRM_FRAMES,
    D0_SIDE_SWITCH_THRESHOLD_PX,
    EMERGENCY_STOP_KEY,
    FIRST_LIVE_TEST_MAX_SECONDS,
    HARD_LOST_SECONDS,
    H_COOLDOWN_SECONDS,
    H_PULSE_MS,
    LOCAL_REID_SECONDS,
    OCCLUDED_COAST_SECONDS,
    POST_OK_SETTLE_MS,
    POST_PULSE_OBSERVE_MS,
    R_KEYDOWN_HEARTBEAT_MS,
    START_RIGHT_PULSE_MS,
    START_RIGHT_SETTLE_MS,
    TURN_PRE_RELEASE_MS,
    TURN_PULSE_MS,
    TURN_SETTLE_MS,
)


@dataclass(frozen=True, slots=True)
class LiveTestContract:
    """Direct-input defaults for explicit target and facing authority."""

    window_title: str = "Shinobi Story Online"
    target_mode: str = "single_trainer"
    emergency_stop_key: str = EMERGENCY_STOP_KEY
    max_duration_seconds: float = FIRST_LIVE_TEST_MAX_SECONDS
    h_pulse_ms: int = H_PULSE_MS
    h_minimum_cooldown_seconds: float = H_COOLDOWN_SECONDS
    r_keydown_heartbeat_ms: int = R_KEYDOWN_HEARTBEAT_MS
    post_action_observe_ms: int = POST_PULSE_OBSERVE_MS
    post_ok_settle_ms: int = POST_OK_SETTLE_MS
    startup_right_pulse_ms: int = START_RIGHT_PULSE_MS
    startup_right_settle_ms: int = START_RIGHT_SETTLE_MS
    turn_pre_release_ms: int = TURN_PRE_RELEASE_MS
    turn_pulse_ms: int = TURN_PULSE_MS
    turn_settle_ms: int = TURN_SETTLE_MS
    d0_deadzone_px: float = D0_DEADZONE_PX
    d0_side_switch_threshold_px: float = D0_SIDE_SWITCH_THRESHOLD_PX
    d0_side_switch_confirm_frames: int = D0_SIDE_SWITCH_CONFIRM_FRAMES
    occluded_coast_seconds: float = OCCLUDED_COAST_SECONDS
    local_reid_seconds: float = LOCAL_REID_SECONDS
    hard_lost_seconds: float = HARD_LOST_SECONDS
    require_foreground_window: bool = True
    require_clean_visual_for_h: bool = True
    require_post_ok_right_pulse: bool = True
    require_separate_turn_and_attack_frames: bool = True
    require_aligned_facing_for_r: bool = True
    require_aligned_facing_for_h: bool = True
    require_fresh_cardinal_pulse_before_each_h: bool = False
    require_fresh_frame_confirmation_before_h: bool = True
    persistent_logical_target: bool = True
    target_capsule_enabled: bool = True
    negative_background_memory_enabled: bool = True
    event_video_enabled: bool = True
    player_facing_dataset_enabled: bool = True
    release_all_keys_on_exit: bool = True
    ignore_new_targets_after_ko: bool = True
    shadow_mode_seconds: float = 0.0
    startup_countdown_seconds: float = 3.0
    direct_input_enabled: bool = True


DEFAULT_LIVE_TEST_CONTRACT = LiveTestContract()


def checklist_lines() -> tuple[str, ...]:
    c = DEFAULT_LIVE_TEST_CONTRACT
    return (
        "LIVE COMBAT CONTRACT — EXPLICIT FACING AUTHORITY",
        f"Window: {c.window_title}",
        f"Target mode: {c.target_mode}",
        "Shadow mode: DISABLED by explicit user decision",
        f"Maximum armed duration: {c.max_duration_seconds:.0f}s",
        f"Emergency stop: {c.emergency_stop_key}",
        (
            "Post-OK startup: release all -> "
            f"wait {c.post_ok_settle_ms}ms -> RIGHT {c.startup_right_pulse_ms}ms -> "
            f"settle {c.startup_right_settle_ms}ms"
        ),
        (
            "Exclusive turn: R off -> "
            f"wait {c.turn_pre_release_ms}ms -> direction {c.turn_pulse_ms}ms -> "
            f"settle {c.turn_settle_ms}ms -> confirm on next frame"
        ),
        "Turning and H never occur in the same frame.",
        "SEARCH, ATTENTION, OCCLUDED_COAST, REID_LOCAL and TURN_ALIGN keep R/H off.",
        "R and H require visible logical target plus confirmed facing equal to stable bearing.",
        f"H: {c.h_pulse_ms}ms tap, minimum cooldown {c.h_minimum_cooldown_seconds:.1f}s",
        "A blocked or failed turn does not consume the H cooldown.",
        f"R heartbeat when authorized: every {c.r_keydown_heartbeat_ms}ms",
        (
            f"D0 Contact Lock: deadzone {c.d0_deadzone_px:.0f}px; side switch requires "
            f">={c.d0_side_switch_threshold_px:.0f}px for "
            f"{c.d0_side_switch_confirm_frames} frames"
        ),
        f"Occluded coast: {c.occluded_coast_seconds:.2f}s with R/H off",
        f"Local visual ReID: up to {c.local_reid_seconds:.1f}s",
        f"Hard lost timeout: {c.hard_lost_seconds:.1f}s",
        "Target identity uses a temporary per-round sprite capsule.",
        "Stable rejected regions become negative background evidence.",
        "Trusted exclusive turns collect 64px player-facing crops for a future classifier.",
        "Critical target/facing events save 5s-before/5s-after video clips.",
        "All keys are released on KO, F12, timeout, focus loss, exception, or process exit.",
    )
