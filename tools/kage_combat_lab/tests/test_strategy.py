from kage_combat_lab.domain import (
    CandidateObservation,
    CombatFrame,
    GridCell,
    MovementPulseProfile,
    ObservationKind,
    TargetState,
)
from kage_combat_lab.strategy import GridFocusStrategy


def candidate(
    track: int,
    cell: GridCell,
    *,
    offset=(32.0, 0.0),
    kind=ObservationKind.CLEAN_BODY,
    identity=0.0,
    appearance=0.0,
    reidentified=False,
):
    return CandidateObservation(
        track_id=track,
        anchor_cell=cell,
        kind=kind,
        confidence=0.9,
        cells_touched=frozenset({cell}),
        face_hint="RIGHT" if cell == GridCell(0, 0) and offset[0] > 0 else None,
        relative_offset_px=offset,
        identity_score=identity,
        appearance_score=appearance,
        position_score=0.8 if identity else 0.0,
        shape_similarity=0.8 if identity else 0.0,
        motion_score=0.6,
        background_probability=0.0,
        reidentified=reidentified,
        body_like=kind in {ObservationKind.CLEAN_BODY, ObservationKind.REIDENTIFIED_BODY},
    )


def lock(strategy, cell=GridCell(1, 0), offset=(64.0, 0.0)):
    player = GridCell(0, 0)
    strategy.update(
        CombatFrame.from_iterable(
            0, player, [candidate(1, cell, offset=offset)], timestamp_seconds=0.0
        )
    )
    decision = strategy.update(
        CombatFrame.from_iterable(
            1, player, [candidate(1, cell, offset=offset)], timestamp_seconds=0.2
        )
    )
    return player, decision


def test_d0_deadzone_holds_stable_without_h_or_movement():
    strategy = GridFocusStrategy()
    player, first = lock(strategy, GridCell(0, 0), offset=(20.0, 0.0))
    assert first.press_h
    strategy.resolve_h_request(fired=True)

    decision = strategy.update(
        CombatFrame.from_iterable(
            2,
            player,
            [candidate(1, GridCell(0, 0), offset=(4.0, 3.0))],
            timestamp_seconds=1.0,
        )
    )
    assert decision.face == "RIGHT"
    assert decision.move is None
    assert not decision.press_h


def test_d0_opposite_flip_requires_two_consistent_frames():
    strategy = GridFocusStrategy()
    player, first = lock(strategy, GridCell(0, 0), offset=(24.0, 1.0))
    strategy.resolve_h_request(fired=True)
    assert first.face == "RIGHT"

    one = strategy.update(
        CombatFrame.from_iterable(
            2,
            player,
            [candidate(1, GridCell(0, 0), offset=(-24.0, 1.0))],
            timestamp_seconds=1.0,
        )
    )
    assert one.face == "RIGHT"
    assert one.move is None

    two = strategy.update(
        CombatFrame.from_iterable(
            3,
            player,
            [candidate(1, GridCell(0, 0), offset=(-25.0, 0.0))],
            timestamp_seconds=1.2,
        )
    )
    assert two.face == "LEFT"
    assert two.move == "left"
    assert two.move_pulse_profile is MovementPulseProfile.VERY_SHORT


def test_short_occlusion_coasts_then_enters_local_reid_without_dropping_identity():
    strategy = GridFocusStrategy()
    player, first = lock(strategy, GridCell(1, 0), offset=(64.0, 0.0))
    strategy.resolve_h_request(fired=True)

    coast = strategy.update(
        CombatFrame.from_iterable(2, player, [], timestamp_seconds=0.5)
    )
    assert coast.target_state is TargetState.OCCLUDED_COAST
    assert coast.combat_target_id == first.combat_target_id
    assert coast.move == "right"
    assert not coast.press_h

    reid = strategy.update(
        CombatFrame.from_iterable(3, player, [], timestamp_seconds=1.0)
    )
    assert reid.target_state is TargetState.REID_LOCAL
    assert reid.combat_target_id == first.combat_target_id
    assert reid.move is None


def test_high_identity_contaminated_track_rebinds_same_logical_target():
    strategy = GridFocusStrategy()
    player, first = lock(strategy, GridCell(1, 0), offset=(64.0, 0.0))
    strategy.resolve_h_request(fired=True)

    strategy.update(CombatFrame.from_iterable(2, player, [], timestamp_seconds=1.0))
    reid_candidate = candidate(
        99,
        GridCell(1, 0),
        offset=(64.0, 0.0),
        kind=ObservationKind.REIDENTIFIED_BODY,
        identity=0.82,
        appearance=0.78,
        reidentified=True,
    )
    rebound = strategy.update(
        CombatFrame.from_iterable(
            3, player, [reid_candidate], timestamp_seconds=1.2
        )
    )
    assert rebound.target_state is TargetState.LOCKED
    assert rebound.combat_target_id == first.combat_target_id
    assert rebound.visual_track_id == 99
    assert rebound.reidentified


def test_hard_loss_waits_for_six_second_local_reid_window():
    strategy = GridFocusStrategy()
    player, first = lock(strategy)
    strategy.resolve_h_request(fired=True)

    retained = strategy.update(
        CombatFrame.from_iterable(2, player, [], timestamp_seconds=5.9)
    )
    assert retained.combat_target_id == first.combat_target_id
    assert retained.target_state is TargetState.REID_LOCAL

    lost = strategy.update(
        CombatFrame.from_iterable(3, player, [], timestamp_seconds=6.3)
    )
    assert lost.target_state is TargetState.SEARCH
    assert lost.combat_target_id is None


def test_failed_closed_loop_aim_does_not_consume_h_cooldown():
    strategy = GridFocusStrategy()
    player, first = lock(strategy)
    assert first.press_h
    strategy.resolve_h_request(fired=False)

    retry = strategy.update(
        CombatFrame.from_iterable(
            2, player, [candidate(1, GridCell(1, 0))], timestamp_seconds=0.5
        )
    )
    assert retry.press_h


def test_ko_releases_r_and_disables_future_combat():
    strategy = GridFocusStrategy()
    player, _ = lock(strategy)
    ended = strategy.update(
        CombatFrame.from_iterable(2, player, [], ko_confirmed=True, timestamp_seconds=1.0)
    )
    assert ended.target_state is TargetState.ENDED
    assert ended.combat_target_id is None
    assert not ended.hold_r
    assert not ended.press_h
