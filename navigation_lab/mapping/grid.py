from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..models import CellState, Point


@dataclass(slots=True)
class GridCell:
    state: CellState = CellState.UNKNOWN
    confidence: float = 0.0
    observations: int = 0
    labels: set[str] = field(default_factory=set)

    def observe(self, state: CellState, confidence: float, label: str | None = None) -> None:
        confidence = max(0.0, min(1.0, confidence))
        if self.observations == 0 or confidence >= self.confidence or self.state == CellState.UNKNOWN:
            self.state = state
            self.confidence = confidence
        else:
            self.confidence = min(1.0, (self.confidence * self.observations + confidence) / (self.observations + 1))
        self.observations += 1
        if label:
            self.labels.add(label)


class OccupancyGrid:
    def __init__(self, width: int, height: int, default: CellState = CellState.UNKNOWN) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Grid dimensions must be positive")
        self.width = width
        self.height = height
        self._cells = [[GridCell(default, 1.0 if default != CellState.UNKNOWN else 0.0) for _ in range(width)] for _ in range(height)]

    def in_bounds(self, point: Point) -> bool:
        return 0 <= point.x < self.width and 0 <= point.y < self.height

    def get(self, point: Point) -> GridCell:
        if not self.in_bounds(point):
            raise IndexError(point)
        return self._cells[point.y][point.x]

    def observe(self, point: Point, state: CellState, confidence: float = 1.0, label: str | None = None) -> None:
        self.get(point).observe(state, confidence, label)

    def set(self, point: Point, state: CellState, confidence: float = 1.0, label: str | None = None) -> None:
        if not self.in_bounds(point):
            raise IndexError(point)
        cell = GridCell(state=state, confidence=max(0.0, min(1.0, confidence)), observations=1)
        if label:
            cell.labels.add(label)
        self._cells[point.y][point.x] = cell

    def neighbors(self, point: Point, diagonal: bool = False) -> list[Point]:
        offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if diagonal:
            offsets += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        result = [Point(point.x + dx, point.y + dy) for dx, dy in offsets]
        return [candidate for candidate in result if self.in_bounds(candidate)]

    def is_walkable(self, point: Point, allow_unknown: bool = False) -> bool:
        state = self.get(point).state
        if state in {CellState.BLOCKED, CellState.TEMPORARY_BLOCK, CellState.DANGEROUS}:
            return False
        return allow_unknown or state != CellState.UNKNOWN

    def iter_points(self) -> Iterable[tuple[Point, GridCell]]:
        for y, row in enumerate(self._cells):
            for x, cell in enumerate(row):
                yield Point(x, y), cell

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "cells": [
                {
                    "x": point.x,
                    "y": point.y,
                    "state": cell.state.value,
                    "confidence": cell.confidence,
                    "observations": cell.observations,
                    "labels": sorted(cell.labels),
                }
                for point, cell in self.iter_points()
                if cell.state != CellState.UNKNOWN or cell.observations > 0
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "OccupancyGrid":
        grid = cls(int(payload["width"]), int(payload["height"]))
        for item in payload.get("cells", []):
            point = Point(int(item["x"]), int(item["y"]))
            cell = GridCell(
                state=CellState(item["state"]),
                confidence=float(item.get("confidence", 1.0)),
                observations=int(item.get("observations", 1)),
                labels=set(item.get("labels", [])),
            )
            grid._cells[point.y][point.x] = cell
        return grid
