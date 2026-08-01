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
        self.activated = False
        self.released = 0

    def activate(self):
        self.activated = True
        self.calls.append(("activate",))

    def apply_keys(self, keys):
        self.calls.append(tuple(keys))

    def release_all(self):
        self.released += 1
        self.calls.append(("release_all",))


def test_live_bridge_uses_feet_anchor_on_64px_grid() -> None:
    track = SimpleNamespace(
        track_id=7,
        bbox=(64, 0, 32, 64),
        observations=3,
        enemy_score=80.0,
        shape_score=0.5,
    )
    observer = SimpleNamespace(tracker=FakeTracker({7: "VISIBLE"}))
    state = SimpleNamespace(player_center=(32.0, 32.0), tracks=(track,))
    frame = combat_frame_from_observer_state(
        observer=observer,
        state=state,
        frame_index=1,
        timestamp_seconds=1.0,
    )
    assert frame.player_cell == GridCell(0, 0)
    assert frame.candidates[0].anchor_cell == GridCell(1, 1)
    assert frame.candidates[0].is_clean_body
    assert frame.candidates[0].cells_touched == frozenset({GridCell(1, 1)})


def test_live_bridge_respects_observer_grid_origin() -> None:
    track = SimpleNamespace(
        track_id=8,
        bbox=(112, 64, 32, 64),
        observations=3,
        enemy_score=80.0,
        shape_score=0.5,
    )
    observer = SimpleNamespace(
        tracker=FakeTracker({8: "VISIBLE"}),
        grid_origin=(32.0, 32.0),
    )
    state = SimpleNamespace(player_center=(64.0, 64.0), tracks=(track,))
    frame = combat_frame_from_observer_state(
        observer=observer,
        state=state,
        frame_index=1,
        timestamp_seconds=1.0,
    )
    assert frame.player_cell == GridCell(0, 0)
    assert frame.candidates[0].anchor_cell == GridCell(1, 1)


def test_live_bridge_marks_large_effect_multicell() -> None:
    track = SimpleNamespace(
        track_id=9,
        bbox=(0, 0, 256, 128),
        observations=5,
        enemy_score=99.0,
        shape_score=1.0,
    )
    observer = SimpleNamespace(tracker=FakeTracker({9: "VISIBLE"}))
    state = SimpleNamespace(player_center=(32.0, 32.0), tracks=(track,))
    frame = combat_frame_from_observer_state(
        observer=observer,
        state=state,
        frame_index=1,
        timestamp_seconds=1.0,
    )
    candidate = frame.candidates[0]
    assert not candidate.is_clean_body
    assert len(candidate.cells_touched) > 1


def _decision(*, press_h=False, move=None, profile=None, state=TargetState.LOCKED):
    return CombatDecision(
        frame_index=1,
        target_state=state,
        combat_target_id=1 if state is not TargetState.ENDED else None,
        confirmed_cell=GridCell(2, 0) if state is not TargetState.ENDED else None,
        predicted_cell=GridCell(2, 0) if state is not TargetState.ENDED else None,
        grid_distance=2 if state is not TargetState.ENDED else None,
        face="RIGHT" if state is not TargetState.ENDED else None,
        move=move,
        move_pulse_profile=profile,
        move_pulse_ms=profile.duration_ms if profile else None,
        post_pulse_observe_ms=150,
        hold_r=state is not TargetState.ENDED,
        r_keydown_heartbeat_ms=250 if state is not TargetState.ENDED else None,
        press_h=press_h,
        h_pulse_ms=50 if press_h else None,
        h_cooldown_remaining_seconds=0.0,
        action_sequence=(),
        reason="test",
    )


def test_physical_input_aims_taps_h_and_preserves_r() -> None:
    controller = FakeController()
    sleeps = []
    physical = PhysicalCombatInput(controller, sleep_fn=sleeps.append)
    physical.activate()
    physical.start_combat_hold()
    actions = physical.execute(_decision(press_h=True))
    assert controller.repeat_keys == {"r"}
    assert ("r", "right") in controller.calls
    assert ("h", "r") in controller.calls
    assert actions == ("AIM_RIGHT_50MS", "H_50MS", "OBSERVE_150MS")
    assert sleeps == [0.05, 0.05, 0.15]


def test_physical_input_executes_approach_after_h() -> None:
    controller = FakeController()
    sleeps = []
    physical = PhysicalCombatInput(controller, sleep_fn=sleeps.append)
    physical.activate()
    physical.start_combat_hold()
    actions = physical.execute(
        _decision(
            press_h=True,
            move="right",
            profile=MovementPulseProfile.APPROACH,
        )
    )
    assert actions == (
        "AIM_RIGHT_50MS",
        "H_50MS",
        "MOVE_RIGHT_100MS",
        "OBSERVE_150MS",
    )
    assert sleeps == [0.05, 0.05, 0.1, 0.15]


def test_ended_decision_releases_everything() -> None:
    controller = FakeController()
    physical = PhysicalCombatInput(controller, sleep_fn=lambda _: None)
    physical.activate()
    actions = physical.execute(_decision(state=TargetState.ENDED))
    assert actions == ("RELEASE_ALL",)
    assert controller.released >= 2
