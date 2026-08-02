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
        self._scene_recovery_cells: set[GridCell] = set()
        self.last_scene_shift_cells: tuple[GridCell, ...] = ()
        self.scene_shift_generation = 0
        self.last_player_rect: tuple[int, int, int, int] | None = None
        self.last_rejected_clusters: tuple[dict[str, Any], ...] = ()
        self.last_cells: dict[GridCell, CellOccupancy] = {}
        self.last_clusters: tuple[OccupancyCluster, ...] = ()

    def bind_perception(self, perception: Any) -> None:
        self.perception = perception

    @staticmethod
    def _crop(frame: np.ndarray, state: Any, item: TileEvidence) -> np.ndarray | None:
        arena_x, arena_y, _, _ = (int(v) for v in state.arena_rect)
        left, top, width, height = (int(v) for v in item.bbox)
        crop = frame[
            arena_y + top : arena_y + top + height,
            arena_x + left : arena_x + left + width,
        ]
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
                (
                    example
                    for example in examples
                    if str(getattr(example, "example_id", ""))
                    == str(item.matched_example_id or "")
                ),
                None,
            )
            if prefer_non_danger and (
                selected is None
                or getattr(selected, "category", None) is TileClass.DANGER
            ):
                allowed = {
                    TileClass.WALKABLE,
                    TileClass.WALKABLE_WITH_JUTSU,
                    TileClass.BLOCKING_OBJECT,
                    TileClass.TRANSITION,
                    TileClass.WALL,
                }
                candidates = [
                    example
                    for example in examples
                    if getattr(example, "category", None) in allowed
                    and getattr(example, "crop_path", None) is not None
                ]
                extractor = getattr(perception, "extractor", None)
                if current is not None and extractor is not None and candidates:
                    inset = max(
                        0,
                        min(8, int(getattr(perception.config, "crop_inset_px", 2))),
                    )
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
            crop = cv2.resize(
                crop,
                (CELL_SIZE_PX, CELL_SIZE_PX),
                interpolation=cv2.INTER_AREA,
            )
        return crop.copy()

    def _metrics(self, current: np.ndarray, baseline: np.ndarray):
        if current.shape != baseline.shape:
            baseline = cv2.resize(
                baseline,
                (current.shape[1], current.shape[0]),
                interpolation=cv2.INTER_AREA,
            )
        cur_lab = cv2.cvtColor(current, cv2.COLOR_BGR2LAB).astype(np.int16)
        base_lab = cv2.cvtColor(baseline, cv2.COLOR_BGR2LAB).astype(np.int16)
        lab_delta = np.linalg.norm(cur_lab - base_lab, axis=2)
        cur_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        base_gray = cv2.cvtColor(baseline, cv2.COLOR_BGR2GRAY)
        gray_delta = cv2.absdiff(cur_gray, base_gray)
        threshold = float(self.config.pixel_delta_threshold)
        mask = np.where(
            (lab_delta >= threshold) | (gray_delta >= max(10, int(threshold))),
            255,
            0,
        ).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        component, ratio, area, width, height, _ = self._largest_component(mask)
        edge = float(
            np.mean(
                cv2.absdiff(
                    cv2.Canny(cur_gray, 45, 135),
                    cv2.Canny(base_gray, 45, 135),
                )
            )
        ) / 255.0
        color = min(1.0, float(np.mean(lab_delta)) / 80.0)
        return (
            ratio,
            area,
            width,
            height,
            edge,
            color,
            cv2.absdiff(current, baseline),
            component,
        )

    @staticmethod
    def _largest_component(
        mask: np.ndarray | None,
    ) -> tuple[np.ndarray | None, float, int, int, int, tuple[int, int, int, int] | None]:
        if mask is None or mask.size == 0:
            return None, 0.0, 0, 0, 0, None
        binary = np.where(mask > 0, 255, 0).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        if count <= 1:
            return np.zeros_like(binary), 0.0, 0, 0, 0, None
        index = max(range(1, count), key=lambda value: int(stats[value, cv2.CC_STAT_AREA]))
        left = int(stats[index, cv2.CC_STAT_LEFT])
        top = int(stats[index, cv2.CC_STAT_TOP])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        area = int(stats[index, cv2.CC_STAT_AREA])
        component = np.where(labels == index, 255, 0).astype(np.uint8)
        ratio = float(area) / float(component.size)
        return component, ratio, area, width, height, (left, top, width, height)

    @staticmethod
    def _temporal(previous: np.ndarray | None, current: np.ndarray) -> float:
        if previous is None or previous.shape != current.shape:
            return 1.0
        return float(
            np.mean(
                cv2.absdiff(
                    cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY),
                    cv2.cvtColor(current, cv2.COLOR_BGR2GRAY),
                )
            )
        ) / 255.0

    @staticmethod
    def _candidate_cells(candidate: CandidateObservation) -> frozenset[GridCell]:
        return frozenset(set(candidate.cells_touched) | {candidate.anchor_cell})

    @staticmethod
    def _bbox_coverage(
        candidates: Iterable[CandidateObservation],
        item: TileEvidence,
    ) -> float:
        cell_left, cell_top, cell_width, cell_height = item.bbox
        best = 0.0
        for candidate in candidates:
            if candidate.bbox is None:
                continue
            left, top, width, height = candidate.bbox
            overlap_width = max(
                0,
                min(left + width, cell_left + cell_width) - max(left, cell_left),
            )
            overlap_height = max(
                0,
                min(top + height, cell_top + cell_height) - max(top, cell_top),
            )
            best = max(
                best,
                float(overlap_width * overlap_height)
                / float(CELL_SIZE_PX * CELL_SIZE_PX),
            )
        return min(1.0, best)

    @staticmethod
    def _neighbors(cell: GridCell):
        return tuple(
            GridCell(cell.x + dx, cell.y + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if dx or dy
        )

    @staticmethod
    def _cardinal_neighbors(cell: GridCell):
        return (
            GridCell(cell.x - 1, cell.y),
            GridCell(cell.x + 1, cell.y),
            GridCell(cell.x, cell.y - 1),
            GridCell(cell.x, cell.y + 1),
        )

    @staticmethod
    def _mask_player(
        mask: np.ndarray | None,
        item: TileEvidence,
        player_rect: tuple[int, int, int, int] | None,
    ) -> tuple[np.ndarray | None, int]:
        if mask is None or player_rect is None:
            return mask, 0
        cell_left, cell_top, cell_width, cell_height = item.bbox
        player_left, player_top, player_width, player_height = player_rect
        overlap_left = max(cell_left, player_left)
        overlap_top = max(cell_top, player_top)
        overlap_right = min(cell_left + cell_width, player_left + player_width)
        overlap_bottom = min(cell_top + cell_height, player_top + player_height)
        if overlap_left >= overlap_right or overlap_top >= overlap_bottom:
            return mask, 0
        result = mask.copy()
        x0 = max(0, overlap_left - cell_left)
        y0 = max(0, overlap_top - cell_top)
        x1 = min(cell_width, overlap_right - cell_left)
        y1 = min(cell_height, overlap_bottom - cell_top)
        removed = int(np.count_nonzero(result[y0:y1, x0:x1]))
        result[y0:y1, x0:x1] = 0
        return result, removed

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
        if item.category in {
            TileClass.DANGER,
            TileClass.PLAYER,
            TileClass.IGNORE_DYNAMIC,
        }:
            return False
        if cell in raw_occupied or any(
            cell.chebyshev_distance(danger) <= 1 for danger in danger_cells
        ):
            return False
        if self._temporal(self._previous.get(cell), crop) > self.config.baseline_stability:
            return False
        if reference is not None:
            ratio, area, *_ = self._metrics(crop, reference)
            if ratio > self.config.weak_ratio or area >= self.config.blob_area_min:
                return False
        samples = self._samples.setdefault(
            cell,
            deque(maxlen=self.config.baseline_samples),
        )
        samples.append(crop.copy())
        if len(samples) < self.config.baseline_samples:
            return False
        self.exact_baselines[cell] = np.median(
            np.stack(tuple(samples)),
            axis=0,
        ).astype(np.uint8)
        return True

    def _learn_scene_recovery_baseline(
        self,
        cell: GridCell,
        crop: np.ndarray,
        item: TileEvidence,
        raw_occupied: set[GridCell],
    ) -> bool:
        """Re-anchor a screen cell after a coherent viewport/background shift."""

        if cell not in self._scene_recovery_cells:
            return False
        if item.category in {TileClass.PLAYER, TileClass.IGNORE_DYNAMIC} or cell in raw_occupied:
            self._samples.pop(cell, None)
            return False
        if self._temporal(self._previous.get(cell), crop) > self.config.baseline_stability:
            self._samples.pop(cell, None)
            return False
        samples = self._samples.setdefault(
            cell,
            deque(maxlen=self.config.baseline_samples),
        )
        samples.append(crop.copy())
        if len(samples) < self.config.baseline_samples:
            return False
        self.exact_baselines[cell] = np.median(
            np.stack(tuple(samples)),
            axis=0,
        ).astype(np.uint8)
        self._scene_recovery_cells.discard(cell)
        self._samples.pop(cell, None)
        return True

    @staticmethod
    def _class_reference_reliable(
        source: DiffSource,
        ratio: float,
        area: int,
        width: int,
        height: int,
    ) -> bool:
        if source is DiffSource.EXACT_CELL_BASELINE:
            return True
        if source is not DiffSource.CLASS_REFERENCE:
            return False
        return bool(
            ratio <= 0.55
            and area <= int(CELL_SIZE_PX * CELL_SIZE_PX * 0.75)
            and not (width >= CELL_SIZE_PX - 4 and height >= CELL_SIZE_PX - 4)
        )

    def _detect_boundary_scene_shift(
        self,
        observed: dict[GridCell, CellOccupancy],
    ) -> set[GridCell]:
        """Detect coherent full-cell changes entering from a viewport edge."""

        if not observed:
            return set()
        xs = [cell.x for cell in observed]
        ys = [cell.y for cell in observed]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        row_count = max_y - min_y + 1
        severe = {
            cell
            for cell, item in observed.items()
            if item.diff_source is DiffSource.EXACT_CELL_BASELINE
            and item.true_changed_ratio >= 0.60
            and item.largest_blob_area >= 2500
            and item.blob_width >= CELL_SIZE_PX - 16
            and item.blob_height >= CELL_SIZE_PX - 16
        }
        if not severe:
            return set()
        minimum_column_hits = max(3, int(np.ceil(row_count * 0.75)))
        seed_columns = {
            boundary_x
            for boundary_x in (min_x, max_x)
            if sum(cell.x == boundary_x for cell in severe) >= minimum_column_hits
        }
        if not seed_columns:
            return set()
        seeds = {cell for cell in severe if cell.x in seed_columns}
        selected = set(seeds)
        queue = list(seeds)
        while queue:
            current = queue.pop()
            for neighbor in self._neighbors(current):
                if neighbor in severe and neighbor not in selected:
                    selected.add(neighbor)
                    queue.append(neighbor)
        return selected

    def observe(
        self,
        *,
        frame: np.ndarray,
        state: Any,
        candidates: tuple[CandidateObservation, ...],
        evidence: dict[GridCell, TileEvidence],
        danger_fresh: bool,
        player_rect: tuple[int, int, int, int] | None = None,
    ) -> tuple[dict[GridCell, CellOccupancy], tuple[GridCell, ...]]:
        self.last_player_rect = player_rect
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
        self.last_scene_shift_cells = ()
        for item in evidence.values():
            crop = self._crop(frame, state, item)
            if crop is None:
                continue
            reference = self._reference(item, crop)
            if self._learn_scene_recovery_baseline(
                item.cell,
                crop,
                item,
                raw_occupied,
            ):
                baseline_ready.append(item.cell)
            elif self._learn_baseline(
                item.cell,
                crop,
                item,
                raw_occupied,
                danger_cells,
                reference,
            ):
                baseline_ready.append(item.cell)

            baseline = self.exact_baselines.get(item.cell)
            source = DiffSource.EXACT_CELL_BASELINE
            if baseline is None:
                baseline = reference
                source = (
                    DiffSource.CLASS_REFERENCE
                    if baseline is not None
                    else DiffSource.NONE
                )
            ratio = color = edge = 0.0
            area = width = height = 0
            diff = mask = None
            blob_bbox = None
            player_masked_pixels = 0
            if baseline is not None:
                (
                    ratio,
                    area,
                    width,
                    height,
                    edge,
                    color,
                    diff,
                    mask,
                ) = self._metrics(crop, baseline)
                mask, player_masked_pixels = self._mask_player(
                    mask,
                    item,
                    player_rect,
                )
                (
                    mask,
                    ratio,
                    area,
                    width,
                    height,
                    blob_bbox,
                ) = self._largest_component(mask)
                if area == 0:
                    edge = 0.0
                    color = 0.0
            coverage = self._bbox_coverage(candidates, item)
            danger_prior = item.similarity if item.cell in danger_cells else 0.0
            reference_reliable = self._class_reference_reliable(
                source,
                ratio,
                area,
                width,
                height,
            )
            authoritative = source is DiffSource.EXACT_CELL_BASELINE
            recovering = item.cell in self._scene_recovery_cells
            structural = (
                reference_reliable
                and not recovering
                and ratio >= self.config.suspect_ratio
                and area >= self.config.blob_area_min
                and width >= self.config.blob_width_min
                and height >= self.config.blob_height_min
            )
            strong = (
                reference_reliable
                and not recovering
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
                score = min(self.config.class_reference_score_cap, score * 0.55)
            if not reference_reliable or recovering:
                score = 0.0
            occupied_now = bool(authoritative and (structural or strong))
            weak_now = bool(
                reference_reliable
                and not recovering
                and (ratio >= self.config.weak_ratio or structural or strong)
            )
            votes = self._votes.setdefault(item.cell, deque(maxlen=3))
            votes.append(occupied_now)
            state_value = (
                OccupancyState.OCCUPIED
                if occupied_now
                else OccupancyState.WEAK
                if weak_now
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
                blob_bbox=blob_bbox,
                player_masked_pixels=player_masked_pixels,
                reference_authoritative=authoritative,
            )
            self._previous[item.cell] = crop.copy()

        shifted = self._detect_boundary_scene_shift(observed)
        if shifted:
            self.scene_shift_generation += 1
            self.last_scene_shift_cells = tuple(
                sorted(shifted, key=lambda cell: (cell.y, cell.x))
            )
            for cell in shifted:
                self.exact_baselines.pop(cell, None)
                self._samples.pop(cell, None)
                self._votes.pop(cell, None)
                self._scene_recovery_cells.add(cell)
                item = observed[cell]
                item.state = OccupancyState.EMPTY
                item.occupancy_score = 0.0
                item.danger_prior = 0.0
                item.persistence = 0
                item.mask = np.zeros((CELL_SIZE_PX, CELL_SIZE_PX), dtype=np.uint8)
                item.blob_bbox = None

        self.last_cells = observed
        return observed, tuple(baseline_ready)

    def _masks_touch(
        self,
        left: CellOccupancy,
        right: CellOccupancy,
    ) -> bool:
        if left.mask is None or right.mask is None:
            return False
        dx = right.cell.x - left.cell.x
        dy = right.cell.y - left.cell.y
        if abs(dx) + abs(dy) != 1:
            return False
        band = self.config.mask_edge_band_px
        if dx == 1:
            first = np.any(left.mask[:, -band:] > 0, axis=1)
            second = np.any(right.mask[:, :band] > 0, axis=1)
        elif dx == -1:
            first = np.any(left.mask[:, :band] > 0, axis=1)
            second = np.any(right.mask[:, -band:] > 0, axis=1)
        elif dy == 1:
            first = np.any(left.mask[-band:, :] > 0, axis=0)
            second = np.any(right.mask[:band, :] > 0, axis=0)
        else:
            first = np.any(left.mask[:band, :] > 0, axis=0)
            second = np.any(right.mask[-band:, :] > 0, axis=0)
        expanded = np.convolve(first.astype(np.uint8), np.ones(3, dtype=np.uint8), mode="same") > 0
        return int(np.count_nonzero(expanded & second)) >= self.config.mask_edge_contact_px

    def _group_geometry_valid(self, group: set[GridCell]) -> bool:
        if not group or len(group) > self.config.cluster_max_cells:
            return False
        width = max(cell.x for cell in group) - min(cell.x for cell in group) + 1
        height = max(cell.y for cell in group) - min(cell.y for cell in group) + 1
        return bool(
            width <= self.config.cluster_max_width_cells
            and height <= self.config.cluster_max_height_cells
        )

    @staticmethod
    def _global_blob_bbox(item: CellOccupancy) -> tuple[int, int, int, int]:
        cell_left, cell_top, cell_width, cell_height = item.evidence.bbox
        if item.blob_bbox is None:
            return cell_left, cell_top, cell_width, cell_height
        left, top, width, height = item.blob_bbox
        return cell_left + left, cell_top + top, width, height

    @staticmethod
    def _foot_from_items(
        items: tuple[CellOccupancy, ...],
    ) -> tuple[tuple[float, float], GridCell]:
        points: list[tuple[int, int, GridCell]] = []
        for item in items:
            if item.mask is None:
                continue
            ys, xs = np.where(item.mask > 0)
            if xs.size == 0:
                continue
            cell_left, cell_top, _, _ = item.evidence.bbox
            points.extend(
                (int(cell_left + x), int(cell_top + y), item.cell)
                for x, y in zip(xs.tolist(), ys.tolist())
            )
        if not points:
            fallback = max(items, key=lambda item: (item.cell.y, item.cell.x))
            left, top, width, height = fallback.evidence.bbox
            return (left + width / 2.0, top + height), fallback.cell
        bottom = max(y for _, y, _ in points)
        bottom_points = [(x, cell) for x, y, cell in points if y >= bottom - 2]
        x_values = sorted(x for x, _ in bottom_points)
        foot_x = float(x_values[len(x_values) // 2])
        matching_cells = [cell for x, cell in bottom_points if abs(float(x) - foot_x) <= 3.0]
        foot_cell = matching_cells[len(matching_cells) // 2] if matching_cells else bottom_points[0][1]
        return (foot_x, float(bottom)), foot_cell

    def clusters(
        self,
        cells: dict[GridCell, CellOccupancy],
        candidates: tuple[CandidateObservation, ...],
    ) -> tuple[OccupancyCluster, ...]:
        seeds = {
            cell
            for cell, item in cells.items()
            if item.state is OccupancyState.OCCUPIED
            and item.diff_source is DiffSource.EXACT_CELL_BASELINE
            and item.mask is not None
            and item.largest_blob_area >= self.config.blob_area_min
        }
        support = {
            cell
            for cell, item in cells.items()
            if item.mask is not None
            and item.state is OccupancyState.WEAK
            and (
                (
                    item.diff_source is DiffSource.EXACT_CELL_BASELINE
                    and item.occupancy_score >= 0.24
                )
                or (
                    item.diff_source is DiffSource.CLASS_REFERENCE
                    and item.danger_prior >= self.config.danger_confidence
                    and item.occupancy_score > 0.0
                )
            )
        }
        eligible = seeds | support
        consumed: set[GridCell] = set()
        result: list[OccupancyCluster] = []
        rejected: list[dict[str, Any]] = []
        for start in sorted(seeds, key=lambda cell: (cell.y, cell.x)):
            if start in consumed:
                continue
            group = {start}
            queue = [start]
            consumed.add(start)
            contact_edges = 0
            while queue:
                current = queue.pop()
                for neighbor in self._cardinal_neighbors(current):
                    if neighbor not in eligible or neighbor in consumed:
                        continue
                    if not self._masks_touch(cells[current], cells[neighbor]):
                        continue
                    proposed = set(group)
                    proposed.add(neighbor)
                    if not self._group_geometry_valid(proposed):
                        continue
                    consumed.add(neighbor)
                    group.add(neighbor)
                    queue.append(neighbor)
                    contact_edges += 1
            if not self._group_geometry_valid(group):
                rejected.append(
                    {
                        "reason": "CLUSTER_GEOMETRY_REJECTED",
                        "cells": tuple(sorted(group, key=lambda cell: (cell.y, cell.x))),
                    }
                )
                continue
            items = tuple(cells[cell] for cell in group)
            authoritative_cells = sum(
                item.diff_source is DiffSource.EXACT_CELL_BASELINE
                and item.state is OccupancyState.OCCUPIED
                for item in items
            )
            if authoritative_cells < 1:
                continue
            boxes = [self._global_blob_bbox(item) for item in items]
            left = min(box[0] for box in boxes)
            top = min(box[1] for box in boxes)
            right = max(box[0] + box[2] for box in boxes)
            bottom = max(box[1] + box[3] for box in boxes)
            foot, foot_cell = self._foot_from_items(items)
            raw_ids = {
                candidate.track_id
                for candidate in candidates
                if candidate.track_id >= 0
                and self._candidate_cells(candidate) & group
            }
            result.append(
                OccupancyCluster(
                    local_id=len(result) + 1,
                    cells=frozenset(group),
                    bbox=(left, top, right - left, bottom - top),
                    foot_point=foot,
                    foot_cell=foot_cell,
                    occupancy_score=max(item.occupancy_score for item in items),
                    danger_prior=max(item.danger_prior for item in items),
                    true_changed_ratio=max(item.true_changed_ratio for item in items),
                    largest_blob_area=max(item.largest_blob_area for item in items),
                    raw_track_ids=frozenset(raw_ids),
                    cell_observations=items,
                    mask_contact_edges=contact_edges,
                    authoritative_cells=authoritative_cells,
                )
            )
        result.sort(
            key=lambda item: (
                -item.danger_prior,
                -item.occupancy_score,
                item.foot_cell.y,
                item.foot_cell.x,
            )
        )
        self.last_rejected_clusters = tuple(rejected)
        self.last_clusters = tuple(result)
        return self.last_clusters
