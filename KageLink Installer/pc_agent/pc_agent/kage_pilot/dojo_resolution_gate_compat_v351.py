from __future__ import annotations


class _SidecarSlot:
    """Descriptor-backed storage for fields added after a slots dataclass was created."""

    def __init__(self, default):
        self.default = default
        self.values: dict[int, object] = {}

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return self.values.get(id(instance), self.default)

    def __set__(self, instance, value) -> None:
        self.values[id(instance)] = value


def install_resolution_gate_slots_compat() -> None:
    from .trainer_search_v03k import TrainerSearchMotionGate

    if bool(getattr(TrainerSearchMotionGate, "_kagelink_resolution_slots", False)):
        return
    TrainerSearchMotionGate._kagelink_blind_moves = _SidecarSlot(0)
    TrainerSearchMotionGate._kagelink_scale_hold_started = _SidecarSlot(None)
    TrainerSearchMotionGate._kagelink_resolution_slots = True


__all__ = ["install_resolution_gate_slots_compat"]
