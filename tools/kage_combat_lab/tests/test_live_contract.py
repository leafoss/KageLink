from kage_combat_lab.domain import (
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
    R_KEYDOWN_HEARTBEAT_MS,
    START_RIGHT_PULSE_MS,
    START_RIGHT_SETTLE_MS,
    TURN_PRE_RELEASE_MS,
    TURN_PULSE_MS,
    TURN_SETTLE_MS,
)
from kage_combat_lab.live_contract import DEFAULT_LIVE_TEST_CONTRACT


def test_live_contract_protects_identity_and_explicit_facing_authority() -> None:
    contract = DEFAULT_LIVE_TEST_CONTRACT
    assert contract.target_mode == "single_trainer"
    assert contract.emergency_stop_key == EMERGENCY_STOP_KEY == "F12"
    assert contract.max_duration_seconds == FIRST_LIVE_TEST_MAX_SECONDS == 80.0
    assert contract.h_pulse_ms == H_PULSE_MS == 50
    assert contract.h_minimum_cooldown_seconds == H_COOLDOWN_SECONDS == 5.0
    assert contract.r_keydown_heartbeat_ms == R_KEYDOWN_HEARTBEAT_MS == 250
    assert contract.post_ok_settle_ms == POST_OK_SETTLE_MS == 300
    assert contract.startup_right_pulse_ms == START_RIGHT_PULSE_MS == 90
    assert contract.startup_right_settle_ms == START_RIGHT_SETTLE_MS == 120
    assert contract.turn_pre_release_ms == TURN_PRE_RELEASE_MS == 30
    assert contract.turn_pulse_ms == TURN_PULSE_MS == 80
    assert contract.turn_settle_ms == TURN_SETTLE_MS == 90
    assert contract.d0_deadzone_px == D0_DEADZONE_PX == 16.0
    assert contract.d0_side_switch_threshold_px == D0_SIDE_SWITCH_THRESHOLD_PX == 20.0
    assert contract.d0_side_switch_confirm_frames == D0_SIDE_SWITCH_CONFIRM_FRAMES == 2
    assert contract.occluded_coast_seconds == OCCLUDED_COAST_SECONDS == 0.45
    assert contract.local_reid_seconds == LOCAL_REID_SECONDS == 6.0
    assert contract.hard_lost_seconds == HARD_LOST_SECONDS == 6.0
    assert contract.require_clean_visual_for_h
    assert contract.require_post_ok_right_pulse
    assert contract.require_separate_turn_and_attack_frames
    assert contract.require_aligned_facing_for_r
    assert contract.require_aligned_facing_for_h
    assert not contract.require_fresh_cardinal_pulse_before_each_h
    assert contract.require_fresh_frame_confirmation_before_h
    assert contract.persistent_logical_target
    assert contract.target_capsule_enabled
    assert contract.negative_background_memory_enabled
    assert contract.event_video_enabled
    assert contract.player_facing_dataset_enabled
    assert contract.require_foreground_window
    assert contract.release_all_keys_on_exit
    assert contract.ignore_new_targets_after_ko
    assert contract.shadow_mode_seconds == 0.0
    assert contract.direct_input_enabled
