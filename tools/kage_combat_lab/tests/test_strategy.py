from kage_combat_lab.domain import CandidateObservation, CombatFrame, GridCell, ObservationKind, TargetState
from kage_combat_lab.strategy import GridFocusStrategy


def clean(track: int, cell: GridCell) -> CandidateObservation:
    return CandidateObservation(track, cell, ObservationKind.CLEAN_BODY)


def test_track_id_change_in_same_cell_preserves_identity() -> None:
    strategy = GridFocusStrategy()
    player = GridCell(0, 0)
    first = strategy.update(CombatFrame.from_iterable(0, player, [clean(1, GridCell(1, 0))]))
    second = strategy.update(CombatFrame.from_iterable(1, player, [clean(1, GridCell(1, 0))]))
    third = strategy.update(CombatFrame.from_iterable(2, player, [clean(99, GridCell(1, 0))]))
    assert first.target_state is TargetState.ATTENTION
    assert second.combat_target_id == 1
    assert third.combat_target_id == 1
    assert third.attack_primary


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
        assert not decision.attack_primary


def test_short_loss_suspends_without_movement() -> None:
    strategy = GridFocusStrategy()
    player = GridCell(0, 0)
    strategy.update(CombatFrame.from_iterable(0, player, [clean(1, GridCell(1, 0))]))
    strategy.update(CombatFrame.from_iterable(1, player, [clean(1, GridCell(1, 0))]))
    decision = strategy.update(CombatFrame.from_iterable(2, player, []))
    assert decision.target_state is TargetState.SUSPENDED
    assert decision.combat_target_id == 1
    assert decision.move is None
    assert not decision.attack_primary


def test_ko_disables_future_combat() -> None:
    strategy = GridFocusStrategy()
    player = GridCell(0, 0)
    strategy.update(CombatFrame.from_iterable(0, player, [clean(1, GridCell(1, 0))]))
    strategy.update(CombatFrame.from_iterable(1, player, [clean(1, GridCell(1, 0))]))
    ended = strategy.update(CombatFrame.from_iterable(2, player, [], ko_confirmed=True))
    after = strategy.update(CombatFrame.from_iterable(3, player, [clean(2, GridCell(-1, 0))]))
    assert ended.target_state is TargetState.ENDED
    assert after.target_state is TargetState.ENDED
    assert after.combat_target_id is None
