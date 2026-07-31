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

    if not bool(getattr(TrainerSearchMotionGate, "_kagelink_resolution_slots", False)):
        TrainerSearchMotionGate._kagelink_blind_moves = _SidecarSlot(0)
        TrainerSearchMotionGate._kagelink_scale_hold_started = _SidecarSlot(None)
        TrainerSearchMotionGate._kagelink_resolution_slots = True

    # Preserve dynamic observer/search-grid corrections, then replace every
    # Trainer acquisition alias with the exact RAW pipeline. RAW runs last so an
    # older compatibility provider cannot win through import order.
    from .dojo_resolution_runtime_fix_v351 import install_resolution_runtime_fix

    install_resolution_runtime_fix()

    from . import post_combat_v03c
    from .dojo_resolution_scope_compat_v351 import _legacy_detector_class

    # Generic parent post-combat behavior remains isolated. Trainer acquisition,
    # anchor monitoring and the round helper are patched explicitly by RAW install.
    post_combat_v03c.PersistentDojoLeaderDetector = _legacy_detector_class()

    from .dojo_raw_trainer_v351 import install_raw_trainer_pipeline

    install_raw_trainer_pipeline()


__all__ = ["install_resolution_gate_slots_compat"]
