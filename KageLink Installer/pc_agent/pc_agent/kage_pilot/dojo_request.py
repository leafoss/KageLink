"""Canonical Dojo request boundary.

The physically validated request/dialog provider remains encapsulated behind this
stable boundary. KageLink 3.5.1 adds only the defensive post-OK startup sequence:
one Ctrl+Right pulse followed by repeat-held R through the normal spawn timer.
"""

from __future__ import annotations

from .dojo_fight_v03e import DojoFightRequestError, TrainerClickTarget, f12_pressed
from .dojo_fight_v03i import DojoRoundWithoutCombatError
from .dojo_precombat_guard_v351 import request_taijutsu_dojo_spar_single_click


__all__ = [
    "DojoFightRequestError",
    "DojoRoundWithoutCombatError",
    "TrainerClickTarget",
    "f12_pressed",
    "request_taijutsu_dojo_spar_single_click",
]
