"""Canonical Dojo request boundary.

The implementation is still provided by the physically validated compatibility
chain. New code must import this module instead of a versioned filename.
"""

from __future__ import annotations

from .dojo_fight_v03e import DojoFightRequestError, TrainerClickTarget, f12_pressed
from .dojo_fight_v03i import (
    DojoRoundWithoutCombatError,
    request_taijutsu_dojo_spar_single_click,
)

__all__ = [
    "DojoFightRequestError",
    "DojoRoundWithoutCombatError",
    "TrainerClickTarget",
    "f12_pressed",
    "request_taijutsu_dojo_spar_single_click",
]
