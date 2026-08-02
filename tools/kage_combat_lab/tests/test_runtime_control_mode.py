from __future__ import annotations

from types import SimpleNamespace


def _install(monkeypatch):
    import kage_combat_lab.live_bridge as live_module
    import kage_combat_lab.runtime_control_mode as mode_module

    class FakePhysical:
        def __init__(self, controller):
            self.controller = controller
            self.activated = False

        def activate(self):
            self.activated = True
            self.controller.repeat_keys = {"r"}
            self.controller.activate()
            self.controller.release_all()

        def start_combat_hold(self):
            self.controller.apply_keys(("r",))
            return ("R_BASELINE_STARTED",)

        def execute(self, decision, *, confirm_aim=None):
            if getattr(decision, "turn_direction", None):
                direction = str(decision.turn_direction).lower()
                self.controller.apply_keys((direction,))
                return (f"TURN_{direction.upper()}",)
            self.controller.apply_keys(("r",))
            return ("R_BASELINE",)

    monkeypatch.setattr(live_module, "PhysicalCombatInput", FakePhysical)
    mode_module._INSTALLED = False
    mode_module.install_runtime_control_mode()
    return live_module.PhysicalCombatInput


class _Controller:
    def __init__(self) -> None:
        self.releases = 0
        self.repeat_keys = {"r"}
        self.applied = []
        self.activations = 0

    def activate(self) -> None:
        self.activations += 1

    def apply_keys(self, keys) -> None:
        self.applied.append(tuple(keys))

    def release_all(self) -> None:
        self.releases += 1


def test_perception_only_blocks_every_physical_action(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "PERCEPTION_ONLY")
    Physical = _install(monkeypatch)
    controller = _Controller()
    physical = Physical(controller)

    physical.activate()
    physical.start_combat_hold()
    actions = physical.execute(
        SimpleNamespace(turn_direction="LEFT", r_authorized=False)
    )

    assert controller.activations == 1
    assert controller.repeat_keys == set()
    assert controller.applied == []
    assert controller.releases >= 3
    assert "PR26_PERCEPTION_ONLY" in actions[1]


def test_face_only_blocks_baseline_r_and_non_turn_execution(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "FACE_ONLY")
    Physical = _install(monkeypatch)
    controller = _Controller()
    physical = Physical(controller)

    physical.activate()
    physical.start_combat_hold()
    actions = physical.execute(
        SimpleNamespace(turn_direction=None, r_authorized=True)
    )

    assert controller.repeat_keys == set()
    assert controller.applied == []
    assert "PR26_FACE_ONLY" in actions[1]


def test_face_only_delegates_only_exclusive_turn(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "FACE_ONLY")
    Physical = _install(monkeypatch)
    controller = _Controller()
    physical = Physical(controller)

    actions = physical.execute(
        SimpleNamespace(turn_direction="LEFT", r_authorized=False)
    )

    assert actions == ("TURN_LEFT",)
    assert controller.applied == [("left",)]
    assert controller.repeat_keys == set()


def test_full_combat_delegates_to_validated_physical_input(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "FULL_COMBAT")
    Physical = _install(monkeypatch)
    controller = _Controller()
    physical = Physical(controller)

    physical.activate()
    startup = physical.start_combat_hold()
    actions = physical.execute(
        SimpleNamespace(turn_direction=None, r_authorized=True)
    )

    assert startup == ("R_BASELINE_STARTED",)
    assert actions == ("R_BASELINE",)
    assert controller.applied == [("r",), ("r",)]
