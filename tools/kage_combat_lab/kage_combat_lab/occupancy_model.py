from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from .domain import GridCell
from .hostility_gate import EntityState, HostilityState
from .tile_perception import TileClass, TileEvidence


class PR26ControlMode(str, Enum):
    PERCEPTION_ONLY = "PERCEPTION_ONLY"
    FACE_ONLY = "FACE_ONLY"
    FULL_COMBAT = "FULL_COMBAT"

    @classmethod
    def from_environment(cls) -> "PR26ControlMode":
        raw = os.environ.get("KAGE_PR26_CONTROL_MODE", cls.PERCEPTION_ONLY.value)
        try:
            return cls(str(raw).strip().upper())
        except ValueError as exc:
            raise ValueError(f"KAGE_PR26_CONTROL_MODE_INVALID:{raw!r}") from exc


class DiffSource(str, Enum):
    EXACT_CELL_BASELINE = "EXACT_CELL_BASELINE"
    CLASS_REFERENCE = "CLASS_REFERENCE"
    NONE = "NONE"


class OccupancyState(str, Enum):
    EMPTY = "EMPTY"
    WEAK = "WEAK"
    OCCUPIED = "OCCUPIED"


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(default if raw is None or not raw.strip() else raw)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(default if raw is None or not raw.strip() else raw)


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class OccupancyConfig:
    danger_confidence: float = 0.80
    danger_strong_confidence: float = 0.90
    weak_ratio: float = 0.04
    suspect_ratio: float = 0.08
    strong_ratio: float = 0.12
    blob_area_min: int = 180
    blob_area_strong: int = 250
    blob_width_min: int = 8
    blob_height_min: int = 14
    blob_height_strong: int = 18
    pixel_delta_threshold: float = 18.0
    baseline_samples: int = 5
    baseline_stability: float = 0.012
    danger_memory_seconds: float = 2.5
    danger_memory_frames: int = 12
    max_speed_cells_per_second: float = 3.5
    evidence_votes: int = 2
    evidence_window: int = 3
    face_deadzone_px: float = 12.0
    approach_step_min_px: float = 4.0
    approach_reductions: int = 3
    approach_total_px: float = 32.0
    contact_distance_px: float = 96.0
    non_aggressive_seconds: float = 3.0
    mask_edge_contact_px: int = 5
    mask_edge_band_px: int = 4
    player_mask_margin_px: int = 10
    cluster_max_width_cells: int = 2
    cluster_max_height_cells: int = 3
    cluster_max_cells: int = 6
    class_reference_score_cap: float = 0.28
    overlay_enabled: bool = False
    evidence_save_seconds: float = 2.0
    evidence_root: Path = Path("kage_pilot_loop_logs/occupancy_evidence")

    @classmethod
    def from_environment(cls) -> "OccupancyConfig":
        return cls(
            danger_confidence=_float("KAGE_PR26_DANGER_CONFIDENCE", 0.80),
            danger_strong_confidence=_float("KAGE_PR26_DANGER_STRONG", 0.90),
            weak_ratio=_float("KAGE_PR26_OCCUPANCY_WEAK", 0.04),
            suspect_ratio=_float("KAGE_PR26_CHANGED_RATIO", 0.08),
            strong_ratio=_float("KAGE_PR26_CHANGED_RATIO_STRONG", 0.12),
            blob_area_min=_int("KAGE_PR26_BLOB_AREA", 180),
            blob_area_strong=_int("KAGE_PR26_BLOB_AREA_STRONG", 250),
            blob_width_min=_int("KAGE_PR26_BLOB_WIDTH", 8),
            blob_height_min=_int("KAGE_PR26_BLOB_HEIGHT", 14),
            blob_height_strong=_int("KAGE_PR26_BLOB_HEIGHT_STRONG", 18),
            pixel_delta_threshold=_float("KAGE_PR26_PIXEL_DELTA", 18.0),
            baseline_samples=_int("KAGE_PR26_BASELINE_SAMPLES", 5),
            baseline_stability=_float("KAGE_PR26_BASELINE_STABILITY", 0.012),
            danger_memory_seconds=_float("KAGE_PR26_DANGER_MEMORY_SECONDS", 2.5),
            danger_memory_frames=_int("KAGE_PR26_DANGER_MEMORY_FRAMES", 12),
            max_speed_cells_per_second=_float("KAGE_PR26_MAX_SPEED_CELLS", 3.5),
            evidence_votes=_int("KAGE_PR26_EVIDENCE_VOTES", 2),
            evidence_window=_int("KAGE_PR26_EVIDENCE_WINDOW", 3),
            face_deadzone_px=_float("KAGE_PR26_FACE_DEADZONE_PX", 12.0),
            approach_step_min_px=_float("KAGE_PR26_APPROACH_STEP_PX", 4.0),
            approach_reductions=_int("KAGE_PR26_APPROACH_REDUCTIONS", 3),
            approach_total_px=_float("KAGE_PR26_APPROACH_TOTAL_PX", 32.0),
            contact_distance_px=_float("KAGE_PR26_CONTACT_DISTANCE_PX", 96.0),
            non_aggressive_seconds=_float("KAGE_PR26_NON_AGGRESSIVE_SECONDS", 3.0),
            mask_edge_contact_px=_int("KAGE_PR26_MASK_EDGE_CONTACT_PX", 5),
            mask_edge_band_px=_int("KAGE_PR26_MASK_EDGE_BAND_PX", 4),
            player_mask_margin_px=_int("KAGE_PR26_PLAYER_MASK_MARGIN_PX", 10),
            cluster_max_width_cells=_int("KAGE_PR26_CLUSTER_MAX_WIDTH_CELLS", 2),
            cluster_max_height_cells=_int("KAGE_PR26_CLUSTER_MAX_HEIGHT_CELLS", 3),
            cluster_max_cells=_int("KAGE_PR26_CLUSTER_MAX_CELLS", 6),
            class_reference_score_cap=_float("KAGE_PR26_CLASS_REFERENCE_SCORE_CAP", 0.28),
            overlay_enabled=_bool("KAGE_PR26_HOSTILITY_OVERLAY"),
            evidence_save_seconds=_float("KAGE_PR26_EVIDENCE_SAVE_SECONDS", 2.0),
            evidence_root=Path(
                os.environ.get(
                    "KAGE_PR26_EVIDENCE_DIR",
                    "kage_pilot_loop_logs/occupancy_evidence",
                )
            ),
        ).normalized()

    def normalized(self) -> "OccupancyConfig":
        if not 0.50 <= self.danger_confidence <= self.danger_strong_confidence <= 1.0:
            raise ValueError("danger confidence thresholds are invalid")
        if not 0.0 <= self.weak_ratio <= self.suspect_ratio <= self.strong_ratio <= 1.0:
            raise ValueError("occupancy ratio thresholds are invalid")
        if self.baseline_samples < 3:
            raise ValueError("baseline_samples must be at least 3")
        if self.evidence_window < 3 or not 1 <= self.evidence_votes <= self.evidence_window:
            raise ValueError("evidence voting configuration is invalid")
        if self.danger_memory_seconds <= 0 or self.danger_memory_frames < 1:
            raise ValueError("danger memory must be positive")
        if self.mask_edge_contact_px < 1 or not 1 <= self.mask_edge_band_px <= 16:
            raise ValueError("mask edge-contact configuration is invalid")
        if self.player_mask_margin_px < 0:
            raise ValueError("player mask margin must not be negative")
        if (
            self.cluster_max_width_cells < 1
            or self.cluster_max_height_cells < 1
            or self.cluster_max_cells < 1
        ):
            raise ValueError("cluster geometry limits must be positive")
        if not 0.0 <= self.class_reference_score_cap <= 0.49:
            raise ValueError("class reference score cap must stay below authority")
        return self


