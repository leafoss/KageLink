"""Deterministic offline combat reasoning laboratory.

The package deliberately imports no BYOND, Windows input, mouse, keyboard, capture
or runtime bridge modules. It evaluates the same explicit combat strategies using
logical grid observations and replay records only.
"""

from .runner import CombatLabReport, run_all_scenarios, run_scenario
from .scenarios import CombatLabScenario, all_scenarios

__all__ = [
    "CombatLabReport",
    "CombatLabScenario",
    "all_scenarios",
    "run_all_scenarios",
    "run_scenario",
]
