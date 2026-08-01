import pytest

from kage_combat_lab.domain import (
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
    strategy.update(CombatFrame.from_iterable(0, player, [clean(1, cell, face_hint=face_hint)]))
    decision = strategy.update(CombatFrame.from_iterable(1, player, [clean(1, cell, face_hint=face_hint)]))
    return strategy, player, decision


def test_d0_uses_very_short_direction_pulse_without_h() -> None:
    _, _, decision = lock_at(GridCell(0, 0), face_hint="LEFT")
    assert decision.grid_distance == 0
    assert decision.move == "left"
    assert decision.move_pulse_profile is MovementPulseProfile.VERY_SHORT
    assert not decision.press_h


def test_d0_without_visual_direction_holds_fail_closed() -> None:
    _, _, decision = lock_at(GridCell(0, 0))
    assert decision.grid_distance == 0
    assert decision.move is None
    assert decision.move_pulse_profile is None
    assert not decision.press_h


def test_d1_uses_very_short_direction_pulse_without_h() -> None:
    _, _, decision = lock_at(GridCell(1, 0))
    assert decision.grid_distance == 1
    assert decision.move == "right"
    assert decision.move_pulse_profile is MovementPulseProfile.VERY_SHORT
    assert not decision.press_h


def test_d2_holds_and_presses_h_with_clean_visual_confirmation() -> None:
    _, _, decision = lock_at(GridCell(2, 0))
    assert decision.grid_distance == 2
    assert decision.move is None
    assert decision.move_pulse_profile is None
    assert decision.press_h


def test_d3_presses_h_and_approaches_toward_d2() -> None:
    _, _, decision = lock_at(GridCell(3, 0))
    assert decision.grid_distance == 3
    assert decision.move == "right"
    assert decision.move_pulse_profile is MovementPulseProfile.APPROACH
    assert decision.press_h


def test_d4_holds_until_rule_is_defined() -> None:
    _, _, decision = lock_at(GridCell(4, 0))
    assert decision.grid_distance == 4
    assert decision.move is None
    assert decision.move_pulse_profile is None
    assert not decision.press_h


def test_track_id_change_in_same_cell_preserves_identity() -> None:
    strategy, player, second = lock_at(GridCell(1, 0))
    third = strategy.update(CombatFrame.from_iterable(2, player, [clean(99, GridCell(1, 0))]))
    assert second.combat_target_id == 1
    assert third.combat_target_id == 1
    assert third.move_pulse_profile is MovementPulseProfile.VERY_SHORT


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


def test_short_loss_suspends_without_movement_or_h() -> None:
    strategy, player, _ = lock_at(GridCell(2, 0))
    decision = strategy.update(CombatFrame.from_iterable(2, player, []))
    assert decision.target_state is TargetState.SUSPENDED
    assert decision.combat_target_id == 1
    assert decision.move is None
    assert decision.move_pulse_profile is None
    assert not decision.press_h


def test_ko_disables_future_combat() -> None:
    strategy, player, _ = lock_at(GridCell(2, 0))
    ended = strategy.update(CombatFrame.from_iterable(2, player, [], ko_confirmed=True))
    after = strategy.update(CombatFrame.from_iterable(3, player, [clean(2, GridCell(-1, 0))]))
    assert ended.target_state is TargetState.ENDED
    assert after.target_state is TargetState.ENDED
    assert after.combat_target_id is None
    assert not after.press_h


def test_invalid_face_hint_is_rejected() -> None:
    with pytest.raises(ValueError, match="face_hint must be cardinal"):
        clean(1, GridCell(0, 0), face_hint="DIAGONAL")
