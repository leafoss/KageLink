"""Canonical Dojo Trainer search boundary."""

from __future__ import annotations

from .trainer_search_v03k import (
    TrainerSearchMotionGate,
    search_trainer_until_visible_safe,
)

__all__ = ["TrainerSearchMotionGate", "search_trainer_until_visible_safe"]
