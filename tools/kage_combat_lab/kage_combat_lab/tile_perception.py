from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np

from .domain import CELL_SIZE_PX, CandidateObservation, GridCell, ObservationKind, require_canonical_cell_size


class TileClass(str, Enum):
    UNKNOWN = "unknown"
    WALKABLE = "walkable"
    WALL = "wall"
    WALKABLE_WITH_JUTSU = "walkable_with_jutsu"
    BLOCKING_OBJECT = "blocking_object"
    PLAYER = "player"
    NPC = "npc"
    TRANSITION = "transition"
    DANGER = "danger"
    IGNORE_DYNAMIC = "ignore_dynamic"


TERRAIN_CLASSES = frozenset(
    {
        TileClass.WALKABLE,
        TileClass.WALL,
        TileClass.WALKABLE_WITH_JUTSU,
        TileClass.BLOCKING_OBJECT,
        TileClass.TRANSITION,
        TileClass.DANGER,
    }
)


def default_pr24_data_root() -> Path:
    configured = os.environ.get("KAGE_PR26_TILE_DATA_ROOT")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "KageNavigationLab"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "kage-navigation-lab"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return float(default)
    return float(raw)


@dataclass(frozen=True, slots=True)
class TilePerceptionConfig:
    data_root: Path
    profile: str = "default"
    region_id: str = "mapping_input_calibration"
    similarity_threshold: float = 0.90
    novelty_threshold: float = 0.12
    temporal_activity_threshold: float = 0.018
    terrain_reject_similarity: float = 0.965
    crop_inset_px: int = 2

    @classmethod
    def from_environment(cls) -> "TilePerceptionConfig":
        return cls(
            data_root=default_pr24_data_root(),
            profile=os.environ.get("KAGE_PR26_TILE_PROFILE", "default"),
            region_id=os.environ.get("KAGE_PR26_TILE_REGION", "mapping_input_calibration"),
            similarity_threshold=_env_float("KAGE_PR26_TILE_SIMILARITY", 0.90),
            novelty_threshold=_env_float("KAGE_PR26_TILE_NOVELTY", 0.12),
            temporal_activity_threshold=_env_float("KAGE_PR26_TILE_ACTIVITY", 0.018),
            terrain_reject_similarity=_env_float("KAGE_PR26_TILE_REJECT", 0.965),
        ).normalized()

    def normalized(self) -> "TilePerceptionConfig":
        if not 0.50 <= float(self.similarity_threshold) <= 0.999:
            raise ValueError("tile similarity threshold must be between 0.50 and 0.999")
        if not 0.01 <= float(self.novelty_threshold) <= 0.90:
            raise ValueError("tile novelty threshold must be between 0.01 and 0.90")
        if not 0.0 <= float(self.temporal_activity_threshold) <= 1.0:
            raise ValueError("tile temporal activity threshold must be between 0 and 1")
        if not 0.50 <= float(self.terrain_reject_similarity) <= 1.0:
            raise ValueError("tile terrain reject similarity must be between 0.50 and 1")
        return self

    @property
    def profile_root(self) -> Path:
        return self.data_root / "profiles" / self.profile

    @property
    def calibration_path(self) -> Path:
        return self.profile_root / "calibrations" / f"{self.region_id}_grid.json"

    @property
    def knowledge_path(self) -> Path:
        return self.profile_root / "tile_knowledge" / f"{self.region_id}.json"


class TileFeatureExtractor:
    """PR24-compatible compact descriptor for one calibrated tile."""

    def __init__(self, normalized_size: int = 32) -> None:
        if normalized_size < 16:
            raise ValueError("normalized_size must be at least 16")
        self.normalized_size = int(normalized_size)

    def extract(self, crop: np.ndarray) -> np.ndarray:
        if crop is None or crop.size == 0:
            raise ValueError("crop must be a non-empty image")
        if crop.ndim == 2:
            bgr = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        elif crop.ndim == 3 and crop.shape[2] >= 3:
            bgr = crop[:, :, :3]
        else:
            raise ValueError("crop must be grayscale or BGR-compatible")

        resized = cv2.resize(
            bgr,
            (self.normalized_size, self.normalized_size),
            interpolation=cv2.INTER_AREA,
        )
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        color_histogram = cv2.calcHist(
            [hsv], [0, 1], None, [12, 4], [0, 180, 0, 256]
        ).reshape(-1)
        color_histogram = color_histogram / max(float(color_histogram.sum()), 1e-9)

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        structure = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        structure = structure.reshape(-1)
        structure -= float(structure.mean())
        structure_std = float(structure.std())
        if structure_std > 1e-6:
            structure /= structure_std

        edges = cv2.Canny(gray, 45, 135)
        edge_blocks: list[float] = []
        for row in range(4):
            for column in range(4):
                y0 = row * edges.shape[0] // 4
                y1 = (row + 1) * edges.shape[0] // 4
                x0 = column * edges.shape[1] // 4
                x1 = (column + 1) * edges.shape[1] // 4
                edge_blocks.append(float(edges[y0:y1, x0:x1].mean()) / 255.0)

        means, deviations = cv2.meanStdDev(resized)
        color_statistics = np.asarray(
            [
                *(float(value) / 255.0 for value in means.reshape(-1)[:3]),
                *(float(value) / 255.0 for value in deviations.reshape(-1)[:3]),
            ],
            dtype=np.float32,
        )

        vector = np.concatenate(
            [
                color_histogram.astype(np.float32),
                structure.astype(np.float32),
                np.asarray(edge_blocks, dtype=np.float32),
                color_statistics,
            ]
        )
        norm = float(np.linalg.norm(vector))
        if norm > 1e-9:
            vector /= norm
        return vector.astype(np.float32)

    @staticmethod
    def similarity(left: np.ndarray, right: np.ndarray) -> float:
        if left.size == 0 or left.shape != right.shape:
            return 0.0
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        if denominator <= 1e-9:
            return 0.0
        cosine = float(np.dot(left, right) / denominator)
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


