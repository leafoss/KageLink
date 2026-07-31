from __future__ import annotations

import sys

from .dojo_resolution_bridge_v351 import ResolutionIndependentDojoLeaderDetector


def _legacy_detector_class():
    from . import dojo_templates_v35

    # dojo_templates_v35 captured the compatibility provider before any runtime patch.
    return dojo_templates_v35._PersistentDojoLeaderDetector


def _patch_parent_dojo_aliases() -> None:
    """Use the adaptive detector only in the real parent request/anchor path."""

    from . import trainer_search_v03k

    trainer_search_v03k.PersistentDojoLeaderDetector = ResolutionIndependentDojoLeaderDetector

    monitor_module = sys.modules.get("pc_agent.kage_pilot.dojo_position_bridge")
    if monitor_module is not None:
        setattr(monitor_module, "UserDojoLeaderDetector", ResolutionIndependentDojoLeaderDetector)


def _scoped_user_detector_install() -> None:
    """Compatibility replacement for the old global detector installer."""

    from . import post_combat_v03c

    # The parent process must not alter generic post-combat classes used by tests or
    # other entry points. Only the Trainer acquisition and anchor monitor need the
    # external resolution-independent detector here.
    post_combat_v03c.PersistentDojoLeaderDetector = _legacy_detector_class()
    _patch_parent_dojo_aliases()


def install_resolution_scope_compat() -> None:
    """Prevent parent-process detector installation from leaking into legacy engines."""

    from . import dojo_templates, dojo_templates_v35, post_combat_v03c

    post_combat_v03c.PersistentDojoLeaderDetector = _legacy_detector_class()
    _patch_parent_dojo_aliases()

    dojo_templates_v35.install_user_dojo_leader_detector = _scoped_user_detector_install
    dojo_templates.install_user_dojo_leader_detector = _scoped_user_detector_install

    # kage_pilot_loop_v03j imports the installer by value before the canonical loop
    # installs this compatibility bridge. Replace that copied reference as well.
    for module_name in (
        "kage_pilot_loop_v03j",
        "pc_agent.kage_pilot.kage_pilot_loop_v03j",
    ):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "install_user_dojo_leader_detector"):
            setattr(module, "install_user_dojo_leader_detector", _scoped_user_detector_install)


def activate_round_resolution_detector() -> None:
    """Enable the adaptive detector globally only inside KagePilotRound.exe."""

    from . import post_combat_v03c

    post_combat_v03c.PersistentDojoLeaderDetector = ResolutionIndependentDojoLeaderDetector

    # Patch copied aliases in already-imported isolated runtime providers.
    for module_name, attribute in (
        ("kage_pilot_live_v03e_round", "PersistentDojoLeaderDetector"),
        ("kage_pilot_live_v0351_round", "PersistentDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_position_bridge", "UserDojoLeaderDetector"),
    ):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, attribute):
            setattr(module, attribute, ResolutionIndependentDojoLeaderDetector)


__all__ = [
    "activate_round_resolution_detector",
    "install_resolution_scope_compat",
]
