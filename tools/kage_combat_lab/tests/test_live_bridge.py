from types import SimpleNamespace

from kage_combat_lab.domain import (
    CombatDecision,
    GridCell,
    MovementPulseProfile,
    TargetState,
)
from kage_combat_lab.live_bridge import (
    PhysicalCombatInput,
    combat_frame_from_observer_state,
)


class FakeTracker:
    def __init__(self, states):
        self.states = states

    def context_for(self, track_id):
        return SimpleNamespace(state=self.states[track_id])


class FakeController:
    def __init__(self):
        self.repeat_keys = set()
        self.calls = []

    def activate(self):
        self.calls.append(("activate",))

    def apply_keys(self, keys):
        self.calls.append(tuple(keys))

    def release_all(self):
        self.calls.append(("release_all",))


def decision(face="RIGHT", press_h=True, move=None):
    profile = MovementPulseProfile.APPROACH if move else None
    return CombatDecision(
        frame_index=1,
        target_state=TargetState.LOCKED,
        combat_target_id=1,
        visual_track_id=7,
        confirmed_cell=GridCell(1, 0),
        predicted_cell=GridCell(1, 0),
        grid_distance=1,
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
        aim_requires_confirmation=press_h,
        action_sequence=(),
        reason="test",
    )


def test_live_bridge_keeps_bbox_foot_offset_and_motion_evidence():
    track = SimpleNamespace(
        track_id=7,
        bbox=(64, 0, 32, 64),
        observations=3,
        enemy_score=80.0,
        shape_score=0.5,
        residual_speed=20.0,
    )
    observer = SimpleNamespace(
        tracker=FakeTracker({7: "VISIBLE"}),
        grid_origin=(0.0, 0.0),
    )
    state = SimpleNamespace(player_center=(32.0, 32.0), tracks=(track,))
    frame = combat_frame_from_observer_state(
        observer=observer,
        state=state,
        frame_index=1,
        timestamp_seconds=1.0,
    )
    candidate = frame.candidates[0]
    assert candidate.anchor_cell == GridCell(1, 1)
    assert candidate.bbox == (64, 0, 32, 64)
    assert candidate.foot_point == (80.0, 64.0)
    assert candidate.relative_offset_px == (48.0, 32.0)
    assert candidate.motion_score > 0.45


def test_closed_loop_fires_only_after_fresh_confirmation():
    sleeps = []
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=sleeps.append)
    physical.activate()
    actions = physical.execute(
        decision(),
        confirm_aim=lambda attempted: attempted,
    )
    assert "AIM_CONFIRMED_RIGHT" in actions
    assert "H_50MS" in actions
    assert physical.h_fired(actions)
    assert 0.075 in sleeps


def test_closed_loop_corrects_direction_before_h():
    sleeps = []
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=sleeps.append)
    physical.activate()
    answers = iter(["DOWN", "DOWN"])
    actions = physical.execute(
        decision(),
        confirm_aim=lambda _: next(answers),
    )
    assert "AIM_CORRECT_RIGHT_TO_DOWN" in actions
    assert "AIM_DOWN_50MS" in actions
    assert "AIM_CONFIRMED_DOWN" in actions
    assert "H_50MS" in actions


def test_closed_loop_skips_h_when_two_fresh_frames_cannot_confirm():
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    actions = physical.execute(
        decision(),
        confirm_aim=lambda _: None,
    )
    assert "H_SKIPPED_AIM_UNCONFIRMED" in actions
    assert not physical.h_fired(actions)
    assert not any(call == ("h", "r") for call in controller.calls)


def test_h_confirmation_is_required_when_flagged():
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    actions = physical.execute(decision(), confirm_aim=None)
    assert "H_SKIPPED_NO_AIM_CONFIRMATION" in actions
    assert not physical.h_fired(actions)
