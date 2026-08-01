from kage_combat_lab.domain import (
    CandidateObservation,
    CombatDecision,
    GridCell,
    MovementPulseProfile,
    ObservationKind,
    TargetState,
)
from kage_combat_lab.facing_authority import FacingAuthority


def candidate(cell=GridCell(1, 0), offset=(64.0, 0.0), track=1):
    return CandidateObservation(
        track,
        cell,
        ObservationKind.CLEAN_BODY,
        confidence=0.9,
        cells_touched=frozenset({cell}),
        relative_offset_px=offset,
    )


def decision(
    *,
    state=TargetState.LOCKED,
    cell=GridCell(1, 0),
    face="RIGHT",
    press_h=True,
    move="right",
):
    profile = MovementPulseProfile.APPROACH if move else None
    distance = GridCell(0, 0).chebyshev_distance(cell) if cell is not None else None
    return CombatDecision(
        frame_index=1,
        target_state=state,
        combat_target_id=1 if cell is not None else None,
        visual_track_id=1 if cell is not None else None,
        confirmed_cell=cell,
        predicted_cell=cell,
        grid_distance=distance,
        face=face,
        move=move,
        move_pulse_profile=profile,
        move_pulse_ms=profile.duration_ms if profile else None,
        post_pulse_observe_ms=150,
        hold_r=True,
        r_keydown_heartbeat_ms=250,
        press_h=press_h,
        h_pulse_ms=50 if press_h else None,
        h_cooldown_remaining_seconds=0.0,
        identity_score=0.8,
        appearance_score=0.8,
        background_probability=0.1,
        reidentified=False,
        aim_requires_confirmation=False,
        action_sequence=(),
        reason="test",
    )


def test_startup_right_is_explicitly_registered():
    authority = FacingAuthority()
    authority.register_startup_right(now=1.0)
    assert authority.commanded_facing == "RIGHT"
    assert authority.confirmed_facing == "RIGHT"
    assert authority.facing_source == "STARTUP_RIGHT_PULSE"


def test_search_attention_reid_and_occlusion_never_authorize_r_or_h():
    for state in (
        TargetState.SEARCH,
        TargetState.ATTENTION,
        TargetState.REID_LOCAL,
        TargetState.OCCLUDED_COAST,
    ):
        authority = FacingAuthority()
        authority.register_startup_right(now=0.0)
        raw = decision(state=state, cell=None, face=None, press_h=False, move=None)
        gated = authority.apply(raw, None, now=1.0)
        assert not gated.r_authorized
        assert not gated.h_authorized
        assert not gated.hold_r
        assert gated.move is None


def test_unaligned_target_enters_turn_align_without_h_or_chase():
    authority = FacingAuthority()
    authority.register_startup_right(now=0.0)
    left = candidate(GridCell(-1, 0), (-64.0, 0.0))
    gated = authority.apply(
        decision(cell=GridCell(-1, 0), face="LEFT", move="left"),
        left,
        now=1.0,
    )
    assert gated.target_state is TargetState.TURN_ALIGN
    assert gated.turn_direction == "LEFT"
    assert not gated.r_authorized
    assert not gated.h_authorized
    assert not gated.press_h
    assert gated.move is None


def test_turn_and_attack_are_separate_frames():
    authority = FacingAuthority()
    authority.register_startup_right(now=0.0)
    left = candidate(GridCell(-1, 0), (-64.0, 0.0))
    raw = decision(cell=GridCell(-1, 0), face="LEFT", move="left")
    turning = authority.apply(raw, left, now=1.0)
    assert authority.begin_turn(turning.turn_direction, now=1.0)
    assert authority.resolve_turn(
        observed_bearing="LEFT",
        target_visible=True,
        now=1.2,
    )
    assert not turning.press_h
    aligned = authority.apply(raw, left, now=1.3)
    assert aligned.target_state is TargetState.LOCKED_ALIGNED
    assert aligned.r_authorized
    assert aligned.h_authorized
    assert aligned.press_h


def test_two_failed_turns_invalidate_facing_and_back_off():
    authority = FacingAuthority()
    authority.register_startup_right(now=0.0)
    for now in (1.0, 1.2):
        assert authority.begin_turn("LEFT", now=now)
        assert not authority.resolve_turn(
            observed_bearing=None,
            target_visible=False,
            now=now + 0.1,
        )
    assert authority.confirmed_facing is None
    assert authority.orientation_invalidated_reason == "AIM_UNCONFIRMED"
    assert not authority.begin_turn("LEFT", now=1.35)


def test_d0_deadzone_uses_contact_lock_without_movement():
    authority = FacingAuthority()
    authority.register_startup_right(now=0.0)
    close = candidate(GridCell(0, 0), (5.0, 3.0))
    raw = decision(cell=GridCell(0, 0), face="RIGHT", move="right")
    gated = authority.apply(raw, close, now=1.0)
    assert gated.target_state is TargetState.CONTACT_LOCK
    assert gated.contact_deadzone_active
    assert gated.move is None
    assert gated.r_authorized


def test_d0_opposite_side_requires_two_frames_and_twenty_pixels():
    authority = FacingAuthority()
    authority.register_startup_right(now=0.0)
    raw = decision(cell=GridCell(0, 0), face="LEFT", move="left")
    weak = candidate(GridCell(0, 0), (-18.0, 0.0))
    one = authority.apply(raw, weak, now=1.0)
    assert one.stable_target_bearing == "RIGHT"

    strong = candidate(GridCell(0, 0), (-24.0, 0.0))
    first = authority.apply(raw, strong, now=1.1)
    assert first.stable_target_bearing == "RIGHT"
    assert first.side_crossing_frames == 1
    second = authority.apply(raw, strong, now=1.2)
    assert second.stable_target_bearing == "LEFT"
    assert second.target_state is TargetState.TURN_ALIGN


def test_large_relative_jump_invalidates_orientation():
    authority = FacingAuthority()
    authority.register_startup_right(now=0.0)
    right = candidate(GridCell(1, 0), (64.0, 0.0))
    authority.apply(decision(), right, now=1.0)
    jump = candidate(GridCell(1, 0), (-16.0, 0.0))
    gated = authority.apply(decision(face="LEFT", move="left"), jump, now=1.1)
    assert gated.orientation_invalidated_reason == "KNOCKBACK"
    assert not gated.r_authorized


def test_ko_never_authorizes_any_input():
    authority = FacingAuthority()
    authority.register_startup_right(now=0.0)
    ended = decision(state=TargetState.ENDED, cell=None, face=None, press_h=False, move=None)
    gated = authority.apply(ended, None, now=1.0)
    assert not gated.r_authorized
    assert not gated.h_authorized
    assert not gated.hold_r
