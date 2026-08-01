import pytest

from kage_combat_lab.domain import (
    APPROACH_PULSE_MS,
    H_COOLDOWN_SECONDS,
    H_PULSE_MS,
    R_KEYDOWN_HEARTBEAT_MS,
    VERY_SHORT_PULSE_MS,
    CandidateObservation,
    CombatFrame,
    GridCell,
    MovementPulseProfile,
    ObservationKind,
    TargetState,
)
from kage_combat_lab.strategy import GridFocusStrategy


def clean(track: int, cell: GridCell, *, face_hint: str | None = None) -> CandidateObservation:
    return CandidateObservation(track, cell, ObservationKind.CLEAN_BODY, face_hint=face_hint)


def lock_at(cell: GridCell, *, face_hint: str | None = None):
    strategy = GridFocusStrategy()
    player = GridCell(0, 0)
    strategy.update(
        CombatFrame.from_iterable(
            0, player, [clean(1, cell, face_hint=face_hint)], timestamp_seconds=0.0
        )
    )
    decision = strategy.update(
        CombatFrame.from_iterable(
            1, player, [clean(1, cell, face_hint=face_hint)], timestamp_seconds=0.5
        )
    )
    return strategy, player, decision


def test_r_is_held_with_repeated_keydown_heartbeat_during_combat() -> None:
    _, _, decision = lock_at(GridCell(2, 0))
    assert decision.hold_r
    assert decision.r_keydown_heartbeat_ms == R_KEYDOWN_HEARTBEAT_MS


def test_d0_micro_chases_and_fires_h_with_fresh_direction() -> None:
    _, _, decision = lock_at(GridCell(0, 0), face_hint="LEFT")
    assert decision.grid_distance == 0
    assert decision.face == "LEFT"
    assert decision.move == "left"
    assert decision.move_pulse_profile is MovementPulseProfile.VERY_SHORT
    assert decision.move_pulse_ms == VERY_SHORT_PULSE_MS == 50
    assert decision.press_h
    assert decision.h_pulse_ms == H_PULSE_MS == 50
    assert decision.action_sequence.index("AIM_CURRENT_LEFT_50MS") < decision.action_sequence.index(
        "H_TAP_50MS"
    )
    assert decision.action_sequence.index("H_TAP_50MS") < decision.action_sequence.index(
        "CHASE_LEFT_50MS"
    )


def test_d0_without_current_visual_direction_holds_fail_closed() -> None:
    _, _, decision = lock_at(GridCell(0, 0))
    assert decision.grid_distance == 0
    assert decision.face is None
    assert decision.move is None
    assert decision.move_pulse_profile is None
    assert not decision.press_h


def test_d1_chases_toward_d0_and_fires_h() -> None:
    _, _, decision = lock_at(GridCell(1, 0))
    assert decision.grid_distance == 1
    assert decision.face == "RIGHT"
    assert decision.move == "right"
    assert decision.move_pulse_profile is MovementPulseProfile.APPROACH
    assert decision.move_pulse_ms == APPROACH_PULSE_MS == 100
    assert decision.press_h
    assert decision.action_sequence.index("AIM_CURRENT_RIGHT_50MS") < decision.action_sequence.index(
        "H_TAP_50MS"
    )
    assert decision.action_sequence.index("H_TAP_50MS") < decision.action_sequence.index(
        "CHASE_RIGHT_100MS"
    )


def test_h_cooldown_never_stops_d1_chase() -> None:
    strategy, player, first = lock_at(GridCell(1, 0))
    assert first.press_h
    blocked = strategy.update(
        CombatFrame.from_iterable(
            2, player, [clean(1, GridCell(1, 0))], timestamp_seconds=1.0
        )
    )
    assert not blocked.press_h
    assert blocked.move == "right"
    assert blocked.move_pulse_profile is MovementPulseProfile.APPROACH
    assert blocked.move_pulse_ms == APPROACH_PULSE_MS


