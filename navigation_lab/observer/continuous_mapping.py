from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .grid_calibration import GridCalibration
from .motion import MotionSample, PhaseCorrelationMotionEstimator
from .tile_knowledge import TileClass, TileFeatureExtractor, TileKnowledgeBase
from .tile_map_engine import ClassifiedGridCell, SemanticTileMapEngine, TileScanResult


TERRAIN_CLASSES = frozenset(
    {
        TileClass.WALKABLE,
        TileClass.WALL,
        TileClass.WALKABLE_WITH_JUTSU,
        TileClass.TRANSITION,
        TileClass.DANGER,
    }
)
DYNAMIC_CLASSES = frozenset(
    {
        TileClass.PLAYER,
        TileClass.NPC,
        TileClass.BLOCKING_OBJECT,
        TileClass.IGNORE_DYNAMIC,
    }
)


@dataclass(slots=True)
class CategoryEvidence:
    confidence_total: float = 0.0
    observations: int = 0
    confirmed_observations: int = 0
    last_seen_frame: int = 0
    last_seen_at: str = ""

    def observe(self, confidence: float, confirmed: bool, frame_index: int, timestamp: str) -> None:
        weight = float(confidence) if confirmed else float(confidence) * 0.50
        self.confidence_total += weight
        self.observations += 1
        self.confirmed_observations += int(bool(confirmed))
        self.last_seen_frame = int(frame_index)
        self.last_seen_at = timestamp

    @property
    def score(self) -> float:
        if self.observations <= 0:
            return 0.0
        return self.confidence_total / float(self.observations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence_total": self.confidence_total,
            "observations": self.observations,
            "confirmed_observations": self.confirmed_observations,
            "last_seen_frame": self.last_seen_frame,
            "last_seen_at": self.last_seen_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CategoryEvidence":
        return cls(
            confidence_total=float(payload.get("confidence_total", 0.0)),
            observations=int(payload.get("observations", 0)),
            confirmed_observations=int(payload.get("confirmed_observations", 0)),
            last_seen_frame=int(payload.get("last_seen_frame", 0)),
            last_seen_at=str(payload.get("last_seen_at", "")),
        )


@dataclass(slots=True)
class DynamicOccupant:
    category: TileClass
    confidence: float
    observations: int
    last_seen_frame: int
    last_seen_at: str

    def observe(self, confidence: float, frame_index: int, timestamp: str) -> None:
        self.confidence = max(float(confidence), self.confidence * 0.70)
        self.observations += 1
        self.last_seen_frame = int(frame_index)
        self.last_seen_at = timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "confidence": self.confidence,
            "observations": self.observations,
            "last_seen_frame": self.last_seen_frame,
            "last_seen_at": self.last_seen_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DynamicOccupant":
        return cls(
            category=TileClass(str(payload["category"])),
            confidence=float(payload.get("confidence", 0.0)),
            observations=int(payload.get("observations", 0)),
            last_seen_frame=int(payload.get("last_seen_frame", 0)),
            last_seen_at=str(payload.get("last_seen_at", "")),
        )


@dataclass(slots=True)
class SemanticWorldCell:
    x: int
    y: int
    terrain: dict[TileClass, CategoryEvidence] = field(default_factory=dict)
    occupants: dict[TileClass, DynamicOccupant] = field(default_factory=dict)
    conflicts: int = 0
    last_seen_frame: int = 0

    def observe(
        self,
        category: TileClass,
        confidence: float,
        confirmed: bool,
        frame_index: int,
        timestamp: str,
    ) -> None:
        self.last_seen_frame = int(frame_index)
        if category in TERRAIN_CLASSES:
            current = self.resolved_terrain
            if current is not None and current != category:
                self.conflicts += 1
            evidence = self.terrain.setdefault(category, CategoryEvidence())
            evidence.observe(confidence, confirmed, frame_index, timestamp)
            return
        if category in DYNAMIC_CLASSES:
            occupant = self.occupants.get(category)
            if occupant is None:
                self.occupants[category] = DynamicOccupant(
                    category=category,
                    confidence=float(confidence),
                    observations=1,
                    last_seen_frame=int(frame_index),
                    last_seen_at=timestamp,
                )
            else:
                occupant.observe(confidence, frame_index, timestamp)

    @property
    def resolved_terrain(self) -> TileClass | None:
        if not self.terrain:
            return None
        ranked = sorted(
            self.terrain.items(),
            key=lambda item: (
                item[1].confirmed_observations,
                item[1].confidence_total,
                item[1].observations,
            ),
            reverse=True,
        )
        return ranked[0][0]

    @property
    def terrain_confidence(self) -> float:
        category = self.resolved_terrain
        return self.terrain[category].score if category is not None else 0.0

    def expire_occupants(self, frame_index: int, ttl_frames: int) -> None:
        self.occupants = {
            category: occupant
            for category, occupant in self.occupants.items()
            if frame_index - occupant.last_seen_frame <= ttl_frames
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "terrain": {category.value: evidence.to_dict() for category, evidence in self.terrain.items()},
            "occupants": {category.value: occupant.to_dict() for category, occupant in self.occupants.items()},
            "conflicts": self.conflicts,
            "last_seen_frame": self.last_seen_frame,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SemanticWorldCell":
        return cls(
            x=int(payload["x"]),
            y=int(payload["y"]),
            terrain={
                TileClass(category): CategoryEvidence.from_dict(evidence)
                for category, evidence in payload.get("terrain", {}).items()
            },
            occupants={
                TileClass(category): DynamicOccupant.from_dict(occupant)
                for category, occupant in payload.get("occupants", {}).items()
            },
            conflicts=int(payload.get("conflicts", 0)),
            last_seen_frame=int(payload.get("last_seen_frame", 0)),
        )


class SemanticWorldMap:
    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], SemanticWorldCell] = {}

    def observe(
        self,
        x: int,
        y: int,
        category: TileClass,
        confidence: float,
        confirmed: bool,
        frame_index: int,
        timestamp: str,
    ) -> None:
        cell = self.cells.setdefault((int(x), int(y)), SemanticWorldCell(int(x), int(y)))
        cell.observe(category, confidence, confirmed, frame_index, timestamp)

    def expire_dynamic(self, frame_index: int, ttl_frames: int = 8) -> None:
        for cell in self.cells.values():
            cell.expire_occupants(frame_index, ttl_frames)

    @property
    def terrain_count(self) -> int:
        return sum(cell.resolved_terrain is not None for cell in self.cells.values())

    @property
    def conflict_count(self) -> int:
        return sum(cell.conflicts for cell in self.cells.values())

    def bounds(self) -> tuple[int, int, int, int] | None:
        if not self.cells:
            return None
        xs = [coordinate[0] for coordinate in self.cells]
        ys = [coordinate[1] for coordinate in self.cells]
        return min(xs), min(ys), max(xs), max(ys)

    def render_ascii(self, player: tuple[int, int] | None, radius: int = 12) -> str:
        if player is None and not self.cells:
            return "?"
        if player is not None:
            min_x, max_x = player[0] - radius, player[0] + radius
            min_y, max_y = player[1] - radius, player[1] + radius
        else:
            bounds = self.bounds()
            assert bounds is not None
            min_x, min_y, max_x, max_y = bounds
        terrain_symbols = {
            TileClass.WALKABLE: ".",
            TileClass.WALL: "#",
            TileClass.WALKABLE_WITH_JUTSU: "J",
            TileClass.TRANSITION: "T",
            TileClass.DANGER: "!",
        }
        lines: list[str] = []
        for y in range(min_y, max_y + 1):
            row: list[str] = []
            for x in range(min_x, max_x + 1):
                if player == (x, y):
                    row.append("P")
                    continue
                cell = self.cells.get((x, y))
                if cell is None:
                    row.append("?")
                    continue
                if TileClass.NPC in cell.occupants:
                    row.append("N")
                elif TileClass.BLOCKING_OBJECT in cell.occupants:
                    row.append("B")
                elif cell.resolved_terrain is not None:
                    row.append(terrain_symbols.get(cell.resolved_terrain, "?"))
                else:
                    row.append("?")
            lines.append("".join(row))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "cells": [cell.to_dict() for cell in self.cells.values()],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SemanticWorldMap":
        world = cls()
        for item in payload.get("cells", []):
            cell = SemanticWorldCell.from_dict(item)
            world.cells[(cell.x, cell.y)] = cell
        return world


