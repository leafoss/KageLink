from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable, Mapping, Sequence

import cv2
import numpy as np

from .pr27_model import (
    AppearanceDescriptor, CellDifference, CellSearchGroup, FragmentRole, GridCell,
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


class FragmentRoleClassifier:
    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()

    def classify(self, *, bbox: tuple[int, int, int, int], pixel_count: int) -> tuple[FragmentRole, str, float]:
        _, _, width, height = bbox
        area = max(1, width * height)
        aspect = width / max(1.0, float(height))
        fill = min(1.0, pixel_count / float(area))
        if pixel_count < self.config.minimum_fragment_pixels:
            return FragmentRole.NOISE, "pixel_count_below_minimum", 0.0
        if width < self.config.minimum_fragment_width and height < self.config.minimum_fragment_height:
            return FragmentRole.NOISE, "dimensions_below_minimum", 0.0
        if height <= self.config.body_ground_max_height and aspect >= self.config.body_ground_min_aspect:
            return FragmentRole.GROUND_LIKE, "wide_low_horizontal_component", 0.0
        if height <= 8 and width >= 12:
            return FragmentRole.GROUND_LIKE, "thin_horizontal_trail", 0.0
        if width > self.config.body_max_width or height > self.config.body_max_height or area > self.config.body_max_area:
            return FragmentRole.EFFECT_LIKE, "oversized_visual_effect", 0.0
        if width < self.config.body_min_width or height < self.config.body_min_height or area < self.config.body_min_area:
            return FragmentRole.NOISE, "not_enough_body_geometry", 0.0
        aspect_score = max(0.0, 1.0 - abs(aspect - 0.65) / 1.30)
        height_score = max(0.0, 1.0 - abs(height - 42.0) / 80.0)
        size_score = 1.0 if 180 <= area <= 5500 else max(0.0, 1.0 - abs(area - 2200.0) / 5000.0)
        fill_score = max(0.0, 1.0 - abs(fill - 0.55) / 0.70)
        score = 0.38 * aspect_score + 0.28 * height_score + 0.20 * size_score + 0.14 * fill_score
        if score < 0.26:
            return FragmentRole.NOISE, "weak_body_shape_score", score
        return FragmentRole.BODY_CANDIDATE, "vertical_compact_body_geometry", score


class SpriteFragmentExtractor:
    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.classifier = FragmentRoleClassifier(self.config)
        self.last_rejections: Counter[str] = Counter()

    def extract(
        self,
        arena_bgr: np.ndarray,
        groups: Iterable[CellSearchGroup],
        differences: Mapping[tuple[int, int], CellDifference],
    ) -> tuple[SpriteFragment, ...]:
        fragments: list[SpriteFragment] = []
        self.last_rejections.clear()
        for group in groups:
            for cell in group.cells:
                evidence = differences[(cell.row, cell.column)]
                cell_crop = arena_bgr[cell.y : cell.y + cell.height, cell.x : cell.x + cell.width]
                for component in evidence.components:
                    x, y, width, height = component.local_bbox
                    role, reason, body_score = self.classifier.classify(
                        bbox=component.local_bbox,
                        pixel_count=component.pixel_count,
                    )
                    if role is not FragmentRole.BODY_CANDIDATE:
                        self.last_rejections[f"{role.value}:{reason}"] += 1
                        continue
                    component_mask = evidence.difference_mask[y : y + height, x : x + width].copy()
                    if not np.any(component_mask):
                        self.last_rejections["NOISE:empty_component_mask"] += 1
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
                            role=role,
                            role_reason=reason,
                            body_score=body_score,
                        )
                    )
        return tuple(fragments)