def test_d2_no_longer_holds_and_chases_toward_d0() -> None:
    _, _, decision = lock_at(GridCell(2, 0))
    assert decision.grid_distance == 2
    assert decision.move == "right"
    assert decision.move_pulse_profile is MovementPulseProfile.APPROACH
    assert decision.move_pulse_ms == APPROACH_PULSE_MS
    assert decision.press_h
    assert decision.h_pulse_ms == H_PULSE_MS == 50
    assert decision.face == "RIGHT"


def test_h_cooldown_is_never_shorter_than_five_seconds() -> None:
    strategy = GridFocusStrategy(h_cooldown_seconds=1.0)
    assert strategy.h_cooldown_seconds == H_COOLDOWN_SECONDS == 5.0


def test_h_cooldown_blocks_only_h_until_five_seconds() -> None:
    strategy, player, first_h = lock_at(GridCell(2, 0))
    blocked = strategy.update(
        CombatFrame.from_iterable(
            2, player, [clean(1, GridCell(2, 0))], timestamp_seconds=4.99
        )
    )
    ready = strategy.update(
        CombatFrame.from_iterable(
            3, player, [clean(1, GridCell(2, 0))], timestamp_seconds=5.50
        )
    )
    assert first_h.press_h
    assert not blocked.press_h
    assert blocked.h_cooldown_remaining_seconds > 0
    assert blocked.move == "right"
    assert blocked.move_pulse_profile is MovementPulseProfile.APPROACH
    assert ready.press_h
    assert ready.move == "right"
    assert ready.h_cooldown_remaining_seconds == H_COOLDOWN_SECONDS


def test_target_below_replaces_old_right_aim_and_chase_with_down() -> None:
    strategy, player, first = lock_at(GridCell(1, 0))
    assert first.face == "RIGHT"
    assert first.move == "right"
    assert first.press_h

    moved_below = strategy.update(
        CombatFrame.from_iterable(
            2, player, [clean(1, GridCell(0, 1))], timestamp_seconds=1.0
        )
    )
    assert moved_below.face == "DOWN"
    assert not moved_below.press_h
    assert moved_below.move == "down"
    assert moved_below.move_pulse_profile is MovementPulseProfile.APPROACH

    ready_below = strategy.update(
        CombatFrame.from_iterable(
            3, player, [clean(1, GridCell(0, 1))], timestamp_seconds=5.50
        )
    )
    assert ready_below.face == "DOWN"
    assert ready_below.press_h
    assert ready_below.move == "down"
    assert ready_below.action_sequence.index("AIM_CURRENT_DOWN_50MS") < ready_below.action_sequence.index(
        "H_TAP_50MS"
    )
    assert ready_below.action_sequence.index("H_TAP_50MS") < ready_below.action_sequence.index(
        "CHASE_DOWN_100MS"
    )


def test_push_from_d0_to_d1_immediately_escalates_to_approach_chase() -> None:
    strategy, player, first = lock_at(GridCell(0, 0), face_hint="DOWN")
    assert first.grid_distance == 0
    assert first.move_pulse_profile is MovementPulseProfile.VERY_SHORT

    pushed = strategy.update(
        CombatFrame.from_iterable(
            2, player, [clean(1, GridCell(0, 1))], timestamp_seconds=1.0
        )
    )
    assert pushed.grid_distance == 1
    assert pushed.face == "DOWN"
    assert pushed.move == "down"
    assert pushed.move_pulse_profile is MovementPulseProfile.APPROACH
    assert pushed.move_pulse_ms == APPROACH_PULSE_MS


def test_same_cell_without_fresh_hint_clears_stale_direction() -> None:
    strategy, player, first = lock_at(GridCell(1, 0))
    assert first.face == "RIGHT"
    same_cell = strategy.update(
        CombatFrame.from_iterable(
            2, player, [clean(1, GridCell(0, 0))], timestamp_seconds=1.0
        )
    )
    assert same_cell.grid_distance == 0
    assert same_cell.face is None
    assert not same_cell.press_h
    assert same_cell.move is None


