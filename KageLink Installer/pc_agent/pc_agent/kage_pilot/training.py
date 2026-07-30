"""Canonical public Dojo training facade.

Versioned runtime layers remain internal compatibility details until they can be
semantically extracted with green CI and renewed real-game validation.
"""

from .dojo_training import DojoTrainingConfig, DojoTrainingPhase, DojoTrainingSnapshot
from .dojo_training_v03k import DojoTrainingService

__all__ = [
    "DojoTrainingConfig",
    "DojoTrainingPhase",
    "DojoTrainingService",
    "DojoTrainingSnapshot",
]
