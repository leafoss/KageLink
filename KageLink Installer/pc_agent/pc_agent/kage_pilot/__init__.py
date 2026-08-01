"""Kage Pilot tools and the stable Dojo training integration facade."""

from dataclasses import dataclass

from .dataset import DatasetStore, SessionWriter
from . import dojo_training as _dojo_training


# KageLink 3.5.1 product contract: recovery is considered safe when
# HP >= 90% and Chakra >= 40%. Keep the compatibility module as the
# implementation authority while exporting a default-correct config type.
_dojo_training.MIN_SAFE_RECOVERY_CHAKRA_PERCENT = 40.0
_BaseDojoTrainingConfig = _dojo_training.DojoTrainingConfig


@dataclass(frozen=True, slots=True)
class DojoTrainingConfig(_BaseDojoTrainingConfig):
    recovery_chakra_percent: float = 40.0


_dojo_training.DojoTrainingConfig = DojoTrainingConfig
DojoTrainingPhase = _dojo_training.DojoTrainingPhase
DojoTrainingSnapshot = _dojo_training.DojoTrainingSnapshot

from .dojo_training_service import DojoTrainingService
from .dojo_stop_reliability_v351 import install_dojo_stop_reliability

install_dojo_stop_reliability(DojoTrainingService)

# Register concrete strategies through the explicit registry. These imports do not
# replace runtime classes or install combat monkeypatches. The configured default
# remains persistent_hardened until a physical BYOND validation authorizes promotion.
from .grid_focus_v2_strategy_v351 import register_grid_focus_v2_strategy
from .persistent_hardened_strategy_v351 import register_persistent_hardened_strategy

register_grid_focus_v2_strategy()
register_persistent_hardened_strategy()

from .learning import BehaviorCloner, Prediction
from .learning_v2 import CombatPrediction, PolicyPrediction, TemporalCombatModel


__all__ = [
    "BehaviorCloner",
    "CombatPrediction",
    "DatasetStore",
    "DojoTrainingConfig",
    "DojoTrainingPhase",
    "DojoTrainingService",
    "DojoTrainingSnapshot",
    "PolicyPrediction",
    "Prediction",
    "SessionWriter",
    "TemporalCombatModel",
]
