from pathlib import Path

from kage_combat_lab.domain import (
    CandidateObservation,
    CombatDecision,
    CombatFrame,
    GridCell,
    MovementPulseProfile,
    ObservationKind,
    TargetState,
)
from kage_combat_lab.runtime_engagement_recovery import (
    ATTENTION_GRACE_SECONDS,
    RUNTIME_OCCLUDED_COAST_SECONDS,
    AttentionGraceLatch,
    _motion_supported_candidate,
    _promote_motion_support,
    baseline_r_required,
)


def decision(
    *,
    state: TargetState,
    r_authorized: bool = False,
    turn_direction: str | None = None,
    h_cancel_reason: str | None = None,
) -> CombatDecision:
    return CombatDecision(
        frame_index=1,
        target_state=state,
        combat_target_id=None,
        visual_track_id=7,
        confirmed_cell=GridCell(1, 0),
        predicted_cell=GridCell(1, 0),
        grid_distance=1,
        face="RIGHT",
        move=None,
        move_pulse_profile=None,
        move_pulse_ms=None,
        post_pulse_observe_ms=150,
        hold_r=False,
        r_keydown_heartbeat_ms=None,
        press_h=False,
        h_pulse_ms=None,
        h_cooldown_remaining_seconds=0.0,
        identity_score=0.0,
        appearance_score=0.0,
        background_probability=0.0,
        reidentified=False,
        aim_requires_confirmation=False,
        action_sequence=(),
        reason="test",
        turn_direction=turn_direction,
        r_authorized=r_authorized,
        h_authorized=False,
        h_cancel_reason=h_cancel_reason,
    )


def candidate(
    *,
    motion: float,
    confidence: float = 0.7,
    background: float = 0.1,
    track_id: int = 7,
) -> CandidateObservation:
    return CandidateObservation(
        track_id=track_id,
        anchor_cell=GridCell(1, 0),
        kind=ObservationKind.CONTAMINATED_ACTIVITY,
        visible=True,
        body_like=False,
        confidence=confidence,
        cells_touched=frozenset({GridCell(1, 0)}),
        face_hint="RIGHT",
        relative_offset_px=(64.0, 0.0),
        motion_score=motion,
        background_probability=background,
    )


def test_r_baseline_is_required_while_target_authority_is_pending() -> None:
    assert baseline_r_required(decision(state=TargetState.SEARCH))
    assert baseline_r_required(decision(state=TargetState.ATTENTION))
    assert baseline_r_required(decision(state=TargetState.REID_LOCAL))
    assert baseline_r_required(decision(state=TargetState.LOCKED_UNALIGNED))


def test_r_baseline_does_not_override_end_turn_or_confirmation_guard() -> None:
    assert not baseline_r_required(decision(state=TargetState.ENDED))
    assert not baseline_r_required(
        decision(state=TargetState.TURN_ALIGN, turn_direction="LEFT")
    )
    assert not baseline_r_required(
        decision(
            state=TargetState.LOCKED,
            h_cancel_reason="TURN_CONFIRMATION_GUARD",
        )
    )
    assert not baseline_r_required(
        decision(state=TargetState.LOCKED_ALIGNED, r_authorized=True)
    )


def test_attention_grace_survives_one_noisy_visual_gap() -> None:
    latch = AttentionGraceLatch()
    attention = decision(state=TargetState.ATTENTION)
    latch.arm(attention, now=10.0)
    assert ATTENTION_GRACE_SECONDS == 1.60
    assert latch.active(now=11.0)
    assert latch.last_decision is attention
    assert not latch.active(now=11.61)


def test_same_moving_track_can_complete_acquisition_support() -> None:
    attention = decision(state=TargetState.ATTENTION)
    moving = candidate(motion=0.72)
    frame = CombatFrame.from_iterable(
        2,
        GridCell(0, 0),
        [moving],
        timestamp_seconds=1.0,
    )
    support = _motion_supported_candidate(frame, attention)
    assert support is moving

    promoted = _promote_motion_support(frame, moving)
    assert promoted.candidates[0].kind is ObservationKind.CLEAN_BODY
    assert promoted.candidates[0].is_clean_body


def test_static_or_background_track_cannot_complete_acquisition_support() -> None:
    attention = decision(state=TargetState.ATTENTION)
    static = candidate(motion=0.45)
    background = candidate(motion=0.80, background=0.70)
    wrong_track = candidate(motion=0.80, track_id=99)

    for item in (static, background, wrong_track):
        frame = CombatFrame.from_iterable(
            2,
            GridCell(0, 0),
            [item],
            timestamp_seconds=1.0,
        )
        assert _motion_supported_candidate(frame, attention) is None


def test_low_fps_coast_window_covers_one_observed_missing_frame() -> None:
    assert RUNTIME_OCCLUDED_COAST_SECONDS == 1.25
    assert RUNTIME_OCCLUDED_COAST_SECONDS > 0.87


def test_full_round_installs_engagement_after_facing_and_startup_inheritance() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "kage_combat_lab"
        / "full_round_daynight.py"
    ).read_text(encoding="utf-8")
    assert source.index("install_runtime_facing_patch(full_round_module)") < source.index(
        "install_inherited_post_ok_startup()"
    )
    assert source.index("install_inherited_post_ok_startup()") < source.index(
        "install_runtime_engagement_recovery(full_round_module)"
    )