class SpriteAssembler:
    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.last_rejections: Counter[str] = Counter()

    @staticmethod
    def _expanded_intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int], gap: int) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (ax + aw + gap < bx or bx + bw + gap < ax or ay + ah + gap < by or by + bh + gap < ay)

    @staticmethod
    def _bbox_union(items: Sequence[SpriteFragment]) -> tuple[int, int, int, int]:
        left = min(item.native_bbox[0] for item in items)
        top = min(item.native_bbox[1] for item in items)
        right = max(item.native_bbox[0] + item.native_bbox[2] for item in items)
        bottom = max(item.native_bbox[1] + item.native_bbox[3] for item in items)
        return left, top, max(1, right - left), max(1, bottom - top)

    @staticmethod
    def _cell_key_for_anchor(anchor: tuple[float, float], cells: Sequence[GridCell]) -> tuple[int, int] | None:
        for cell in cells:
            if cell.contains(anchor):
                return cell.row, cell.column
        return None

    def assemble(
        self,
        arena_bgr: np.ndarray,
        groups: Iterable[CellSearchGroup],
        fragments: Iterable[SpriteFragment],
        *,
        cells: Sequence[GridCell],
    ) -> tuple[SpriteObservation, ...]:
        self.last_rejections.clear()
        by_cell: dict[tuple[int, int], list[SpriteFragment]] = defaultdict(list)
        for fragment in fragments:
            if fragment.role is FragmentRole.BODY_CANDIDATE:
                by_cell[(fragment.cell.row, fragment.cell.column)].append(fragment)
        observations: list[SpriteObservation] = []
        for group in groups:
            group_fragments = [fragment for cell in group.cells for fragment in by_cell[(cell.row, cell.column)]]
            if not group_fragments:
                continue
            group_fragments.sort(key=lambda item: (item.body_score, item.pixel_count), reverse=True)
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
                    if max(abs(left.cell.row - right.cell.row), abs(left.cell.column - right.cell.column)) > 1:
                        continue
                    if self._expanded_intersects(left.native_bbox, right.native_bbox, self.config.fragment_join_gap_px):
                        union(left_index, right_index)
            buckets: dict[int, list[SpriteFragment]] = defaultdict(list)
            for index, fragment in enumerate(group_fragments):
                buckets[find(index)].append(fragment)
            for bucket in buckets.values():
                if sum(item.pixel_count for item in bucket) < self.config.minimum_observation_pixels:
                    self.last_rejections["observation_pixels_below_minimum"] += 1
                    continue
                primary = max(bucket, key=lambda item: (item.body_score, item.pixel_count))
                body_members = [item for item in bucket if item is primary or self._expanded_intersects(primary.native_bbox, item.native_bbox, 6)]
                body_bbox = self._bbox_union(body_members)
                body_left, body_top, body_width, body_height = body_bbox
                body_confidence = float(sum(item.body_score * item.pixel_count for item in body_members)) / max(
                    1, sum(item.pixel_count for item in body_members)
                )
                if body_confidence < self.config.body_lock_min_confidence:
                    self.last_rejections["body_confidence_below_lock_threshold"] += 1
                    continue
                body_anchor = (body_left + body_width / 2.0, body_top + body_height - 2.0)
                anchor_cell = self._cell_key_for_anchor(body_anchor, cells)
                if anchor_cell is None:
                    self.last_rejections["body_anchor_outside_grid"] += 1
                    continue
                left, top, width, height = self._bbox_union(bucket)
                combined_mask = np.zeros((height, width), dtype=np.uint8)
                for item in bucket:
                    x, y, item_width, item_height = item.native_bbox
                    local_x, local_y = x - left, y - top
                    region = combined_mask[local_y : local_y + item_height, local_x : local_x + item_width]
                    np.maximum(region, item.mask, out=region)
                crop = arena_bgr[top : top + height, left : left + width].copy()
                body_mask = np.zeros((body_height, body_width), dtype=np.uint8)
                for item in body_members:
                    x, y, item_width, item_height = item.native_bbox
                    local_x, local_y = x - body_left, y - body_top
                    region = body_mask[local_y : local_y + item_height, local_x : local_x + item_width]
                    np.maximum(region, item.mask, out=region)
                body_crop = arena_bgr[body_top : body_top + body_height, body_left : body_left + body_width].copy()
                observations.append(
                    SpriteObservation(
                        observation_id=len(observations) + 1,
                        source_group_id=group.group_id,
                        fragments=tuple(bucket),
                        cells=frozenset((item.cell.row, item.cell.column) for item in bucket),
                        native_bbox=(left, top, width, height),
                        combined_mask=combined_mask,
                        crop=crop,
                        descriptor=DescriptorFactory.from_masked_crop(body_crop, body_mask),
                        body_bbox=body_bbox,
                        body_anchor=body_anchor,
                        anchor_cell=anchor_cell,
                        body_confidence=body_confidence,
                    )
                )
        return tuple(observations)
