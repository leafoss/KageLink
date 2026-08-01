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


def decision(*, face: str | None, press_h: bool = True) -> CombatDecision:
    return CombatDecision(
        frame_index=10,
        target_state=TargetState.LOCKED,
        combat_target_id=1,
        visual_track_id=8,
        confirmed_cell=GridCell(0, 2),
        predicted_cell=GridCell(0, 2),
        grid_distance=2,
        face=face,
        move=None,
        move_pulse_profile=None,
        move_pulse_ms=None,
        post_pulse_observe_ms=150,
        hold_r=True,
        r_keydown_heartbeat_ms=250,
        press_h=press_h,
        h_pulse_ms=50 if press_h else None,
        h_cooldown_remaining_seconds=5.0 if press_h else 1.0,
        identity_score=0.8,
        appearance_score=0.75,
        background_probability=0.05,
        reidentified=False,
        aim_requires_confirmation=press_h,
        action_sequence=(),
        reason="fresh aim contract",
    )


def test_target_below_requires_down_confirmation_immediately_before_h() -> None:
    controller = FakeController()
    sleeps = []
    physical = PhysicalCombatInput(controller, sleep_fn=sleeps.append)
    physical.activate()
    physical.start_combat_hold()

    actions = physical.execute(
        decision(face="DOWN"),
        confirm_aim=lambda attempted: attempted,
    )

    down_index = controller.calls.index(("down", "r"))
    h_index = controller.calls.index(("h", "r"))
    assert down_index < h_index
    assert "AIM_REOBSERVE_75MS" in actions
    assert "AIM_CONFIRMED_DOWN" in actions
    assert "H_50MS" in actions


def test_h_is_skipped_when_fresh_frame_has_no_target_direction() -> None:
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    physical.start_combat_hold()

    actions = physical.execute(
        decision(face="DOWN"),
        confirm_aim=lambda _: None,
    )

    assert "H_SKIPPED_AIM_UNCONFIRMED" in actions
    assert ("h", "r") not in controller.calls


def test_h_is_skipped_when_current_decision_has_no_direction() -> None:
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    physical.start_combat_hold()

    try:
        physical.execute(
            decision(face=None),
            confirm_aim=lambda _: None,
        )
    except RuntimeError as error:
        assert "H_REQUIRES_CARDINAL_AIM" in str(error)
    else:
        raise AssertionError("H without cardinal aim must fail closed")

    assert ("h", "r") not in controller.calls
