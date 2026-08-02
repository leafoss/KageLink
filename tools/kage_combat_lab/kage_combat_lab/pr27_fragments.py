from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

import cv2
import numpy as np

from .pr27_model import (
    AppearanceDescriptor, CellDifference, CellSearchGroup,
    PR27Config, SpriteFragment, SpriteObservation,
)


class DescriptorFactory:
    @staticmethod
    def from_masked_crop(crop: np.ndarray, mask: np.ndarray) -> AppearanceDescriptor:
        if crop.size == 0 or mask.size == 0 or not np.any(mask):
            return AppearanceDescriptor(
                hsv_histogram=np.zeros((32,), dtype=np.float32),
                structure_vector=np.zeros((64,), dtype=np.float32),
                edge_density=0.0,
            )
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], mask, [8, 4], [0, 180, 0, 256]).flatten()
        norm = float(np.linalg.norm(hist))
        if norm > 1e-9:
            hist = hist / norm
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        structure = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA).astype(np.float32).flatten()
        structure -= float(np.mean(structure))
        structure_norm = float(np.linalg.norm(structure))
        if structure_norm > 1e-9:
            structure /= structure_norm
        edges = cv2.Canny(gray, 40, 120)
        edge_density = float(np.count_nonzero(edges & mask)) / max(1, int(np.count_nonzero(mask)))
        return AppearanceDescriptor(hist.astype(np.float32), structure.astype(np.float32), edge_density)

    @staticmethod
    def similarity(left: AppearanceDescriptor, right: AppearanceDescriptor) -> float:
        hist = float(np.dot(left.hsv_histogram, right.hsv_histogram))
        structure = float(np.dot(left.structure_vector, right.structure_vector))
        edge = 1.0 - min(1.0, abs(left.edge_density - right.edge_density))
        return max(0.0, min(1.0, 0.50 * hist + 0.35 * ((structure + 1.0) / 2.0) + 0.15 * edge))


class SpriteFragmentExtractor:
    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()

    def extract(
        self,
        arena_bgr: np.ndarray,
        groups: Iterable[CellSearchGroup],
        differences: Mapping[tuple[int, int], CellDifference],
    ) -> tuple[SpriteFragment, ...]:
        fragments: list[SpriteFragment] = []
        for group in groups:
            for cell in group.cells:
                evidence = differences[(cell.row, cell.column)]
                cell_crop = arena_bgr[cell.y : cell.y + cell.height, cell.x : cell.x + cell.width]
                for component in evidence.components:
                    x, y, width, height = component.local_bbox
                    if component.pixel_count < self.config.minimum_fragment_pixels:
                        continue
                    if (
                        width < self.config.minimum_fragment_width
                        and height < self.config.minimum_fragment_height
                    ):
                        continue
                    component_mask = evidence.difference_mask[y : y + height, x : x + width].copy()
                    if not np.any(component_mask):
                        continue
                    crop = cell_crop[y : y + height, x : x + width].copy()
                    contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    contour = max(contours, key=cv2.contourArea) if contours else np.empty((0, 1, 2), dtype=np.int32)
                    fragments.append(
                        SpriteFragment(
                            fragment_id=len(fragments) + 1,
                            cell=cell,
                            local_bbox=(x, y, width, height),
                            native_bbox=(cell.x + x, cell.y + y, width, height),
                            mask=component_mask,
                            crop=crop,
                            contour=contour,
                            pixel_count=component.pixel_count,
                            descriptor=DescriptorFactory.from_masked_crop(crop, component_mask),
                        )
                    )
        return tuple(fragments)


class SpriteAssembler:
    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()

    @staticmethod
    def _expanded_intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int], gap: int) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (
            ax + aw + gap < bx
            or bx + bw + gap < ax
            or ay + ah + gap < by
            or by + bh + gap < ay
        )

    def assemble(
        self,
        arena_bgr: np.ndarray,
        groups: Iterable[CellSearchGroup],
        fragments: Iterable[SpriteFragment],
    ) -> tuple[SpriteObservation, ...]:
        by_cell: dict[tuple[int, int], list[SpriteFragment]] = defaultdict(list)
        for fragment in fragments:
            by_cell[(fragment.cell.row, fragment.cell.column)].append(fragment)

        observations: list[SpriteObservation] = []
        for group in groups:
            group_fragments = [fragment for cell in group.cells for fragment in by_cell[(cell.row, cell.column)]]
            if not group_fragments:
                continue
            group_fragments.sort(key=lambda item: item.pixel_count, reverse=True)
            group_fragments = group_fragments[: self.config.maximum_fragments_per_group]
            parent = list(range(len(group_fragments)))

            def find(index: int) -> int:
                while parent[index] != index:
                    parent[index] = parent[parent[index]]
                    index = parent[index]
                return index

            def union(a: int, b: int) -> None:
                root_a, root_b = find(a), find(b)
                if root_a != root_b:
                    parent[root_b] = root_a

            for left_index, left in enumerate(group_fragments):
                for right_index in range(left_index + 1, len(group_fragments)):
                    right = group_fragments[right_index]
                    row_gap = abs(left.cell.row - right.cell.row)
                    column_gap = abs(left.cell.column - right.cell.column)
                    if max(row_gap, column_gap) > 1:
                        continue
                    if self._expanded_intersects(
                        left.native_bbox,
                        right.native_bbox,
                        self.config.fragment_join_gap_px,
                    ):
                        union(left_index, right_index)

            buckets: dict[int, list[SpriteFragment]] = defaultdict(list)
            for index, fragment in enumerate(group_fragments):
                buckets[find(index)].append(fragment)

            for bucket in buckets.values():
                pixel_count = sum(item.pixel_count for item in bucket)
                if pixel_count < self.config.minimum_observation_pixels:
                    continue
                left = min(item.native_bbox[0] for item in bucket)
                top = min(item.native_bbox[1] for item in bucket)
                right = max(item.native_bbox[0] + item.native_bbox[2] for item in bucket)
                bottom = max(item.native_bbox[1] + item.native_bbox[3] for item in bucket)
                width, height = max(1, right - left), max(1, bottom - top)
                if (
                    width < self.config.minimum_fragment_width
                    and height < self.config.minimum_fragment_height
                ):
                    continue
                combined_mask = np.zeros((height, width), dtype=np.uint8)
                for item in bucket:
                    x, y, item_width, item_height = item.native_bbox
                    local_x, local_y = x - left, y - top
                    region = combined_mask[local_y : local_y + item_height, local_x : local_x + item_width]
                    np.maximum(region, item.mask, out=region)
                crop = arena_bgr[top:bottom, left:right].copy()
                observations.append(
                    SpriteObservation(
                        observation_id=len(observations) + 1,
                        source_group_id=group.group_id,
                        fragments=tuple(bucket),
                        cells=frozenset((item.cell.row, item.cell.column) for item in bucket),
                        native_bbox=(left, top, width, height),
                        combined_mask=combined_mask,
                        crop=crop,
                        descriptor=DescriptorFactory.from_masked_crop(crop, combined_mask),
                    )
                )
        return tuple(observations)
