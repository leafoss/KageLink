"""Compatibility wrapper for the canonical Dojo training service.

New code must import :mod:`pc_agent.kage_pilot.dojo_training_service`.
This filename remains temporarily for third-party and historical test imports.
"""

from __future__ import annotations

from .dojo_training_service import (
    DojoTrainingConfig,
    DojoTrainingPhase,
    DojoTrainingService,
    DojoTrainingSnapshot,
)

__all__ = [
    "DojoTrainingConfig",
    "DojoTrainingPhase",
    "DojoTrainingService",
    "DojoTrainingSnapshot",
]