@dataclass(slots=True)
class CellOccupancy:
    cell: GridCell
    evidence: TileEvidence
    state: OccupancyState
    diff_source: DiffSource
    true_changed_ratio: float
    bbox_coverage_ratio: float
    largest_blob_area: int
    blob_width: int
    blob_height: int
    edge_delta: float
    color_delta: float
    occupancy_score: float
    danger_prior: float
    persistence: int
    crop: np.ndarray | None = None
    baseline: np.ndarray | None = None
    diff: np.ndarray | None = None
    mask: np.ndarray | None = None
    blob_bbox: tuple[int, int, int, int] | None = None
    player_masked_pixels: int = 0
    reference_authoritative: bool = False


@dataclass(slots=True)
class OccupancyCluster:
    local_id: int
    cells: frozenset[GridCell]
    bbox: tuple[int, int, int, int]
    foot_point: tuple[float, float]
    foot_cell: GridCell
    occupancy_score: float
    danger_prior: float
    true_changed_ratio: float
    largest_blob_area: int
    raw_track_ids: frozenset[int]
    cell_observations: tuple[CellOccupancy, ...]
    mask_contact_edges: int = 0
    authoritative_cells: int = 0


@dataclass(slots=True)
class DangerTrack:
    track_id: int
    first_seen: float
    last_seen: float
    last_seen_frame: int
    last_danger_time: float
    last_danger_frame: int
    cells: frozenset[GridCell]
    bbox: tuple[int, int, int, int]
    foot_point: tuple[float, float]
    foot_cell: GridCell
    occupancy_score: float
    danger_score: float
    true_changed_ratio: float
    largest_blob_area: int
    diff_source: DiffSource
    raw_track_ids: frozenset[int] = field(default_factory=frozenset)
    entity_votes: deque[bool] = field(default_factory=lambda: deque(maxlen=3))
    pixel_distance_history: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    grid_distance_history: deque[int] = field(default_factory=lambda: deque(maxlen=5))
    attention_lock: bool = True
    face_only_lock: bool = False
    combat_lock: bool = False
    entity_state: EntityState = EntityState.DANGER_CANDIDATE
    hostility_state: HostilityState = HostilityState.OBSERVE_HOSTILITY
    visible: bool = True
    ambiguous: bool = False
    reason: str = "DANGER seed created"

    @property
    def persistence(self) -> int:
        return sum(self.entity_votes)


