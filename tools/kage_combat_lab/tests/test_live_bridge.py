from dataclasses import replace
from types import SimpleNamespace

import pytest

from kage_combat_lab.domain import (
    CombatDecision,
    GridCell,
    MovementPulseProfile,
    TargetState,
)
from kage_combat_lab.live_bridge import PhysicalCombatInput, combat_frame_from_observer_state


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


def aligned_decision(*, press_h=True, move=None):
    profile = MovementPulseProfile.APPROACH if move else None
    return CombatDecision(
        frame_index=1,
        target_state=TargetState.LOCKED,
        combat_target_id=1,
        visual_track_id=7,
        confirmed_cell=GridCell(1, 0),
        predicted_cell=GridCell(1, 0),
        grid_distance=1,
        face="RIGHT",
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
        confirmed_facing="RIGHT",
        stable_target_bearing="RIGHT",
        r_authorized=True,
        h_authorized=press_h,
    )


def test_startup_right_is_exclusive_and_ordered():
    sleeps = []
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=sleeps.append)
    physical.activate()
    actions = physical.startup_face_right()
    assert ("right",) in controller.calls
    assert ("r", "right") not in controller.calls
    assert sleeps == [0.3, 0.09, 0.12]
    assert actions[1] == "STARTUP_RIGHT_PULSE_90MS"


def test_turn_releases_r_and_uses_only_requested_direction():
    sleeps = []
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=sleeps.append)
    physical.activate()
    actions = physical.execute_turn("left")
    assert ("left",) in controller.calls
    assert ("left", "r") not in controller.calls
    assert sleeps == [0.03, 0.08, 0.09]
    assert "TURN_LEFT_80MS" in actions


def test_search_or_unaligned_decision_releases_everything():
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    decision = replace(
        aligned_decision(),
        target_state=TargetState.TURN_ALIGN,
        hold_r=False,
        r_authorized=False,
        press_h=False,
        h_authorized=False,
    )
    actions = physical.execute(decision)
    assert actions == ("RELEASE_ALL", "WAIT_FOR_TARGET_OR_ALIGNMENT")
    assert not any("h" in call for call in controller.calls)


def test_h_is_sent_only_after_alignment_was_authorized():
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    actions = physical.execute(aligned_decision(press_h=True))
    assert "H_50MS" in actions
    assert physical.h_fired(actions)
    assert ("h", "r") in controller.calls


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
    assert candidate.relative_offset_px == (48.0, 32.0)
    assert candidate.motion_score > 0.45


def test_emergency_exception_still_releases_direction():
    controller = FakeController()
    calls = 0

    def sleep(_):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("F12_STOP")

    physical = PhysicalCombatInput(controller, sleep_fn=sleep)
    physical.activate()
    with pytest.raises(RuntimeError, match="F12_STOP"):
        physical.execute_turn("right")
    assert controller.calls[-1] == ("release_all",)
