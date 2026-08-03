from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

import cv2
import numpy as np

from .pr27_fixed_grid import FixedNativeGridCalibration, NativeRect


class CandidateClass(str, Enum):
    BACKGROUND = "BACKGROUND"
    ANIMATED_BACKGROUND = "ANIMATED_BACKGROUND"
    UNKNOWN_VISUAL_CHANGE = "UNKNOWN_VISUAL_CHANGE"
    ENTITY_CANDIDATE = "ENTITY_CANDIDATE"
    HUMANOID_CANDIDATE = "HUMANOID_CANDIDATE"
    OPPONENT_CANDIDATE = "OPPONENT_CANDIDATE"
    HOSTILITY_PENDING = "HOSTILITY_PENDING"
    HOSTILE_CONFIRMED = "HOSTILE_CONFIRMED"
    NPC = "NPC"
    SELF = "SELF"


@dataclass(slots=True)
class EntityCandidate:
    candidate_id: int
    bbox: NativeRect
    feet_anchor: tuple[float, float]
    relative_cell: tuple[int, int] | None
    area: int
    component_pixels: int
    occupancy: float
    aspect_ratio: float
    solidity: float
    vertical_score: float
    feet_support_score: float
    rigidity_score: float
    entity_confidence: float
    humanoid_confidence: float
    candidate_class: CandidateClass
    rejection_reason: str | None = None
    descriptor: np.ndarray = field(default_factory=lambda: np.zeros(32, dtype=np.float32))

    @property
    def center(self) -> tuple[float, float]:
        return (
            (self.bbox.left + self.bbox.right) / 2.0,
            (self.bbox.top + self.bbox.bottom) / 2.0,
        )


