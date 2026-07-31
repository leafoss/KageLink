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

    # Install after the original resolution bridge has loaded its aliases. The runtime
    # fix bounds template work per frame and makes the search grid follow real geometry.
    from .dojo_resolution_runtime_fix_v351 import (
        _ORIGINAL_RESOLUTION_DETECTOR,
        install_resolution_runtime_fix,
    )

    install_resolution_runtime_fix()

    # The bounded detector is runtime-only. Restore the public template API and generic
    # post-combat provider immediately; trainer_search, the anchor monitor and the isolated
    # round activation retain the bounded class through their explicit aliases.
    from . import dojo_templates, dojo_templates_v35, post_combat_v03c
    from .dojo_resolution_scope_compat_v351 import _legacy_detector_class

    dojo_templates_v35.UserDojoLeaderDetector = _ORIGINAL_RESOLUTION_DETECTOR
    dojo_templates.UserDojoLeaderDetector = _ORIGINAL_RESOLUTION_DETECTOR
    post_combat_v03c.PersistentDojoLeaderDetector = _legacy_detector_class()


__all__ = ["install_resolution_gate_slots_compat"]
