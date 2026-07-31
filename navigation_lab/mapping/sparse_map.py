from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ..models import CellState, Point


@dataclass(slots=True)
class SparseMapCell:
    state: CellState = CellState.UNKNOWN
    confidence: float = 0.0
    observations: int = 0
    labels: set[str] = field(default_factory=set)

    def observe(self, state: CellState, confidence: float = 1.0, label: str | None = None) -> None:
        confidence = max(0.0, min(1.0, confidence))
        if self.observations == 0 or self.state == CellState.UNKNOWN or confidence >= self.confidence:
            self.state = state
        self.confidence = max(self.confidence, confidence)
        self.observations += 1
        if label:
            self.labels.add(label)


class SparseTileMap:
    """Unbounded tile map used while the world dimensions are still unknown."""

    def __init__(self, region_id: str, tile_size_px: int = 64) -> None:
        if tile_size_px <= 0:
            raise ValueError("tile_size_px must be positive")
        self.region_id = region_id
        self.tile_size_px = tile_size_px
        self.current_position = Point(0, 0)
        self._cells: dict[Point, SparseMapCell] = {}
        self.mark_visited(self.current_position, confidence=1.0, label="origin")

    def get(self, point: Point) -> SparseMapCell:
        return self._cells.get(point, SparseMapCell())

    def observe(
        self,
        point: Point,
        state: CellState,
        confidence: float = 1.0,
        label: str | None = None,
    ) -> None:
        cell = self._cells.setdefault(point, SparseMapCell())
        cell.observe(state, confidence, label)

    def mark_visited(self, point: Point, confidence: float = 1.0, label: str | None = None) -> None:
        self.observe(point, CellState.VISITED, confidence, label)

    def set_current_position(self, point: Point, confidence: float = 1.0) -> None:
        self.current_position = point
        self.mark_visited(point, confidence)

    def mark_path(self, points: Iterable[Point], confidence: float = 1.0) -> None:
        points_list = list(points)
        for point in points_list:
            self.mark_visited(point, confidence)
        if points_list:
            self.current_position = points_list[-1]

    def mark_landmark(self, point: Point, label: str, confidence: float = 1.0) -> None:
        self.observe(point, CellState.LANDMARK, confidence, label)

    def iter_cells(self) -> Iterable[tuple[Point, SparseMapCell]]:
        yield from self._cells.items()

    def bounds(self) -> tuple[int, int, int, int]:
        points = list(self._cells) or [self.current_position]
        return (
            min(point.x for point in points),
            min(point.y for point in points),
            max(point.x for point in points),
            max(point.y for point in points),
        )

    def render_ascii(self, radius: int = 10) -> str:
        if radius < 1:
            raise ValueError("radius must be at least 1")
        cx, cy = self.current_position.x, self.current_position.y
        symbols = {
            CellState.UNKNOWN: "?",
            CellState.WALKABLE: ".",
            CellState.VISITED: ",",
            CellState.BLOCKED: "#",
            CellState.TEMPORARY_BLOCK: "X",
            CellState.DANGEROUS: "!",
            CellState.LANDMARK: "L",
            CellState.TRANSITION: "T",
            CellState.DESTINATION: "D",
            CellState.CURRENT_POSITION: "P",
            CellState.PLANNED_PATH: "*",
        }
        rows: list[str] = []
        for y in range(cy - radius, cy + radius + 1):
            row: list[str] = []
            for x in range(cx - radius, cx + radius + 1):
                point = Point(x, y)
                row.append("P" if point == self.current_position else symbols[self.get(point).state])
            rows.append("".join(row))
        return "\n".join(rows)

    def to_dict(self) -> dict[str, Any]:
        cells = []
        for point, cell in sorted(self._cells.items(), key=lambda item: (item[0].y, item[0].x)):
            cells.append({
                "x": point.x,
                "y": point.y,
                "state": cell.state.value,
                "confidence": cell.confidence,
                "observations": cell.observations,
                "labels": sorted(cell.labels),
            })
        return {
            "schema_version": 1,
            "region_id": self.region_id,
            "tile_size_px": self.tile_size_px,
            "current_position": {"x": self.current_position.x, "y": self.current_position.y},
            "cells": cells,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SparseTileMap":
        result = cls(str(payload["region_id"]), int(payload.get("tile_size_px", 64)))
        result._cells.clear()
        for item in payload.get("cells", []):
            point = Point(int(item["x"]), int(item["y"]))
            result._cells[point] = SparseMapCell(
                state=CellState(item.get("state", CellState.UNKNOWN.value)),
                confidence=float(item.get("confidence", 0.0)),
                observations=int(item.get("observations", 0)),
                labels=set(item.get("labels", [])),
            )
        current = payload.get("current_position", {"x": 0, "y": 0})
        result.current_position = Point(int(current["x"]), int(current["y"]))
        result.mark_visited(result.current_position)
        return result
