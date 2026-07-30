"""Canonical Kage Pilot combat-control boundary.

The current implementation is supplied by the physically validated compatibility
engine. New code must import these contracts from this module rather than from a
versioned filename.
"""

from __future__ import annotations

from .live_control_v03 import (
    LiveCombatControlPlanner,
    LiveControlCommand,
    MotionBurstGuard,
    MotionBurstState,
)

__all__ = [
    "LiveCombatControlPlanner",
    "LiveControlCommand",
    "MotionBurstGuard",
    "MotionBurstState",
]
