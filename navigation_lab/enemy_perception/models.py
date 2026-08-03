from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class EntityClass(str, Enum):
    PLAYER = "player"
    NEUTRAL_NPC = "neutral_npc"
    ENEMY = "enemy"
    STATIC_OBJECT = "static_object"
    DECORATION = "decoration"
    EFFECT = "effect"
    IGNORED_DYNAMIC = "ignored_dynamic"
    UNKNOWN_ENTITY = "unknown_entity"


class HostilityState(str, Enum):
    UNKNOWN_VISUAL = "unknown_visual"
    STATIC_OVERLAY = "static_overlay"
    MOBILE_ENTITY = "mobile_entity"
    APPROACHING_ENTITY = "approaching_entity"
    FOLLOWING_ENTITY = "following_entity"
    HOSTILE_PROBABLE = "hostile_probable"
    HOSTILE_CONFIRMED = "hostile_confirmed"


@dataclass(slots=True)
class BackgroundMatch:
    available: bool
    reference_id: str | None = None
    confidence: float = 0.0
    image: Any | None = field(default=None, repr=False, compare=False)


@dataclass(slots=True)
class OverlayMetrics:
    difference_mean: float = 0.0
    difference_max: float = 0.0
    changed_pixel_count: int = 0
    changed_pixel_ratio: float = 0.0
    component_count: int = 0
    largest_component_area: int = 0
    overlay_detected: bool = False


@dataclass(slots=True)
class OverlayResult:
    metrics: OverlayMetrics
    difference: Any = field(repr=False, compare=False, default=None)
    mask: Any = field(repr=False, compare=False, default=None)


@dataclass(slots=True)
class EntityRegion:
    bounding_box_px: tuple[int, int, int, int]
    anchor_screen_cell: tuple[int, int]
    anchor_world_cell: tuple[int, int] | None
    covered_cells: list[tuple[int, int]]
    crop: Any = field(repr=False, compare=False, default=None)
    mask: Any = field(repr=False, compare=False, default=None)
    difference: Any = field(repr=False, compare=False, default=None)


@dataclass(slots=True)
class EntityClassification:
    category: EntityClass
    confidence: float
    known: bool
    matched_example_id: str | None = None


@dataclass(slots=True)
class EntityObservation:
    region: EntityRegion
    feature: list[float]
    classification: EntityClassification
    frame_index: int
    track_id: str | None = None
    movement_detected: bool = False
    previous_world_cell: tuple[int, int] | None = None
    distance_to_player: int | None = None
    previous_distance_to_player: int | None = None
    approaching: bool = False
    hostility_score: int = 0
    hostility_state: HostilityState = HostilityState.UNKNOWN_VISUAL
    hostility_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "classification": self.classification.category.value,
            "classification_confidence": self.classification.confidence,
            "known": self.classification.known,
            "bounding_box": list(self.region.bounding_box_px),
            "anchor_screen_cell": list(self.region.anchor_screen_cell),
            "anchor_world_cell": list(self.region.anchor_world_cell) if self.region.anchor_world_cell else None,
            "covered_cells": [list(item) for item in self.region.covered_cells],
            "movement_detected": self.movement_detected,
            "previous_world_cell": list(self.previous_world_cell) if self.previous_world_cell else None,
            "current_world_cell": list(self.region.anchor_world_cell) if self.region.anchor_world_cell else None,
            "distance_to_player": self.distance_to_player,
            "previous_distance_to_player": self.previous_distance_to_player,
            "approaching": self.approaching,
            "hostility_score": self.hostility_score,
            "hostility_state": self.hostility_state.value,
            "hostility_reasons": list(self.hostility_reasons),
        }


@dataclass(slots=True)
class EntityTrack:
    track_id: str
    feature: list[float]
    classification: EntityClassification
    first_seen_frame: int
    last_seen_frame: int
    first_seen_at: str
    last_seen_at: str
    current_screen_cell: tuple[int, int]
    current_world_cell: tuple[int, int] | None
    previous_world_cell: tuple[int, int] | None = None
    covered_cells: list[tuple[int, int]] = field(default_factory=list)
    position_history: list[tuple[int, int] | None] = field(default_factory=list)
    distance_history: list[int] = field(default_factory=list)
    movement_count: int = 0
    stationary_frame_count: int = 0
    hostility_score: int = 0
    hostility_state: HostilityState = HostilityState.UNKNOWN_VISUAL
    hostility_reasons: list[str] = field(default_factory=list)
    approach_streak: int = 0
    last_scored_frame: int = 0
    last_move_vector: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["classification"] = {
            "category": self.classification.category.value,
            "confidence": self.classification.confidence,
            "known": self.classification.known,
            "matched_example_id": self.classification.matched_example_id,
        }
        payload["hostility_state"] = self.hostility_state.value
        return payload


@dataclass(slots=True)
class CellDebugRecord:
    screen_cell: tuple[int, int]
    world_cell: tuple[int, int] | None
    pixel_bounds: tuple[int, int, int, int]
    terrain_class: str
    terrain_confidence: float
    background_reference_available: bool
    background_reference_id: str | None
    background_reference_confidence: float
    metrics: OverlayMetrics
    decision: str
    decision_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "screen_cell": list(self.screen_cell),
            "world_cell": list(self.world_cell) if self.world_cell else None,
            "pixel_bounds": list(self.pixel_bounds),
            "terrain_class": self.terrain_class,
            "terrain_confidence": self.terrain_confidence,
            "background_reference_available": self.background_reference_available,
            "background_reference_id": self.background_reference_id,
            "background_reference_confidence": self.background_reference_confidence,
            **asdict(self.metrics),
            "decision": self.decision,
            "decision_reason": self.decision_reason,
        }


@dataclass(slots=True)
class FramePerception:
    session_id: str
    frame_index: int
    captured_at: str
    window: dict[str, Any]
    calibration: dict[str, Any]
    frame_state: dict[str, Any]
    player: dict[str, Any]
    cells: list[CellDebugRecord]
    entities: list[EntityObservation]
    events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    processing_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "frame_index": self.frame_index,
            "captured_at": self.captured_at,
            "window": self.window,
            "calibration": self.calibration,
            "frame_state": self.frame_state,
            "player": self.player,
            "cells": [item.to_dict() for item in self.cells],
            "entities": [item.to_dict() for item in self.entities],
            "events": self.events,
            "errors": self.errors,
            "processing_time_ms": self.processing_time_ms,
        }
