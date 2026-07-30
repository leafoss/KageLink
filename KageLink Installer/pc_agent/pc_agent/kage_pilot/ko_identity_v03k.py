"""Compatibility wrapper for :mod:`pc_agent.kage_pilot.ko_identity`."""

from __future__ import annotations

from .ko_identity import (
    KOIdentityDecision,
    RoundKOIdentityGate,
    collapse_spaces,
    extract_ko_identity,
    normalize_ko_identity,
)

__all__ = [
    "KOIdentityDecision",
    "RoundKOIdentityGate",
    "collapse_spaces",
    "extract_ko_identity",
    "normalize_ko_identity",
]
