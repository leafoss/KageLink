from __future__ import annotations

from collections import deque
from typing import Any, Iterable

import cv2
import numpy as np

from .domain import CELL_SIZE_PX, CandidateObservation, GridCell
from .occupancy_model import (
    CellOccupancy,
    DiffSource,
    OccupancyCluster,
    OccupancyConfig,
    OccupancyState,
)
from .tile_perception import TileClass, TileEvidence


class PixelOccupancyMap:
    """Fast real-pixel occupancy map over the immutable 64px grid."""

    def __init__(self, config: OccupancyConfig) -> None:
        self.config = config
        self.perception: Any | None = None
        self.exact_baselines: dict[GridCell, np.ndarray] = {}
        self._samples: dict[GridCell, deque[np.ndarray]] = {}
        self._previous: dict[GridCell, np.ndarray] = {}
        self._votes: dict[GridCell, deque[bool]] = {}
        self.last_cells: dict[GridCell, CellOccupancy] = {}
        self.last_clusters: tuple[OccupancyCluster, ...] = ()

    def bind_perception(self, perception: Any) -> None:
        self.perception = perception

    @staticmethod
    def _crop(frame: np.ndarray, state: Any, item: TileEvidence) -> np.ndarray | None:
        arena_x, arena_y, _, _ = (int(v) for v in state.arena_rect)
        left, top, width, height = (int(v) for v in item.bbox)
        crop = frame[arena_y + top : arena_y + top + height, arena_x + left : arena_x + left + width]
        return crop.copy() if crop.shape[:2] == (CELL_SIZE_PX, CELL_SIZE_PX) else None

    def _reference(
        self,
        item: TileEvidence,
        current: np.ndarray | None = None,
    ) -> np.ndarray | None:
        perception = self.perception
        if perception is None:
            return None
        prefer_non_danger = item.category in {TileClass.DANGER, TileClass.UNKNOWN}
        getter = getattr(perception, "reference_crop", None)
        crop = getter(item, prefer_non_danger=prefer_non_danger) if getter else None
        if crop is None:
            examples = tuple(getattr(perception, "_terrain_examples", ()))
            selected = next(
                (x for x in examples if str(getattr(x, "example_id", "")) == str(item.matched_example_id or "")),
                None,
            )
            if prefer_non_danger and (selected is None or getattr(selected, "category", None) is TileClass.DANGER):
                allowed = {
                    TileClass.WALKABLE,
                    TileClass.WALKABLE_WITH_JUTSU,
                    TileClass.BLOCKING_OBJECT,
                    TileClass.TRANSITION,
                    TileClass.WALL,
                }
                candidates = [
                    x
                    for x in examples
                    if getattr(x, "category", None) in allowed
                    and getattr(x, "crop_path", None) is not None
                ]
                extractor = getattr(perception, "extractor", None)
                if current is not None and extractor is not None and candidates:
                    inset = max(0, min(8, int(getattr(perception.config, "crop_inset_px", 2))))
                    feature_crop = current[
                        inset : CELL_SIZE_PX - inset,
                        inset : CELL_SIZE_PX - inset,
                    ]
                    current_feature = extractor.extract(feature_crop)
                    selected = max(
                        candidates,
                        key=lambda example: extractor.similarity(
                            current_feature,
                            getattr(example, "feature"),
                        ),
                    )
                elif candidates:
                    selected = candidates[0]
            if selected is not None:
                crop = getattr(selected, "crop", None)
                if crop is None and getattr(selected, "crop_path", None) is not None:
                    crop = cv2.imread(str(selected.crop_path), cv2.IMREAD_COLOR)
                    if crop is not None:
                        try:
                            selected.crop = crop.copy()
                        except Exception:
                            pass
        if crop is None or getattr(crop, "size", 0) == 0:
            return None
        if crop.shape[:2] != (CELL_SIZE_PX, CELL_SIZE_PX):
            crop = cv2.resize(crop, (CELL_SIZE_PX, CELL_SIZE_PX), interpolation=cv2.INTER_AREA)
        return crop.copy()

    def _metrics(self, current: np.ndarray, baseline: np.ndarray):
        if current.shape != baseline.shape:
            baseline = cv2.resize(baseline, (current.shape[1], current.shape[0]), interpolation=cv2.INTER_AREA)
        cur_lab = cv2.cvtColor(current, cv2.COLOR_BGR2LAB).astype(np.int16)
        base_lab = cv2.cvtColor(baseline, cv2.COLOR_BGR2LAB).astype(np.int16)
        lab_delta = np.linalg.norm(cur_lab - base_lab, axis=2)
        cur_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        base_gray = cv2.cvtColor(baseline, cv2.COLOR_BGR2GRAY)
        gray_delta = cv2.absdiff(cur_gray, base_gray)
        threshold = float(self.config.pixel_delta_threshold)
        mask = np.where((lab_delta >= threshold) | (gray_delta >= max(10, int(threshold))), 255, 0).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        ratio = float(np.count_nonzero(mask)) / float(mask.size)
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        area = width = height = 0
        for index in range(1, count):
            _, _, w, h, a = (int(v) for v in stats[index])
            if a > area:
                area, width, height = a, w, h
        edge = float(np.mean(cv2.absdiff(cv2.Canny(cur_gray, 45, 135), cv2.Canny(base_gray, 45, 135)))) / 255.0
        color = min(1.0, float(np.mean(lab_delta)) / 80.0)
        return ratio, area, width, height, edge, color, cv2.absdiff(current, baseline), mask

    @staticmethod
    def _temporal(previous: np.ndarray | None, current: np.ndarray) -> float:
        if previous is None or previous.shape != current.shape:
            return 1.0
        return float(np.mean(cv2.absdiff(cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY), cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)))) / 255.0

    @staticmethod
    def _candidate_cells(candidate: CandidateObservation) -> frozenset[GridCell]:
        return frozenset(set(candidate.cells_touched) | {candidate.anchor_cell})

    @staticmethod
    def _bbox_coverage(candidates: Iterable[CandidateObservation], item: TileEvidence) -> float:
        cell_left, cell_top, cell_width, cell_height = item.bbox
        best = 0.0
        for candidate in candidates:
            if candidate.bbox is None:
                continue
            left, top, width, height = candidate.bbox
            w = max(0, min(left + width, cell_left + cell_width) - max(left, cell_left))
            h = max(0, min(top + height, cell_top + cell_height) - max(top, cell_top))
            best = max(best, float(w * h) / float(CELL_SIZE_PX * CELL_SIZE_PX))
        return min(1.0, best)

    @staticmethod
    def _neighbors(cell: GridCell):
        return tuple(
            GridCell(cell.x + dx, cell.y + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if dx or dy
        )

    def _learn_baseline(
        self,
        cell: GridCell,
        crop: np.ndarray,
        item: TileEvidence,
        raw_occupied: set[GridCell],
        danger_cells: set[GridCell],
        reference: np.ndarray | None,
    ) -> bool:
        if cell in self.exact_baselines:
            return False
        if item.category in {TileClass.DANGER, TileClass.PLAYER, TileClass.IGNORE_DYNAMIC}:
            return False
        if cell in raw_occupied or any(cell.chebyshev_distance(danger) <= 1 for danger in danger_cells):
            return False
        if self._temporal(self._previous.get(cell), crop) > self.config.baseline_stability:
            return False
        if reference is not None:
            ratio, area, *_ = self._metrics(crop, reference)
            if ratio > self.config.weak_ratio or area >= self.config.blob_area_min:
                return False
        samples = self._samples.setdefault(cell, deque(maxlen=self.config.baseline_samples))
        samples.append(crop.copy())
        if len(samples) < self.config.baseline_samples:
            return False
        self.exact_baselines[cell] = np.median(np.stack(tuple(samples)), axis=0).astype(np.uint8)
        return True

    def observe(
        self,
        *,
        frame: np.ndarray,
        state: Any,
        candidates: tuple[CandidateObservation, ...],
        evidence: dict[GridCell, TileEvidence],
        danger_fresh: bool,
    ) -> tuple[dict[GridCell, CellOccupancy], tuple[GridCell, ...]]:
        raw_occupied = {
            cell
            for candidate in candidates
            if candidate.track_id >= 0 and candidate.visible
            for cell in self._candidate_cells(candidate)
        }
        danger_cells = {
            item.cell
            for item in evidence.values()
            if danger_fresh
            and item.category is TileClass.DANGER
            and item.similarity >= self.config.danger_confidence
        }
        baseline_ready: list[GridCell] = []
        observed: dict[GridCell, CellOccupancy] = {}
        for item in evidence.values():
            crop = self._crop(frame, state, item)
            if crop is None:
                continue
            reference = self._reference(item, crop)
            if self._learn_baseline(item.cell, crop, item, raw_occupied, danger_cells, reference):
                baseline_ready.append(item.cell)
            baseline = self.exact_baselines.get(item.cell)
            source = DiffSource.EXACT_CELL_BASELINE
            if baseline is None:
                baseline = reference
                source = DiffSource.CLASS_REFERENCE if baseline is not None else DiffSource.NONE
            ratio = color = edge = 0.0
            area = width = height = 0
            diff = mask = None
            if baseline is not None:
                ratio, area, width, height, edge, color, diff, mask = self._metrics(crop, baseline)
            coverage = self._bbox_coverage(candidates, item)
            danger_prior = item.similarity if item.cell in danger_cells else 0.0
            structural = (
                source is not DiffSource.NONE
                and ratio >= self.config.suspect_ratio
                and area >= self.config.blob_area_min
                and width >= self.config.blob_width_min
                and height >= self.config.blob_height_min
            )
            strong = (
                source is not DiffSource.NONE
                and ratio >= self.config.strong_ratio
                and area >= self.config.blob_area_strong
                and height >= self.config.blob_height_strong
            )
            score = (
                0.40 * min(1.0, ratio / max(self.config.strong_ratio, 1e-6))
                + 0.22 * min(1.0, area / 600.0)
                + 0.13 * min(1.0, edge / 0.20)
                + 0.10 * min(1.0, color / 0.35)
                + 0.15 * danger_prior
            )
            if source is DiffSource.CLASS_REFERENCE:
                score *= 0.88
            occupied_now = bool(danger_prior or structural or strong)
            votes = self._votes.setdefault(item.cell, deque(maxlen=3))
            votes.append(occupied_now)
            state_value = (
                OccupancyState.OCCUPIED
                if occupied_now
                else OccupancyState.WEAK
                if source is not DiffSource.NONE and ratio >= self.config.weak_ratio
                else OccupancyState.EMPTY
            )
            observed[item.cell] = CellOccupancy(
                cell=item.cell,
                evidence=item,
                state=state_value,
                diff_source=source,
                true_changed_ratio=ratio,
                bbox_coverage_ratio=coverage,
                largest_blob_area=area,
                blob_width=width,
                blob_height=height,
                edge_delta=edge,
                color_delta=color,
                occupancy_score=max(0.0, min(1.0, score)),
                danger_prior=danger_prior,
                persistence=sum(votes),
                crop=crop,
                baseline=baseline.copy() if baseline is not None else None,
                diff=diff,
                mask=mask,
            )
            self._previous[item.cell] = crop.copy()
        self.last_cells = observed
        return observed, tuple(baseline_ready)

    def clusters(
        self,
        cells: dict[GridCell, CellOccupancy],
        candidates: tuple[CandidateObservation, ...],
    ) -> tuple[OccupancyCluster, ...]:
        occupied = {c for c, x in cells.items() if x.state is OccupancyState.OCCUPIED}
        occupied |= {
            c
            for c, x in cells.items()
            if x.state is OccupancyState.WEAK
            and x.occupancy_score >= 0.30
            and any(n in occupied for n in self._neighbors(c))
        }
        remaining = set(occupied)
        result: list[OccupancyCluster] = []
        while remaining:
            start = remaining.pop()
            group, queue = {start}, [start]
            while queue:
                current = queue.pop()
                for neighbor in self._neighbors(current):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        group.add(neighbor)
                        queue.append(neighbor)
            items = tuple(cells[c] for c in group)
            left = min(x.evidence.bbox[0] for x in items)
            top = min(x.evidence.bbox[1] for x in items)
            right = max(x.evidence.bbox[0] + x.evidence.bbox[2] for x in items)
            bottom = max(x.evidence.bbox[1] + x.evidence.bbox[3] for x in items)
            bottom_y = max(c.y for c in group)
            bottoms = sorted((c for c in group if c.y == bottom_y), key=lambda c: c.x)
            foot_cell = bottoms[len(bottoms) // 2]
            foot_box = cells[foot_cell].evidence.bbox
            foot = (foot_box[0] + foot_box[2] / 2.0, foot_box[1] + foot_box[3])
            raw_ids = {
                candidate.track_id
                for candidate in candidates
                if candidate.track_id >= 0 and self._candidate_cells(candidate) & group
            }
            result.append(
                OccupancyCluster(
                    local_id=len(result) + 1,
                    cells=frozenset(group),
                    bbox=(left, top, right - left, bottom - top),
                    foot_point=foot,
                    foot_cell=foot_cell,
                    occupancy_score=max(x.occupancy_score for x in items),
                    danger_prior=max(x.danger_prior for x in items),
                    true_changed_ratio=max(x.true_changed_ratio for x in items),
                    largest_blob_area=max(x.largest_blob_area for x in items),
                    raw_track_ids=frozenset(raw_ids),
                    cell_observations=items,
                )
            )
        result.sort(key=lambda x: (-x.danger_prior, -x.occupancy_score, x.foot_cell.y, x.foot_cell.x))
        self.last_clusters = tuple(result)
        return self.last_clusters