@dataclass(frozen=True, slots=True)
class OccupancySnapshot:
    visual_lock: bool = False
    combat_lock: bool = False
    raw_track_id: int | None = None
    cell: GridCell | None = None
    entity_state: EntityState = EntityState.TERRAIN_ONLY
    hostility_state: HostilityState = HostilityState.NONE
    danger_confidence: float = 0.0
    terrain_class: TileClass = TileClass.UNKNOWN
    changed_pixel_ratio: float = 0.0
    largest_blob_area: int = 0
    blob_width: int = 0
    blob_height: int = 0
    persistence: int = 0
    distance_history: tuple[int, ...] = ()
    approach_votes: int = 0
    retreat_votes: int = 0
    reason: str = "no mobile DANGER identity"
    attention_lock: bool = False
    face_only_lock: bool = False
    cluster_id: int | None = None
    cluster_cells: tuple[tuple[int, int], ...] = ()
    cluster_bbox: tuple[int, int, int, int] | None = None
    true_changed_ratio: float = 0.0
    bbox_coverage_ratio: float = 0.0
    diff_source: str = DiffSource.NONE.value
    occupancy_score: float = 0.0
    danger_score: float = 0.0
    pixel_distance_history: tuple[float, ...] = ()
    approach_total_px: float = 0.0
    control_mode: str = PR26ControlMode.PERCEPTION_ONLY.value
    ambiguous: bool = False

    def as_log_fields(self) -> dict[str, Any]:
        return {
            "attention_lock": self.attention_lock,
            "visual_lock": self.visual_lock,
            "face_only_lock": self.face_only_lock,
            "combat_lock": self.combat_lock,
            "entity_state": self.entity_state.value,
            "hostility_state": self.hostility_state.value,
            "danger_confidence": round(self.danger_confidence, 4),
            "terrain_class": self.terrain_class.value,
            "changed_ratio": round(self.changed_pixel_ratio, 4),
            "true_changed_ratio": round(self.true_changed_ratio, 4),
            "bbox_coverage_ratio": round(self.bbox_coverage_ratio, 4),
            "diff_source": self.diff_source,
            "largest_blob": self.largest_blob_area,
            "entity_persistence": self.persistence,
            "D_history": list(self.distance_history),
            "pixel_distance_history": list(self.pixel_distance_history),
            "approach_votes": self.approach_votes,
            "approach_total_px": round(self.approach_total_px, 3),
            "hostility_track_id": self.raw_track_id,
            "cluster_id": self.cluster_id,
            "cluster_cells": [list(value) for value in self.cluster_cells],
            "cluster_bbox": list(self.cluster_bbox) if self.cluster_bbox else None,
            "cluster_cell_count": len(self.cluster_cells),
            "occupancy_score": round(self.occupancy_score, 4),
            "danger_score": round(self.danger_score, 4),
            "control_mode": self.control_mode,
            "ambiguous": self.ambiguous,
            "hostility_reason": self.reason,
        }
