from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import cv2
import numpy as np

from .pr27_model import (
    CELL_SIZE_PX, ArenaRect, CellBaseline, CellDifference, CellSearchGroup,
    CellState, ComponentEvidence, GridCell, PR27Config,
)


class ArenaCropper:
    def __init__(
        self,
        rect: ArenaRect | None = None,
        *,
        left_ratio: float = 0.04,
        top_ratio: float = 0.04,
        right_ratio: float = 0.96,
        bottom_ratio: float = 0.86,
    ) -> None:
        self.rect = rect
        self.ratios = (left_ratio, top_ratio, right_ratio, bottom_ratio)

    def resolve(self, frame_bgr: np.ndarray) -> ArenaRect:
        if self.rect is not None:
            return self.rect.clamp(frame_bgr.shape)
        height, width = frame_bgr.shape[:2]
        left, top, right, bottom = self.ratios
        x = int(round(width * left))
        y = int(round(height * top))
        x2 = int(round(width * right))
        y2 = int(round(height * bottom))
        return ArenaRect(x, y, max(1, x2 - x), max(1, y2 - y)).clamp(frame_bgr.shape)

    def crop(self, frame_bgr: np.ndarray) -> tuple[ArenaRect, np.ndarray]:
        rect = self.resolve(frame_bgr)
        return rect, frame_bgr[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width]


class NativeGrid64:
    def __init__(self, cell_size_px: int = CELL_SIZE_PX) -> None:
        if int(cell_size_px) != CELL_SIZE_PX:
            raise ValueError("PR27_GRID_MUST_BE_NATIVE_64PX")
        self.cell_size_px = CELL_SIZE_PX

    def build(self, arena_shape: Sequence[int]) -> tuple[GridCell, ...]:
        height, width = int(arena_shape[0]), int(arena_shape[1])
        cells: list[GridCell] = []
        row = 0
        for y in range(0, height, self.cell_size_px):
            column = 0
            for x in range(0, width, self.cell_size_px):
                cells.append(
                    GridCell(
                        row=row,
                        column=column,
                        x=x,
                        y=y,
                        width=min(self.cell_size_px, width - x),
                        height=min(self.cell_size_px, height - y),
                    )
                )
                column += 1
            row += 1
        return tuple(cells)


class CellBaselineStore:
    def __init__(self) -> None:
        self._baselines: dict[tuple[int, int], CellBaseline] = {}
        self.metadata: dict[str, object] = {}

    def __len__(self) -> int:
        return len(self._baselines)

    def get(self, cell: GridCell) -> CellBaseline | None:
        return self._baselines.get((cell.row, cell.column))

    def set(self, cell: GridCell, image: np.ndarray, *, stability_score: float = 0.0) -> None:
        if image.shape[:2] != (cell.height, cell.width):
            raise ValueError(f"PR27_BASELINE_SHAPE_MISMATCH:{cell.cell_id}:{image.shape[:2]}")
        stored_image = np.ascontiguousarray(image.copy())
        self._baselines[(cell.row, cell.column)] = CellBaseline(
            cell=cell,
            image=stored_image,
            lab_image=np.ascontiguousarray(cv2.cvtColor(stored_image, cv2.COLOR_BGR2LAB)),
            captured_at=time.time(),
            valid=True,
            stability_score=float(stability_score),
        )

    def invalidate_all(self) -> None:
        for baseline in self._baselines.values():
            baseline.valid = False

    def load_npz(self, path: Path, cells: Iterable[GridCell]) -> int:
        if not path.is_file():
            raise RuntimeError(f"PR27_NATIVE_BASELINE_MISSING:{path}")
        by_key = {(cell.row, cell.column): cell for cell in cells}
        count = 0
        with np.load(path, allow_pickle=False) as archive:
            if "metadata" in archive.files:
                try:
                    self.metadata = json.loads(str(archive["metadata"].item()))
                except Exception:
                    self.metadata = {}
            for name in archive.files:
                if not name.startswith("cell_r"):
                    continue
                try:
                    raw_row, raw_column = name.removeprefix("cell_r").split("_c", 1)
                    key = (int(raw_row), int(raw_column))
                except (TypeError, ValueError):
                    continue
                cell = by_key.get(key)
                if cell is None:
                    continue
                image = archive[name]
                if image.shape[:2] != (cell.height, cell.width):
                    continue
                self.set(cell, image)
                count += 1
        if count == 0:
            raise RuntimeError("PR27_NATIVE_BASELINE_EMPTY")
        return count

    def save_npz(self, path: Path, *, metadata: Mapping[str, object] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, np.ndarray] = {
            f"cell_r{row}_c{column}": baseline.image
            for (row, column), baseline in self._baselines.items()
            if baseline.valid
        }
        payload["metadata"] = np.asarray(json.dumps(dict(metadata or self.metadata)))
        np.savez_compressed(path, **payload)