def test_d3_fires_h_and_keeps_chasing_toward_d0() -> None:
    _, _, decision = lock_at(GridCell(3, 0))
    assert decision.grid_distance == 3
    assert decision.move == "right"
    assert decision.move_pulse_profile is MovementPulseProfile.APPROACH
    assert decision.move_pulse_ms == APPROACH_PULSE_MS == 100
    assert decision.press_h
    assert decision.action_sequence.index("AIM_CURRENT_RIGHT_50MS") < decision.action_sequence.index(
        "H_TAP_50MS"
    )
    assert decision.action_sequence.index("H_TAP_50MS") < decision.action_sequence.index(
        "CHASE_RIGHT_100MS"
    )


@pytest.mark.parametrize("distance", [1, 2, 3, 4, 10, 50, 51])
def test_every_visible_distance_above_zero_uses_approach_chase(distance: int) -> None:
    _, _, decision = lock_at(GridCell(distance, 0))
    assert decision.grid_distance == distance
    assert decision.move == "right"
    assert decision.move_pulse_profile is MovementPulseProfile.APPROACH
    assert decision.move_pulse_ms == APPROACH_PULSE_MS


def test_d51_is_outside_h_range_but_chase_remains_active() -> None:
    _, _, decision = lock_at(GridCell(51, 0))
    assert decision.grid_distance == 51
    assert not decision.press_h
    assert decision.move == "right"
    assert decision.move_pulse_profile is MovementPulseProfile.APPROACH


def test_track_id_change_in_same_cell_preserves_identity_and_chase() -> None:
    strategy, player, second = lock_at(GridCell(1, 0))
    third = strategy.update(
        CombatFrame.from_iterable(
            2, player, [clean(99, GridCell(1, 0))], timestamp_seconds=1.0
        )
    )
    assert second.combat_target_id == 1
    assert third.combat_target_id == 1
    assert third.move == "right"
    assert third.move_pulse_profile is MovementPulseProfile.APPROACH
    assert not third.press_h


def test_multicell_blob_never_acquires() -> None:
    strategy = GridFocusStrategy()
    player = GridCell(0, 0)
    blob = CandidateObservation(
        10,
        GridCell(1, 0),
        ObservationKind.MULTI_CELL_BLOB,
        cells_touched=frozenset({GridCell(0, 0), GridCell(1, 0)}),
    )
    for frame in range(5):
        decision = strategy.update(CombatFrame.from_iterable(frame, player, [blob]))
        assert decision.combat_target_id is None
        assert not decision.press_h
        assert decision.move is None


def test_short_loss_suspends_without_blind_chase_or_h() -> None:
    strategy, player, _ = lock_at(GridCell(2, 0))
    decision = strategy.update(
        CombatFrame.from_iterable(2, player, [], timestamp_seconds=1.0)
    )
    assert decision.target_state is TargetState.SUSPENDED
    assert decision.combat_target_id == 1
    assert decision.move is None
    assert decision.move_pulse_profile is None
    assert not decision.press_h
    assert decision.hold_r
    assert decision.face is None


def test_hard_loss_after_two_seconds_clears_identity() -> None:
    strategy, player, _ = lock_at(GridCell(2, 0))
    decision = strategy.update(
        CombatFrame.from_iterable(2, player, [], timestamp_seconds=2.5)
    )
    assert decision.target_state is TargetState.SEARCH
    assert decision.combat_target_id is None
    assert not decision.press_h
    assert decision.move is None


def test_ko_releases_r_and_disables_future_combat() -> None:
    strategy, player, _ = lock_at(GridCell(2, 0))
    ended = strategy.update(
        CombatFrame.from_iterable(2, player, [], ko_confirmed=True)
    )
    after = strategy.update(
        CombatFrame.from_iterable(3, player, [clean(2, GridCell(-1, 0))])
    )
    assert ended.target_state is TargetState.ENDED
    assert after.target_state is TargetState.ENDED
    assert after.combat_target_id is None
    assert not after.press_h
    assert after.move is None
    assert not after.hold_r
    assert after.r_keydown_heartbeat_ms is None


def test_invalid_face_hint_is_rejected() -> None:
    with pytest.raises(ValueError, match="face_hint must be cardinal"):
        clean(1, GridCell(0, 0), face_hint="DIAGONAL")
