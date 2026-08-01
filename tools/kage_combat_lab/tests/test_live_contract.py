from kage_combat_lab.domain import (
    EMERGENCY_STOP_KEY,
    FIRST_LIVE_TEST_MAX_SECONDS,
    HARD_LOST_SECONDS,
    H_COOLDOWN_SECONDS,
    H_PULSE_MS,
    R_KEYDOWN_HEARTBEAT_MS,
)
from kage_combat_lab.live_contract import DEFAULT_LIVE_TEST_CONTRACT


def test_first_live_test_contract_arms_direct_input_safely() -> None:
    contract = DEFAULT_LIVE_TEST_CONTRACT
    assert contract.target_mode == "single_trainer"
    assert contract.emergency_stop_key == EMERGENCY_STOP_KEY == "F12"
    assert contract.max_duration_seconds == FIRST_LIVE_TEST_MAX_SECONDS == 80.0
    assert contract.h_pulse_ms == H_PULSE_MS == 50
    assert contract.h_minimum_cooldown_seconds == H_COOLDOWN_SECONDS == 5.0
    assert contract.r_keydown_heartbeat_ms == R_KEYDOWN_HEARTBEAT_MS == 250
    assert contract.hard_lost_seconds == HARD_LOST_SECONDS == 2.0
    assert contract.require_clean_visual_for_h
    assert contract.require_foreground_window
    assert contract.release_all_keys_on_exit
    assert contract.ignore_new_targets_after_ko
    assert contract.shadow_mode_seconds == 0.0
    assert contract.startup_countdown_seconds == 3.0
    assert contract.direct_input_enabled