class EntityValidator:
    """Strict residual-body validator.

    A changed patch is not an entity merely because it moves. It must preserve a
    compact, vertically structured body core with a stable feet anchor.
    """

    def __init__(
        self,
        grid: FixedNativeGridCalibration,
        *,
        minimum_pixels: int = 70,
        maximum_pixels: int = 2600,
    ) -> None:
        self.grid = grid
        self.minimum_pixels = max(20, int(minimum_pixels))
        self.maximum_pixels = max(self.minimum_pixels, int(maximum_pixels))
        self._next_candidate_id = 1

    @staticmethod
    def _descriptor(frame_bgr: np.ndarray, mask: np.ndarray, rect: NativeRect) -> np.ndarray:
        crop = frame_bgr[rect.top : rect.bottom, rect.left : rect.right]
        crop_mask = mask[rect.top : rect.bottom, rect.left : rect.right]
        if crop.size == 0 or not np.any(crop_mask):
            return np.zeros(32, dtype=np.float32)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], crop_mask, [8, 4], [0, 180, 0, 256]).reshape(-1)
        norm = float(np.linalg.norm(hist))
        return (hist / norm).astype(np.float32) if norm > 0 else hist.astype(np.float32)

    @staticmethod
    def _solidity(contour: np.ndarray) -> float:
        area = cv2.contourArea(contour)
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        return float(area / hull_area) if hull_area > 0 else 0.0

    @staticmethod
    def _feet_support(component_mask: np.ndarray) -> float:
        height = component_mask.shape[0]
        if height <= 0:
            return 0.0
        bottom = component_mask[max(0, height - max(3, height // 6)) :, :] > 0
        if bottom.size == 0:
            return 0.0
        occupied_columns = np.any(bottom, axis=0)
        return float(np.count_nonzero(occupied_columns) / max(1, occupied_columns.size))

    @staticmethod
    def _vertical_score(component_mask: np.ndarray) -> float:
        points = cv2.findNonZero(component_mask)
        if points is None or len(points) < 3:
            return 0.0
        points2 = points.reshape(-1, 2).astype(np.float32)
        covariance = np.cov(points2.T)
        values = np.linalg.eigvalsh(covariance)
        if values[-1] <= 1e-6:
            return 0.0
        elongation = float(values[-1] / max(1e-6, values[0]))
        return float(max(0.0, min(1.0, (elongation - 1.1) / 4.0)))

    @staticmethod
    def _rigidity_score(current_mask: np.ndarray, previous_mask: np.ndarray | None) -> float:
        if previous_mask is None or previous_mask.shape != current_mask.shape:
            return 0.5
        current = current_mask > 0
        previous = previous_mask > 0
        union = np.count_nonzero(current | previous)
        if union == 0:
            return 0.0
        iou = np.count_nonzero(current & previous) / union
        return float(max(0.0, min(1.0, iou)))

    def detect(
        self,
        frame_bgr: np.ndarray,
        residual_mask: np.ndarray,
        *,
        animated_background_mask: np.ndarray | None = None,
        trainer_mask: np.ndarray | None = None,
        self_mask: np.ndarray | None = None,
        previous_residual_mask: np.ndarray | None = None,
    ) -> tuple[EntityCandidate, ...]:
        if residual_mask.shape != frame_bgr.shape[:2]:
            raise ValueError("PR27_ENTITY_MASK_SHAPE_MISMATCH")
        working = np.where(residual_mask > 0, 255, 0).astype(np.uint8)
        for exclusion in (animated_background_mask, trainer_mask, self_mask):
            if exclusion is not None:
                if exclusion.shape != working.shape:
                    raise ValueError("PR27_ENTITY_EXCLUSION_SHAPE_MISMATCH")
                working[exclusion > 0] = 0

        kernel = np.ones((3, 3), dtype=np.uint8)
        working = cv2.morphologyEx(working, cv2.MORPH_OPEN, kernel)
        working = cv2.morphologyEx(working, cv2.MORPH_CLOSE, kernel, iterations=2)
        count, labels, stats, _centroids = cv2.connectedComponentsWithStats(working, 8)
        candidates: list[EntityCandidate] = []
        for label in range(1, count):
            left, top, width, height, pixels = [int(value) for value in stats[label]]
            if width <= 0 or height <= 0:
                continue
            rect = NativeRect(left, top, left + width, top + height)
            area = width * height
            occupancy = pixels / max(1, area)
            aspect = width / max(1.0, float(height))
            component = np.where(labels[top : top + height, left : left + width] == label, 255, 0).astype(np.uint8)
            contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contour = max(contours, key=cv2.contourArea) if contours else np.zeros((0, 1, 2), dtype=np.int32)
            solidity = self._solidity(contour) if len(contour) else 0.0
            vertical = self._vertical_score(component)
            feet_support = self._feet_support(component)
            previous_component = None
            if previous_residual_mask is not None and previous_residual_mask.shape == working.shape:
                previous_component = previous_residual_mask[top : top + height, left : left + width]
            rigidity = self._rigidity_score(component, previous_component)
            feet_anchor = (left + width / 2.0, top + height - 1.0)
            cell = self.grid.cell_for_native_point(*feet_anchor)
            relative = None if cell is None else cell.relative_key

            rejection: str | None = None
            if pixels < self.minimum_pixels:
                rejection = "BODY_CORE_TOO_FEW_PIXELS"
            elif pixels > self.maximum_pixels:
                rejection = "BODY_CORE_TOO_MANY_PIXELS"
            elif width < 6 or width > 48:
                rejection = "BODY_CORE_WIDTH_OUT_OF_RANGE"
            elif height < 14 or height > 82:
                rejection = "BODY_CORE_HEIGHT_OUT_OF_RANGE"
            elif not (0.16 <= aspect <= 1.25):
                rejection = "BODY_CORE_ASPECT_OUT_OF_RANGE"
            elif not (0.10 <= occupancy <= 0.78):
                rejection = "BODY_CORE_OCCUPANCY_OUT_OF_RANGE"
            elif solidity < 0.18:
                rejection = "BODY_CORE_SOLIDITY_LOW"
            elif feet_support < 0.08:
                rejection = "FEET_ANCHOR_UNSUPPORTED"

            geometry_score = (
                0.24 * max(0.0, 1.0 - abs(aspect - 0.55) / 0.70)
                + 0.22 * vertical
                + 0.18 * min(1.0, pixels / 500.0)
                + 0.14 * solidity
                + 0.12 * feet_support
                + 0.10 * rigidity
            )
            entity_confidence = max(0.0, min(1.0, geometry_score))
            humanoid_confidence = max(
                0.0,
                min(
                    1.0,
                    0.30 * vertical
                    + 0.25 * max(0.0, 1.0 - abs(aspect - 0.55) / 0.65)
                    + 0.20 * feet_support
                    + 0.15 * solidity
                    + 0.10 * rigidity,
                ),
            )
            if rejection is not None:
                candidate_class = CandidateClass.UNKNOWN_VISUAL_CHANGE
                entity_confidence *= 0.35
                humanoid_confidence *= 0.25
            elif humanoid_confidence >= 0.45 and entity_confidence >= 0.42:
                candidate_class = CandidateClass.HUMANOID_CANDIDATE
            else:
                candidate_class = CandidateClass.ENTITY_CANDIDATE

            candidate = EntityCandidate(
                candidate_id=self._next_candidate_id,
                bbox=rect,
                feet_anchor=feet_anchor,
                relative_cell=relative,
                area=area,
                component_pixels=pixels,
                occupancy=occupancy,
                aspect_ratio=aspect,
                solidity=solidity,
                vertical_score=vertical,
                feet_support_score=feet_support,
                rigidity_score=rigidity,
                entity_confidence=entity_confidence,
                humanoid_confidence=humanoid_confidence,
                candidate_class=candidate_class,
                rejection_reason=rejection,
                descriptor=self._descriptor(frame_bgr, working, rect),
            )
            self._next_candidate_id += 1
            candidates.append(candidate)
        return tuple(candidates)

    @staticmethod
    def mask_for_candidates(shape: tuple[int, int], candidates: Iterable[EntityCandidate]) -> np.ndarray:
        mask = np.zeros(shape, dtype=np.uint8)
        for candidate in candidates:
            rect = candidate.bbox
            mask[rect.top : rect.bottom, rect.left : rect.right] = 255
        return mask


__all__ = ["CandidateClass", "EntityCandidate", "EntityValidator"]