@dataclass(slots=True)
class UnknownTileGroup:
    id: str
    feature: list[float]
    count: int
    best_similarity: float
    first_seen_frame: int
    last_seen_frame: int
    latest_screen_cell: str
    crop_path: str | None = None
    representative_image: Any | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "feature": self.feature,
            "count": self.count,
            "best_similarity": self.best_similarity,
            "first_seen_frame": self.first_seen_frame,
            "last_seen_frame": self.last_seen_frame,
            "latest_screen_cell": self.latest_screen_cell,
            "crop_path": self.crop_path,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UnknownTileGroup":
        return cls(
            id=str(payload["id"]),
            feature=[float(value) for value in payload.get("feature", [])],
            count=int(payload.get("count", 1)),
            best_similarity=float(payload.get("best_similarity", 0.0)),
            first_seen_frame=int(payload.get("first_seen_frame", 0)),
            last_seen_frame=int(payload.get("last_seen_frame", 0)),
            latest_screen_cell=str(payload.get("latest_screen_cell", "")),
            crop_path=payload.get("crop_path"),
        )


class UnknownReviewQueue:
    def __init__(self, grouping_threshold: float = 0.965) -> None:
        if not 0.50 <= grouping_threshold <= 1.0:
            raise ValueError("grouping_threshold must be between 0.50 and 1.0")
        self.grouping_threshold = float(grouping_threshold)
        self.groups: dict[str, UnknownTileGroup] = {}

    def add(
        self,
        crop: Any,
        feature: list[float],
        best_similarity: float,
        screen_cell: str,
        frame_index: int,
    ) -> UnknownTileGroup:
        selected: UnknownTileGroup | None = None
        selected_score = 0.0
        for group in self.groups.values():
            score = TileFeatureExtractor.similarity(feature, group.feature)
            if score >= self.grouping_threshold and score > selected_score:
                selected = group
                selected_score = score
        if selected is None:
            selected = UnknownTileGroup(
                id=uuid4().hex[:16],
                feature=list(feature),
                count=1,
                best_similarity=float(best_similarity),
                first_seen_frame=int(frame_index),
                last_seen_frame=int(frame_index),
                latest_screen_cell=screen_cell,
                representative_image=crop.copy(),
            )
            self.groups[selected.id] = selected
            return selected
        selected.count += 1
        selected.last_seen_frame = int(frame_index)
        selected.latest_screen_cell = screen_cell
        selected.best_similarity = max(selected.best_similarity, float(best_similarity))
        if selected.representative_image is None:
            selected.representative_image = crop.copy()
        return selected

    def remove(self, group_id: str) -> UnknownTileGroup | None:
        return self.groups.pop(group_id, None)

    def sorted_groups(self) -> list[UnknownTileGroup]:
        return sorted(self.groups.values(), key=lambda group: (-group.count, group.first_seen_frame))

    def to_dict(self) -> dict[str, Any]:
        return {
            "grouping_threshold": self.grouping_threshold,
            "groups": [group.to_dict() for group in self.groups.values()],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UnknownReviewQueue":
        queue = cls(grouping_threshold=float(payload.get("grouping_threshold", 0.965)))
        for item in payload.get("groups", []):
            group = UnknownTileGroup.from_dict(item)
            queue.groups[group.id] = group
        return queue


@dataclass(slots=True)
class ContinuousMappingResult:
    frame_index: int
    scan: TileScanResult
    player_screen: tuple[int, int] | None
    player_world: tuple[int, int] | None
    motion: MotionSample
    mapped_cells: int
    confirmed_cells: int
    provisional_cells: int
    unknown_cells: int
    settled: bool
    localization_reason: str


class ContinuousSemanticMapper:
    """Continuously classify settled viewports and stitch them into relative world coordinates."""

    def __init__(
        self,
        calibration: GridCalibration,
        knowledge: TileKnowledgeBase,
        auto_threshold: float = 0.95,
        review_threshold: float = 0.90,
        grouping_threshold: float = 0.965,
        motion_response: float = 0.24,
    ) -> None:
        if not 0.50 <= review_threshold <= auto_threshold <= 1.0:
            raise ValueError("thresholds must satisfy 0.50 <= review <= auto <= 1.0")
        self.calibration = calibration
        self.knowledge = knowledge
        self.auto_threshold = float(auto_threshold)
        self.review_threshold = float(review_threshold)
        self.scan_engine = SemanticTileMapEngine(
            calibration=calibration,
            knowledge=knowledge,
            similarity_threshold=review_threshold,
        )
        self.motion = PhaseCorrelationMotionEstimator(
            min_response=motion_response,
            max_shift_px=max(96.0, calibration.tile_size_px * 2.5),
            deadzone_px=0.60,
        )
        self.world = SemanticWorldMap()
        self.review_queue = UnknownReviewQueue(grouping_threshold)
        self.frame_index = 0
        self.player_world: tuple[int, int] | None = None
        self.previous_player_screen: tuple[int, int] | None = None
        self.previous_frame: Any | None = None
        self.residual_world_px = [0.0, 0.0]
        self.last_result: ContinuousMappingResult | None = None

    def process_frame(self, frame: Any, timestamp: str | None = None) -> ContinuousMappingResult:
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.frame_index += 1
        scan = self.scan_engine.scan(frame)
        player_cell = self._select_player(scan.cells)
        player_screen = (
            (player_cell.crop.column, player_cell.crop.row) if player_cell is not None else None
        )
        motion = (
            MotionSample.baseline()
            if self.previous_frame is None
            else self.motion.estimate(self.previous_frame, frame)
        )

        localization_reason = "player_not_recognized"
        if player_screen is not None and self.player_world is None:
            self.player_world = (0, 0)
            localization_reason = "player_origin_initialized"
        elif player_screen is not None and self.player_world is not None:
            delta_x, delta_y, localization_reason = self._estimate_world_delta(player_screen, motion)
            self.player_world = (self.player_world[0] + delta_x, self.player_world[1] + delta_y)

        settled = self.previous_frame is None or not motion.accepted
        self.world.expire_dynamic(self.frame_index)
        mapped = confirmed = provisional = unknown = 0
        if settled:
            for cell in scan.cells:
                classification = cell.classification
                if not classification.known or classification.confidence < self.review_threshold:
                    unknown += 1
                    feature = self.knowledge.extractor.extract(cell.crop.image)
                    self.review_queue.add(
                        crop=cell.crop.image,
                        feature=feature,
                        best_similarity=classification.confidence,
                        screen_cell=cell.crop.id,
                        frame_index=self.frame_index,
                    )
                    continue
                is_confirmed = classification.confidence >= self.auto_threshold
                confirmed += int(is_confirmed)
                provisional += int(not is_confirmed)
                if self.player_world is None or player_screen is None:
                    continue
                world_x = self.player_world[0] + (cell.crop.column - player_screen[0])
                world_y = self.player_world[1] + (cell.crop.row - player_screen[1])
                self.world.observe(
                    world_x,
                    world_y,
                    classification.category,
                    classification.confidence,
                    is_confirmed,
                    self.frame_index,
                    timestamp,
                )
                mapped += 1

        self.previous_frame = frame.copy()
        self.previous_player_screen = player_screen
        result = ContinuousMappingResult(
            frame_index=self.frame_index,
            scan=scan,
            player_screen=player_screen,
            player_world=self.player_world,
            motion=motion,
            mapped_cells=mapped,
            confirmed_cells=confirmed,
            provisional_cells=provisional,
            unknown_cells=unknown,
            settled=settled,
            localization_reason=localization_reason,
        )
        self.last_result = result
        return result

    def _select_player(self, cells: list[ClassifiedGridCell]) -> ClassifiedGridCell | None:
        candidates = [
            cell
            for cell in cells
            if cell.classification.known and cell.classification.category == TileClass.PLAYER
        ]
        return max(candidates, key=lambda cell: cell.classification.confidence, default=None)

    def _estimate_world_delta(
        self,
        player_screen: tuple[int, int],
        motion: MotionSample,
    ) -> tuple[int, int, str]:
        if self.previous_player_screen is not None:
            screen_dx = player_screen[0] - self.previous_player_screen[0]
            screen_dy = player_screen[1] - self.previous_player_screen[1]
            if (screen_dx or screen_dy) and max(abs(screen_dx), abs(screen_dy)) <= 3:
                self.residual_world_px = [0.0, 0.0]
                return screen_dx, screen_dy, "player_screen_cell_delta"

        if not motion.accepted:
            return 0, 0, motion.reason
        self.residual_world_px[0] += -motion.screen_dx_px
        self.residual_world_px[1] += -motion.screen_dy_px
        tile = float(self.calibration.tile_size_px)
        delta_x = self._consume_residual_axis(0, tile)
        delta_y = self._consume_residual_axis(1, tile)
        if delta_x or delta_y:
            return delta_x, delta_y, "camera_translation_accumulated"
        return 0, 0, "camera_translation_partial"

    def _consume_residual_axis(self, axis: int, tile_size: float) -> int:
        value = self.residual_world_px[axis]
        if abs(value) < tile_size * 0.65:
            return 0
        steps = int(math.copysign(max(1, int(round(abs(value) / tile_size))), value))
        self.residual_world_px[axis] -= steps * tile_size
        return steps

    def teach_group(self, group_id: str, category: TileClass) -> Any:
        if category == TileClass.UNKNOWN:
            raise ValueError("UNKNOWN cannot be taught")
        group = self.review_queue.groups.get(group_id)
        if group is None:
            raise KeyError(group_id)
        if group.representative_image is None:
            raise ValueError("The unknown group has no loaded representative crop")
        example = self.knowledge.add_example(group.representative_image, category)
        self.review_queue.remove(group_id)
        return example

    def reset_runtime_baseline(self) -> None:
        self.previous_frame = None
        self.previous_player_screen = None
        self.residual_world_px = [0.0, 0.0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "frame_index": self.frame_index,
            "player_world": list(self.player_world) if self.player_world is not None else None,
            "residual_world_px": self.residual_world_px,
            "world": self.world.to_dict(),
            "review_queue": self.review_queue.to_dict(),
            "auto_threshold": self.auto_threshold,
            "review_threshold": self.review_threshold,
        }

    def restore_state(self, payload: dict[str, Any]) -> None:
        self.frame_index = int(payload.get("frame_index", 0))
        raw_player = payload.get("player_world")
        self.player_world = (
            (int(raw_player[0]), int(raw_player[1])) if raw_player is not None else None
        )
        raw_residual = payload.get("residual_world_px", [0.0, 0.0])
        self.residual_world_px = [float(raw_residual[0]), float(raw_residual[1])]
        self.world = SemanticWorldMap.from_dict(payload.get("world", {}))
        self.review_queue = UnknownReviewQueue.from_dict(payload.get("review_queue", {}))
        self.reset_runtime_baseline()
