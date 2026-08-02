from dataclasses import replace

from kage_combat_lab.domain import CombatDecision, GridCell, TargetState
from kage_combat_lab.live_bridge import PhysicalCombatInput


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


def decision(*, aligned: bool, press_h: bool = True) -> CombatDecision:
    return CombatDecision(
        frame_index=10,
        target_state=TargetState.LOCKED,
        combat_target_id=1,
        visual_track_id=8,
        confirmed_cell=GridCell(0, 2),
        predicted_cell=GridCell(0, 2),
        grid_distance=2,
        face="DOWN",
        move=None,
        move_pulse_profile=None,
        move_pulse_ms=None,
        post_pulse_observe_ms=150,
        hold_r=aligned,
        r_keydown_heartbeat_ms=250 if aligned else None,
        press_h=press_h and aligned,
        h_pulse_ms=50 if press_h and aligned else None,
        h_cooldown_remaining_seconds=0.0,
        identity_score=0.8,
        appearance_score=0.75,
        background_probability=0.05,
        reidentified=False,
        aim_requires_confirmation=False,
        action_sequence=(),
        reason="explicit facing authority",
        raw_target_bearing="DOWN",
        stable_target_bearing="DOWN",
        commanded_facing="DOWN" if aligned else "RIGHT",
        confirmed_facing="DOWN" if aligned else "RIGHT",
        r_authorized=aligned,
        h_authorized=press_h and aligned,
        turn_direction=None if aligned else "DOWN",
    )


def test_unaligned_frame_never_sends_h_or_r() -> None:
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    actions = physical.execute(decision(aligned=False))
    assert actions == ("RELEASE_ALL", "WAIT_FOR_TARGET_OR_ALIGNMENT")
    assert ("h", "r") not in controller.calls
    assert ("r",) not in controller.calls


def test_exclusive_turn_contains_no_r_or_h() -> None:
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    actions = physical.execute_turn("down")
    assert "TURN_DOWN_80MS" in actions
    assert ("down",) in controller.calls
    assert ("down", "r") not in controller.calls
    assert ("h", "r") not in controller.calls


def test_h_is_allowed_only_in_later_aligned_frame() -> None:
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    actions = physical.execute(decision(aligned=True))
    assert "H_50MS" in actions
    assert ("h", "r") in controller.calls


def test_h_authority_false_blocks_h_even_when_r_is_present() -> None:
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    blocked = replace(
        decision(aligned=True),
        press_h=True,
        h_authorized=False,
    )
    actions = physical.execute(blocked)
    assert "H_SKIPPED_NOT_AUTHORIZED" in actions
    assert ("h", "r") not in controller.calls
