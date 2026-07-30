"""Canonical Kage Pilot post-combat and recovery boundary.

The exported implementation remains backed by the validated compatibility
chain until Windows/BYOND validation authorizes physical extraction.
"""

from __future__ import annotations

from .post_combat_v03 import PostCombatDecision
from .post_combat_v03h import VisualProgressPostCombatRecoveryEngine

__all__ = [
    "PostCombatDecision",
    "VisualProgressPostCombatRecoveryEngine",
]