class CellDifferenceDetector:
    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        kernel_size = self.config.morphology_kernel
        self.kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)

    def compare(
        self,
        arena_bgr: np.ndarray,
        cells: Iterable[GridCell],
        baselines: CellBaselineStore,
    ) -> dict[tuple[int, int], CellDifference]:
        result: dict[tuple[int, int], CellDifference] = {}
        arena_lab = cv2.cvtColor(arena_bgr, cv2.COLOR_BGR2LAB)
        for cell in cells:
            current_lab = arena_lab[cell.y : cell.y + cell.height, cell.x : cell.x + cell.width]
            baseline = baselines.get(cell)
            if baseline is None or not baseline.valid or baseline.lab_image.shape != current_lab.shape:
                mask = np.zeros((cell.height, cell.width), dtype=np.uint8)
                result[(cell.row, cell.column)] = CellDifference(
                    cell=cell,
                    difference_mask=mask,
                    changed_pixel_count=0,
                    changed_ratio=0.0,
                    components=(),
                    state=CellState.BASELINE_INVALID,
                )
                continue

            delta = cv2.absdiff(current_lab, baseline.lab_image)
            magnitude = np.max(delta, axis=2)
            mask = np.where(
                magnitude >= self.config.pixel_delta_threshold,
                255,
                0,
            ).astype(np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)

            label_count, label_map, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
            cleaned = np.zeros_like(mask)
            components: list[ComponentEvidence] = []
            for label in range(1, label_count):
                x, y, width, height, area = (int(value) for value in stats[label])
                if area < self.config.minimum_component_area:
                    continue
                cleaned[label_map == label] = 255
                components.append(ComponentEvidence((x, y, width, height), area))

            changed = int(np.count_nonzero(cleaned))
            area = max(1, int(cell.width * cell.height))
            ratio = changed / area
            if ratio >= self.config.changed_ratio_threshold:
                state = CellState.CHANGED
            elif ratio >= self.config.uncertain_ratio_threshold:
                state = CellState.UNCERTAIN
            else:
                state = CellState.STABLE
            result[(cell.row, cell.column)] = CellDifference(
                cell=cell,
                difference_mask=cleaned,
                changed_pixel_count=changed,
                changed_ratio=ratio,
                components=tuple(components),
                state=state,
            )
        return result


class ChangedCellGrouper:
    """Groups cell addresses only; no bbox, foot, identity or hostility authority."""

    def group(self, differences: Mapping[tuple[int, int], CellDifference]) -> tuple[CellSearchGroup, ...]:
        changed = {
            key: value.cell
            for key, value in differences.items()
            if value.state is CellState.CHANGED
        }
        unvisited = set(changed)
        groups: list[CellSearchGroup] = []
        while unvisited:
            seed = min(unvisited)
            queue = [seed]
            unvisited.remove(seed)
            cells: list[GridCell] = []
            while queue:
                key = queue.pop()
                cells.append(changed[key])
                row, column = key
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        neighbour = (row + dr, column + dc)
                        if neighbour in unvisited:
                            unvisited.remove(neighbour)
                            queue.append(neighbour)
            groups.append(
                CellSearchGroup(
                    group_id=len(groups) + 1,
                    cells=tuple(sorted(cells)),
                )
            )
        return tuple(groups)
