from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CombatTargetState(str, Enum):
    VISIBLE = "VISIBLE"
    CONTACT = "CONTACT"
    OCCLUDED_PREDICTED = "OCCLUDED_PREDICTED"
    LOCAL_REBIND = "LOCAL_REBIND"
    LOST = "LOST"


@dataclass(frozen=True, slots=True)
class RejectedCandidate:
    bbox: tuple[int, int, int, int]
    reason: str


@dataclass(frozen=True, slots=True)
class CombatTargetSnapshot:
    combat_target_id: int | None
    current_visual_track_id: int | None
    target_state: str
    confidence: float
    target_age: float
    frames_since_last_seen: int
    time_since_last_seen: float
    last_known_position: tuple[float, float] | None
    predicted_position: tuple[float, float] | None
    last_contact_direction: str
    movement_mode: str
    local_rebind_radius: float
    best_rebind_score: float
    target_switch_pending: int | None
    target_switch_confirmation: int
    target_size: tuple[float, float] | None
    trail: tuple[tuple[float, float], ...]
    active: bool


@dataclass(frozen=True, slots=True)
class CombatDecisionV351:
    mode: str
    navigation: str
    face: str
    base_r: bool
    h_opportunity: bool
    target_id: int | None
    grid_distance: int | None
    reason: str
    engagement_active: bool
    engagement_stable_seconds: float
    combat_target_id: int | None
    visual_track_id: int | None
    target_state: str
    target_confidence: float
    movement_mode: str
    predicted_position: tuple[float, float] | None
    time_since_last_seen: float


__all__ = [
    "CombatDecisionV351",
    "CombatTargetSnapshot",
    "CombatTargetState",
    "RejectedCandidate",
]
