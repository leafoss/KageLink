from __future__ import annotations

from types import SimpleNamespace


def _install(monkeypatch):
    import kage_combat_lab.live_bridge as live_module
    import kage_combat_lab.runtime_control_mode as mode_module

    class FakePhysical:
        def __init__(self, controller):
            self.controller = controller

        def execute(self, decision, *, confirm_aim=None):
            return ("BASE_EXECUTE",)

    monkeypatch.setattr(live_module, "PhysicalCombatInput", FakePhysical)
    mode_module._INSTALLED = False
    mode_module.install_runtime_control_mode()
    return live_module.PhysicalCombatInput


class _Controller:
    def __init__(self) -> None:
        self.releases = 0

    def release_all(self) -> None:
        self.releases += 1


def test_perception_only_blocks_every_physical_action(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "PERCEPTION_ONLY")
    Physical = _install(monkeypatch)
    controller = _Controller()
    physical = Physical(controller)

    actions = physical.execute(
        SimpleNamespace(turn_direction="LEFT", r_authorized=False)
    )

    assert controller.releases == 1
    assert "PR26_PERCEPTION_ONLY" in actions[1]


def test_face_only_blocks_non_turn_execution(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "FACE_ONLY")
    Physical = _install(monkeypatch)
    controller = _Controller()
    physical = Physical(controller)

    actions = physical.execute(
        SimpleNamespace(turn_direction=None, r_authorized=True)
    )

    assert controller.releases == 1
    assert "PR26_FACE_ONLY" in actions[1]


def test_full_combat_delegates_to_validated_physical_input(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "FULL_COMBAT")
    Physical = _install(monkeypatch)
    controller = _Controller()
    physical = Physical(controller)

    actions = physical.execute(
        SimpleNamespace(turn_direction=None, r_authorized=True)
    )

    assert actions == ("BASE_EXECUTE",)
    assert controller.releases == 0