@dataclass(slots=True)
class _TerrainExample:
    example_id: str
    category: TileClass
    feature: np.ndarray
    crop_path: Path | None
    crop: np.ndarray | None = None


@dataclass(frozen=True, slots=True)
class TileEvidence:
    cell: GridCell
    bbox: tuple[int, int, int, int]
    category: TileClass
    similarity: float
    novelty: float
    known_terrain: bool
    temporal_activity: float
    activity_bbox: tuple[int, int, int, int] | None
    matched_example_id: str | None

    @property
    def unknown(self) -> bool:
        return not self.known_terrain


class PR24CombatTilePerception:
    """Use PR24 terrain knowledge as an authoritative PR25 acquisition gate.

    During acquisition, a calibrated cell that is unlike every taught terrain
    example can promote an existing raw track or create a synthetic track from
    temporal activity. Once Target Capsule has exemplars, synthetic acquisition
    stops and PR25 identity/ReID remains authoritative.
    """

    def __init__(self, config: TilePerceptionConfig | None = None) -> None:
        self.config = (config or TilePerceptionConfig.from_environment()).normalized()
        self.extractor = TileFeatureExtractor()
        self._terrain_examples: list[_TerrainExample] = []
        self._previous_crops: dict[GridCell, np.ndarray] = {}
        self._synthetic_ids: dict[GridCell, int] = {}
        self._next_synthetic_id = -1_000_000
        self.last_evidence: dict[GridCell, TileEvidence] = {}
        self.last_summary: dict[str, Any] = {}
        self._load()

    @property
    def terrain_example_count(self) -> int:
        return len(self._terrain_examples)

    def _load(self) -> None:
        calibration_path = self.config.calibration_path
        knowledge_path = self.config.knowledge_path
        missing = [str(path) for path in (calibration_path, knowledge_path) if not path.is_file()]
        if missing:
            raise FileNotFoundError("PR26_TILE_DATA_MISSING: " + " | ".join(missing))

        calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
        tile_size = int(calibration.get("tile_size_px", CELL_SIZE_PX))
        require_canonical_cell_size(tile_size)

        payload = json.loads(knowledge_path.read_text(encoding="utf-8"))
        for item in payload.get("examples", []):
            try:
                category = TileClass(str(item.get("category")))
            except ValueError:
                continue
            if category not in TERRAIN_CLASSES:
                continue
            feature_values = item.get("feature") or []
            feature = np.asarray(feature_values, dtype=np.float32)
            if feature.size == 0:
                continue
            crop_path_raw = item.get("crop_path")
            crop_path = Path(crop_path_raw) if crop_path_raw else None
            if crop_path is not None and not crop_path.is_absolute():
                crop_path = self.config.profile_root / crop_path
            self._terrain_examples.append(
                _TerrainExample(
                    example_id=str(item.get("id") or "unknown"),
                    category=category,
                    feature=feature,
                    crop_path=crop_path,
                )
            )

        if not self._terrain_examples:
            raise RuntimeError(
                "PR26_TILE_TERRAIN_EMPTY: teach at least one PR24 terrain tile "
                "(walkable, wall, obstacle, transition or danger)"
            )

    def describe(self) -> dict[str, Any]:
        return {
            "profile": self.config.profile,
            "region_id": self.config.region_id,
            "data_root": str(self.config.data_root),
            "calibration": str(self.config.calibration_path),
            "knowledge": str(self.config.knowledge_path),
            "terrain_examples": self.terrain_example_count,
            "similarity_threshold": self.config.similarity_threshold,
            "novelty_threshold": self.config.novelty_threshold,
            "temporal_activity_threshold": self.config.temporal_activity_threshold,
        }

    def _best_terrain(self, crop: np.ndarray) -> tuple[_TerrainExample, float]:
        feature = self.extractor.extract(crop)
        best = self._terrain_examples[0]
        best_score = -1.0
        for example in self._terrain_examples:
            score = self.extractor.similarity(feature, example.feature)
            if score > best_score:
                best = example
                best_score = score
        return best, max(0.0, min(1.0, best_score))

    @staticmethod
    def _temporal_activity(
        previous: np.ndarray | None,
        current: np.ndarray,
    ) -> tuple[float, tuple[int, int, int, int] | None]:
        if previous is None or previous.shape != current.shape:
            return 0.0, None
        previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
        current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(previous_gray, current_gray)
        activity = float(np.mean(diff)) / 255.0
        _, mask = cv2.threshold(diff, 22, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        best_bbox: tuple[int, int, int, int] | None = None
        best_area = 0
        for index in range(1, count):
            left, top, width, height, area = (int(value) for value in stats[index])
            if area < 24 or width < 4 or height < 8:
                continue
            if area > best_area:
                best_area = area
                best_bbox = (left, top, width, height)
        return max(0.0, min(1.0, activity)), best_bbox

    @staticmethod
    def _cell_range(length: int, origin: float) -> range:
        first = math.ceil((0.0 - float(origin)) / CELL_SIZE_PX)
        last = math.floor((float(length) - CELL_SIZE_PX - float(origin)) / CELL_SIZE_PX)
        return range(first, last + 1)

    def scan(self, *, frame_bgr: np.ndarray, state: Any, observer: Any) -> dict[GridCell, TileEvidence]:
        x0, y0, width, height = (int(value) for value in state.arena_rect)
        if width <= 0 or height <= 0:
            raise RuntimeError("PR26_TILE_ARENA_INVALID")
        arena = frame_bgr[y0 : y0 + height, x0 : x0 + width]
        if arena.size == 0:
            raise RuntimeError("PR26_TILE_ARENA_EMPTY")

        raw_origin = getattr(observer, "grid_origin", (0.0, 0.0))
        origin_x = float(raw_origin[0])
        origin_y = float(raw_origin[1])
        inset = max(0, min(8, int(self.config.crop_inset_px)))

        evidence: dict[GridCell, TileEvidence] = {}
        for cell_x in self._cell_range(width, origin_x):
            left = int(round(origin_x + cell_x * CELL_SIZE_PX))
            for cell_y in self._cell_range(height, origin_y):
                top = int(round(origin_y + cell_y * CELL_SIZE_PX))
                crop = arena[top : top + CELL_SIZE_PX, left : left + CELL_SIZE_PX].copy()
                if crop.shape[:2] != (CELL_SIZE_PX, CELL_SIZE_PX):
                    continue
                feature_crop = crop[inset : CELL_SIZE_PX - inset, inset : CELL_SIZE_PX - inset]
                matched, similarity = self._best_terrain(feature_crop)
                cell = GridCell(cell_x, cell_y)
                previous = self._previous_crops.get(cell)
                temporal_activity, local_activity_bbox = self._temporal_activity(previous, crop)
                self._previous_crops[cell] = crop
                activity_bbox = None
                if local_activity_bbox is not None:
                    bx, by, bw, bh = local_activity_bbox
                    activity_bbox = (left + bx, top + by, bw, bh)
                known = similarity >= self.config.similarity_threshold
                evidence[cell] = TileEvidence(
                    cell=cell,
                    bbox=(left, top, CELL_SIZE_PX, CELL_SIZE_PX),
                    category=matched.category if known else TileClass.UNKNOWN,
                    similarity=similarity,
                    novelty=1.0 - similarity,
                    known_terrain=known,
                    temporal_activity=temporal_activity,
                    activity_bbox=activity_bbox,
                    matched_example_id=matched.example_id,
                )

        self.last_evidence = evidence
        self.last_summary = {
            "cells": len(evidence),
            "unknown": sum(1 for item in evidence.values() if item.unknown),
            "active_unknown": sum(
                1
                for item in evidence.values()
                if item.unknown
                and item.novelty >= self.config.novelty_threshold
                and item.temporal_activity >= self.config.temporal_activity_threshold
            ),
        }
        return evidence

    @staticmethod
    def _plausible_bbox(bbox: tuple[int, int, int, int] | None) -> bool:
        if bbox is None:
            return False
        _, _, width, height = bbox
        return 4 <= int(width) <= 96 and 8 <= int(height) <= 192

    def _synthetic_id(self, cell: GridCell) -> int:
        existing = self._synthetic_ids.get(cell)
        if existing is not None:
            return existing
        value = self._next_synthetic_id
        self._next_synthetic_id -= 1
        self._synthetic_ids[cell] = value
        return value

    def enrich_candidates(
        self,
        *,
        frame_bgr: np.ndarray,
        state: Any,
        observer: Any,
        candidates: Iterable[CandidateObservation],
        target_memory: Any | None,
    ) -> tuple[CandidateObservation, ...]:
        evidence = self.scan(frame_bgr=frame_bgr, state=state, observer=observer)
        current = list(candidates)
        enriched: list[CandidateObservation] = []
        occupied_cells: set[GridCell] = set()

        for candidate in current:
            occupied_cells.update(candidate.cells_touched)
            matching = [evidence[cell] for cell in candidate.cells_touched if cell in evidence]
            if not matching:
                enriched.append(candidate)
                continue
            strongest = max(matching, key=lambda item: (item.novelty, item.temporal_activity))
            unknown = (
                strongest.unknown
                and strongest.novelty >= self.config.novelty_threshold
            )
            supported = (
                candidate.visible
                and candidate.is_single_cell
                and self._plausible_bbox(candidate.bbox)
                and (
                    candidate.body_like
                    or candidate.motion_score >= 0.45
                    or strongest.temporal_activity >= self.config.temporal_activity_threshold
                )
            )

            if unknown and supported:
                enriched.append(
                    replace(
                        candidate,
                        kind=ObservationKind.CLEAN_BODY,
                        body_like=True,
                        confidence=max(float(candidate.confidence), strongest.novelty),
                        identity_score=max(float(candidate.identity_score), strongest.novelty * 0.85),
                        appearance_score=max(float(candidate.appearance_score), strongest.novelty),
                        motion_score=max(
                            float(candidate.motion_score),
                            min(1.0, strongest.temporal_activity * 8.0),
                        ),
                        background_probability=min(
                            float(candidate.background_probability),
                            strongest.similarity * 0.35,
                        ),
                    )
                )
                continue

            if (
                strongest.known_terrain
                and strongest.similarity >= self.config.terrain_reject_similarity
                and candidate.confidence < 0.75
                and candidate.motion_score < 0.55
            ):
                enriched.append(
                    replace(
                        candidate,
                        kind=ObservationKind.CONTAMINATED_ACTIVITY,
                        body_like=False,
                        background_probability=max(
                            float(candidate.background_probability), strongest.similarity
                        ),
                    )
                )
                continue

            enriched.append(candidate)

        target_ready = bool(getattr(target_memory, "ready", False))
        raw_origin = getattr(observer, "grid_origin", (0.0, 0.0))
        player_x, player_y = (float(value) for value in state.player_center)
        player_cell = GridCell(
            math.floor((player_x - float(raw_origin[0])) / CELL_SIZE_PX),
            math.floor((player_y - float(raw_origin[1])) / CELL_SIZE_PX),
        )

        if not target_ready:
            for cell, item in evidence.items():
                if cell == player_cell or cell in occupied_cells:
                    continue
                if (
                    not item.unknown
                    or item.novelty < self.config.novelty_threshold
                    or item.temporal_activity < self.config.temporal_activity_threshold
                    or item.activity_bbox is None
                    or not self._plausible_bbox(item.activity_bbox)
                ):
                    continue
                left, top, width, height = item.activity_bbox
                foot = (float(left) + float(width) * 0.5, float(top) + float(height))
                relative_offset = (foot[0] - player_x, foot[1] - player_y)
                confidence = min(
                    1.0,
                    max(0.55, item.novelty + item.temporal_activity * 3.0),
                )
                enriched.append(
                    CandidateObservation(
                        track_id=self._synthetic_id(cell),
                        anchor_cell=cell,
                        kind=ObservationKind.CLEAN_BODY,
                        visible=True,
                        body_like=True,
                        confidence=confidence,
                        cells_touched=frozenset({cell}),
                        bbox=item.activity_bbox,
                        foot_point=foot,
                        relative_offset_px=relative_offset,
                        identity_score=min(1.0, item.novelty * 0.85),
                        appearance_score=min(1.0, item.novelty),
                        position_score=0.45,
                        shape_similarity=0.55,
                        motion_score=min(1.0, item.temporal_activity * 8.0),
                        background_probability=min(0.69, item.similarity * 0.35),
                    )
                )

        enriched.sort(key=lambda candidate: int(candidate.track_id))
        return tuple(enriched)


__all__ = [
    "PR24CombatTilePerception",
    "TERRAIN_CLASSES",
    "TileClass",
    "TileEvidence",
    "TileFeatureExtractor",
    "TilePerceptionConfig",
    "default_pr24_data_root",
]
