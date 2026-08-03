from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np

from .pr27_fixed_grid import FixedNativeGridCalibration, NativeRect


class SelfVisualState(str, Enum):
    SELF_VISUAL_UNCONFIRMED = "SELF_VISUAL_UNCONFIRMED"
    SELF_TRACKED = "SELF_TRACKED"
    SELF_TEMPORARILY_UNCERTAIN = "SELF_TEMPORARILY_UNCERTAIN"
    SELF_LOST_CRITICAL = "SELF_LOST_CRITICAL"


@dataclass(frozen=True, slots=True)
class SelfVisualObservation:
    found: bool
    bbox: NativeRect | None
    feet_anchor: tuple[float, float] | None
    anchor_inside_fixed_cell: bool
    template_score: float
    confidence: float
    state: SelfVisualState
    reason: str


class FixedSelfDetector:
    """Verify SELF only inside the audited fixed cell and a small sprite margin."""

    def __init__(self, grid: FixedNativeGridCalibration) -> None:
        self.grid = grid
        self.template: np.ndarray | None = None
        self.last_bbox: NativeRect | None = None
        self.last_anchor: tuple[float, float] | None = None
        self.missing_frames = 0

    @staticmethod
    def _debug_overlay_exclusion(crop: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]
        highly_saturated_bright = (saturation >= 170) & (value >= 180)
        gray_lines = (saturation <= 25) & (value >= 40) & (value <= 120)
        mask = np.where(highly_saturated_bright | gray_lines, 255, 0).astype(np.uint8)
        return cv2.dilate(mask, np.ones((2, 2), np.uint8), iterations=1)

    @staticmethod
    def _normalized_template(crop: np.ndarray, mask: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (20, 48), interpolation=cv2.INTER_AREA)
        resized_mask = cv2.resize(mask, (20, 48), interpolation=cv2.INTER_NEAREST)
        return np.where(resized_mask > 0, resized, 0).astype(np.uint8)

    @staticmethod
    def _template_similarity(left: np.ndarray | None, right: np.ndarray) -> float:
        if left is None or left.shape != right.shape:
            return 0.5
        leftf = left.astype(np.float32).reshape(-1)
        rightf = right.astype(np.float32).reshape(-1)
        leftf -= float(leftf.mean())
        rightf -= float(rightf.mean())
        denominator = float(np.linalg.norm(leftf) * np.linalg.norm(rightf))
        if denominator <= 1e-6:
            return 0.0
        return float(max(0.0, min(1.0, (np.dot(leftf, rightf) / denominator + 1.0) / 2.0)))

    def observe(self, frame_bgr: np.ndarray) -> SelfVisualObservation:
        search = self.grid.self_search_rect()
        fixed = self.grid.self_cell_rect()
        crop = frame_bgr[search.top : search.bottom, search.left : search.right]
        if crop.size == 0:
            return SelfVisualObservation(
                False, None, None, False, 0.0, 0.0,
                SelfVisualState.SELF_LOST_CRITICAL,
                "fixed SELF search region is outside frame",
            )
        height, width = crop.shape[:2]
        border = max(3, min(7, min(height, width) // 10))
        border_pixels = np.concatenate(
            (
                crop[:border].reshape(-1, 3),
                crop[-border:].reshape(-1, 3),
                crop[:, :border].reshape(-1, 3),
                crop[:, -border:].reshape(-1, 3),
            ),
            axis=0,
        )
        background_bgr = np.median(border_pixels, axis=0).astype(np.uint8)
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.int16)
        background_lab = cv2.cvtColor(
            background_bgr.reshape(1, 1, 3), cv2.COLOR_BGR2LAB
        ).astype(np.int16)[0, 0]
        color_distance = np.linalg.norm(lab - background_lab, axis=2)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 110)
        foreground = np.where((color_distance >= 15.0) | (edges > 0), 255, 0).astype(np.uint8)
        foreground[self._debug_overlay_exclusion(crop) > 0] = 0
        kernel = np.ones((3, 3), np.uint8)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=2)
        count, labels, stats, _centroids = cv2.connectedComponentsWithStats(foreground, 8)
        candidates: list[tuple[float, NativeRect, tuple[float, float], np.ndarray]] = []
        expected = ((fixed.left + fixed.right) / 2.0, fixed.bottom - 8.0)
        for label in range(1, count):
            local_x, local_y, component_width, component_height, pixels = [
                int(value) for value in stats[label]
            ]
            if pixels < 35 or component_width < 5 or component_height < 12:
                continue
            if component_width > 58 or component_height > 90:
                continue
            native_rect = NativeRect(
                search.left + local_x,
                search.top + local_y,
                search.left + local_x + component_width,
                search.top + local_y + component_height,
            )
            feet = ((native_rect.left + native_rect.right) / 2.0, native_rect.bottom - 1.0)
            if not fixed.contains(feet):
                continue
            component_mask = np.where(
                labels[
                    local_y : local_y + component_height,
                    local_x : local_x + component_width,
                ] == label,
                255,
                0,
            ).astype(np.uint8)
            component_crop = crop[
                local_y : local_y + component_height,
                local_x : local_x + component_width,
            ]
            normalized = self._normalized_template(component_crop, component_mask)
            template_score = self._template_similarity(self.template, normalized)
            proximity = max(
                0.0,
                1.0 - math.hypot(feet[0] - expected[0], feet[1] - expected[1]) / 56.0,
            )
            aspect = component_width / max(1.0, float(component_height))
            geometry = max(0.0, 1.0 - abs(aspect - 0.5) / 0.8)
            persistence = 0.5
            if self.last_anchor is not None:
                persistence = max(
                    0.0,
                    1.0 - math.hypot(
                        feet[0] - self.last_anchor[0], feet[1] - self.last_anchor[1]
                    ) / 24.0,
                )
            score = 0.34 * template_score + 0.30 * proximity + 0.20 * geometry + 0.16 * persistence
            candidates.append((score, native_rect, feet, normalized))
        if not candidates:
            self.missing_frames += 1
            state = (
                SelfVisualState.SELF_TEMPORARILY_UNCERTAIN
                if self.last_bbox is not None and self.missing_frames <= 3
                else SelfVisualState.SELF_LOST_CRITICAL
            )
            return SelfVisualObservation(
                False,
                self.last_bbox if self.missing_frames <= 3 else None,
                self.last_anchor if self.missing_frames <= 3 else None,
                False,
                0.0,
                0.0,
                state,
                "no template-compatible body core inside fixed SELF cell",
            )
        score, bbox, feet, normalized = max(candidates, key=lambda item: item[0])
        if score < 0.34:
            self.missing_frames += 1
            return SelfVisualObservation(
                False, None, None, False, score, score,
                SelfVisualState.SELF_VISUAL_UNCONFIRMED,
                "fixed-cell body candidate did not satisfy SELF confidence",
            )
        self.missing_frames = 0
        self.last_bbox = bbox
        self.last_anchor = feet
        if self.template is None:
            self.template = normalized
        else:
            self.template = np.clip(
                self.template.astype(np.float32) * 0.92
                + normalized.astype(np.float32) * 0.08,
                0,
                255,
            ).astype(np.uint8)
        return SelfVisualObservation(
            True,
            bbox,
            feet,
            fixed.contains(feet),
            score,
            score,
            SelfVisualState.SELF_TRACKED,
            "SELF body visually confirmed inside immutable fixed cell",
        )


__all__ = ["FixedSelfDetector", "SelfVisualObservation", "SelfVisualState"]
