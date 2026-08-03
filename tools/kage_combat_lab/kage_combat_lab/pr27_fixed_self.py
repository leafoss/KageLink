from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

import cv2
import numpy as np

from .pr27_fixed_grid import FixedNativeGridCalibration, NativeRect


class SelfVisualState(str, Enum):
    SELF_VISUAL_UNCONFIRMED = "SELF_VISUAL_UNCONFIRMED"
    SELF_TRACKED = "SELF_TRACKED"
    SELF_PRESERVED_LOW_SCORE = "SELF_PRESERVED_LOW_SCORE"
    SELF_TEMPORARILY_UNCERTAIN = "SELF_TEMPORARILY_UNCERTAIN"
    SELF_OCCLUDED_BY_BODY = "SELF_OCCLUDED_BY_BODY"
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
    matched_template_id: int | None = None
    preserved_from_frame: int | None = None
    missing_frames: int = 0
    template_update_allowed: bool = False
    template_update_block_reason: str | None = None
    protected_mask_pixels: int = 0


@dataclass(slots=True)
class SelfTemplate:
    template_id: int
    gray: np.ndarray
    edges: np.ndarray
    histogram: np.ndarray
    silhouette: np.ndarray
    bbox_size: tuple[int, int]
    feet_anchor_offset: tuple[float, float]
    confidence: float
    source_state: str
    observations: int = 1


class SelfTemplateBank:
    def __init__(self, *, max_templates: int = 12) -> None:
        self.max_templates = max(2, int(max_templates))
        self.templates: list[SelfTemplate] = []
        self._next_id = 1

    @staticmethod
    def _cosine(left: np.ndarray, right: np.ndarray) -> float:
        if left.shape != right.shape or left.size == 0:
            return 0.0
        lf = left.astype(np.float32).reshape(-1)
        rf = right.astype(np.float32).reshape(-1)
        denominator = float(np.linalg.norm(lf) * np.linalg.norm(rf))
        if denominator <= 1e-9:
            return 0.0
        return float(max(0.0, min(1.0, np.dot(lf, rf) / denominator)))

    @staticmethod
    def _iou(left: np.ndarray, right: np.ndarray) -> float:
        if left.shape != right.shape:
            return 0.0
        l = left > 0
        r = right > 0
        union = int(np.count_nonzero(l | r))
        if union == 0:
            return 1.0
        return float(np.count_nonzero(l & r) / union)

    def match(
        self,
        gray: np.ndarray,
        edges: np.ndarray,
        histogram: np.ndarray,
        silhouette: np.ndarray,
        bbox_size: tuple[int, int],
    ) -> tuple[float, int | None]:
        if not self.templates:
            return 0.50, None
        best_score = 0.0
        best_id: int | None = None
        for item in self.templates:
            gray_score = self._cosine(item.gray, gray)
            edge_score = self._iou(item.edges, edges)
            hist_score = self._cosine(item.histogram, histogram)
            silhouette_score = self._iou(item.silhouette, silhouette)
            size_score = min(
                item.bbox_size[0] / max(1, bbox_size[0]),
                bbox_size[0] / max(1, item.bbox_size[0]),
                item.bbox_size[1] / max(1, bbox_size[1]),
                bbox_size[1] / max(1, item.bbox_size[1]),
            )
            score = (
                0.34 * gray_score
                + 0.18 * edge_score
                + 0.18 * hist_score
                + 0.20 * silhouette_score
                + 0.10 * size_score
            )
            if score > best_score:
                best_score = score
                best_id = item.template_id
        return float(best_score), best_id

    def add_or_update(
        self,
        *,
        gray: np.ndarray,
        edges: np.ndarray,
        histogram: np.ndarray,
        silhouette: np.ndarray,
        bbox_size: tuple[int, int],
        feet_anchor_offset: tuple[float, float],
        confidence: float,
        source_state: str,
        matched_template_id: int | None,
    ) -> int:
        if matched_template_id is not None:
            for item in self.templates:
                if item.template_id == matched_template_id:
                    alpha = 0.08
                    item.gray = np.clip(item.gray.astype(np.float32) * (1 - alpha) + gray.astype(np.float32) * alpha, 0, 255).astype(np.uint8)
                    item.edges = np.where((item.edges > 0) | (edges > 0), 255, 0).astype(np.uint8)
                    item.histogram = (item.histogram * (1 - alpha) + histogram * alpha).astype(np.float32)
                    norm = float(np.linalg.norm(item.histogram))
                    if norm > 0:
                        item.histogram /= norm
                    item.silhouette = np.where((item.silhouette > 0) | (silhouette > 0), 255, 0).astype(np.uint8)
                    item.confidence = max(item.confidence, float(confidence))
                    item.observations += 1
                    return item.template_id
        template = SelfTemplate(
            template_id=self._next_id,
            gray=gray.copy(),
            edges=edges.copy(),
            histogram=histogram.copy(),
            silhouette=silhouette.copy(),
            bbox_size=bbox_size,
            feet_anchor_offset=feet_anchor_offset,
            confidence=float(confidence),
            source_state=source_state,
        )
        self._next_id += 1
        self.templates.append(template)
        if len(self.templates) > self.max_templates:
            self.templates.sort(key=lambda item: (item.confidence, item.observations), reverse=True)
            self.templates = self.templates[: self.max_templates]
        return template.template_id

    def silhouette_for(self, template_id: int | None) -> np.ndarray | None:
        if template_id is None:
            return None
        for item in self.templates:
            if item.template_id == template_id:
                return item.silhouette
        return None


class FixedSelfDetector:
    """Verify SELF only inside the immutable fixed cell with score hysteresis."""

    def __init__(
        self,
        grid: FixedNativeGridCalibration,
        *,
        acquire_threshold: float = 0.40,
        keep_threshold: float = 0.28,
        reliable_update_threshold: float = 0.58,
        uncertain_grace_frames: int = 5,
        lost_critical_frames: int = 8,
    ) -> None:
        self.grid = grid
        self.acquire_threshold = float(acquire_threshold)
        self.keep_threshold = float(keep_threshold)
        self.reliable_update_threshold = float(reliable_update_threshold)
        self.uncertain_grace_frames = max(1, int(uncertain_grace_frames))
        self.lost_critical_frames = max(self.uncertain_grace_frames + 1, int(lost_critical_frames))
        self.template_bank = SelfTemplateBank()
        self.last_bbox: NativeRect | None = None
        self.last_anchor: tuple[float, float] | None = None
        self.last_template_id: int | None = None
        self.last_confirmed_frame: int | None = None
        self.frame_index = 0
        self.missing_frames = 0
        self.last_silhouette_native: np.ndarray | None = None

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
    def _features(crop: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray_n = cv2.resize(gray, (20, 48), interpolation=cv2.INTER_AREA)
        silhouette = cv2.resize(mask, (20, 48), interpolation=cv2.INTER_NEAREST)
        gray_n = np.where(silhouette > 0, gray_n, 0).astype(np.uint8)
        edges = cv2.Canny(gray_n, 30, 90)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], mask, [8, 4], [0, 180, 0, 256]).reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(hist))
        if norm > 0:
            hist /= norm
        return gray_n, edges, hist, silhouette

    def _preserved_observation(
        self,
        *,
        score: float,
        state: SelfVisualState,
        reason: str,
    ) -> SelfVisualObservation:
        assert self.last_bbox is not None and self.last_anchor is not None
        protected = self.protected_mask((self.grid.native_height, self.grid.native_width))
        return SelfVisualObservation(
            True,
            self.last_bbox,
            self.last_anchor,
            self.grid.self_cell_rect().contains(self.last_anchor),
            float(score),
            float(score),
            state,
            reason,
            matched_template_id=self.last_template_id,
            preserved_from_frame=self.last_confirmed_frame,
            missing_frames=self.missing_frames,
            template_update_allowed=False,
            template_update_block_reason="LOW_SCORE_OR_TEMPORARY_OCCLUSION",
            protected_mask_pixels=int(np.count_nonzero(protected)),
        )

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
        background_lab = cv2.cvtColor(background_bgr.reshape(1, 1, 3), cv2.COLOR_BGR2LAB).astype(np.int16)[0, 0]
        color_distance = np.linalg.norm(lab - background_lab, axis=2)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 110)
        foreground = np.where((color_distance >= 15.0) | (edges > 0), 255, 0).astype(np.uint8)
        foreground[self._debug_overlay_exclusion(crop) > 0] = 0
        kernel = np.ones((3, 3), np.uint8)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=2)
        count, labels, stats, _centroids = cv2.connectedComponentsWithStats(foreground, 8)
        candidates: list[tuple[float, NativeRect, tuple[float, float], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray], int | None]] = []
        expected = ((fixed.left + fixed.right) / 2.0, fixed.bottom - 8.0)
        for label in range(1, count):
            local_x, local_y, component_width, component_height, pixels = [int(value) for value in stats[label]]
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
                labels[local_y : local_y + component_height, local_x : local_x + component_width] == label,
                255,
                0,
            ).astype(np.uint8)
            component_crop = crop[local_y : local_y + component_height, local_x : local_x + component_width]
            features = self._features(component_crop, component_mask)
            template_score, template_id = self.template_bank.match(
                *features,
                (component_width, component_height),
            )
            proximity = max(0.0, 1.0 - math.hypot(feet[0] - expected[0], feet[1] - expected[1]) / 56.0)
            aspect = component_width / max(1.0, float(component_height))
            geometry = max(0.0, 1.0 - abs(aspect - 0.5) / 0.8)
            persistence = 0.5
            if self.last_anchor is not None:
                persistence = max(0.0, 1.0 - math.hypot(feet[0] - self.last_anchor[0], feet[1] - self.last_anchor[1]) / 24.0)
            score = 0.34 * template_score + 0.30 * proximity + 0.20 * geometry + 0.16 * persistence
            candidates.append((score, native_rect, feet, features, template_id))

        if not candidates:
            self.missing_frames += 1
            if self.last_bbox is not None and self.last_anchor is not None and self.missing_frames <= self.uncertain_grace_frames:
                state = SelfVisualState.SELF_TEMPORARILY_UNCERTAIN
                observation = self._preserved_observation(
                    score=0.0,
                    state=state,
                    reason="SELF preserved through short segmentation failure",
                )
                self.frame_index += 1
                return observation
            state = SelfVisualState.SELF_LOST_CRITICAL if self.missing_frames >= self.lost_critical_frames else SelfVisualState.SELF_VISUAL_UNCONFIRMED
            self.frame_index += 1
            return SelfVisualObservation(
                False,
                None,
                None,
                False,
                0.0,
                0.0,
                state,
                "no template-compatible body core inside fixed SELF cell",
                missing_frames=self.missing_frames,
                template_update_block_reason="NO_BODY_CORE",
            )

        score, bbox, feet, features, matched_id = max(candidates, key=lambda item: item[0])
        if score < self.acquire_threshold:
            self.missing_frames += 1
            if (
                self.last_bbox is not None
                and self.last_anchor is not None
                and score >= self.keep_threshold
                and self.missing_frames <= self.uncertain_grace_frames
            ):
                observation = self._preserved_observation(
                    score=score,
                    state=SelfVisualState.SELF_PRESERVED_LOW_SCORE,
                    reason="SELF identity preserved by keep-threshold hysteresis",
                )
                self.frame_index += 1
                return observation
            state = SelfVisualState.SELF_LOST_CRITICAL if self.missing_frames >= self.lost_critical_frames else SelfVisualState.SELF_VISUAL_UNCONFIRMED
            self.frame_index += 1
            return SelfVisualObservation(
                False,
                None,
                None,
                False,
                score,
                score,
                state,
                "fixed-cell body candidate did not satisfy SELF acquisition confidence",
                matched_template_id=matched_id,
                missing_frames=self.missing_frames,
                template_update_block_reason="BELOW_KEEP_THRESHOLD",
            )

        self.missing_frames = 0
        self.last_bbox = bbox
        self.last_anchor = feet
        self.last_confirmed_frame = self.frame_index
        gray_n, edges_n, hist_n, silhouette_n = features
        update_allowed = score >= self.reliable_update_threshold or not self.template_bank.templates
        block_reason = None if update_allowed else "SELF_SCORE_BELOW_RELIABLE_UPDATE_THRESHOLD"
        if update_allowed:
            self.last_template_id = self.template_bank.add_or_update(
                gray=gray_n,
                edges=edges_n,
                histogram=hist_n,
                silhouette=silhouette_n,
                bbox_size=(bbox.width, bbox.height),
                feet_anchor_offset=(feet[0] - bbox.left, feet[1] - bbox.top),
                confidence=score,
                source_state=SelfVisualState.SELF_TRACKED.value,
                matched_template_id=matched_id,
            )
        elif matched_id is not None:
            self.last_template_id = matched_id
        native_silhouette = np.zeros((self.grid.native_height, self.grid.native_width), dtype=np.uint8)
        resized = cv2.resize(silhouette_n, (bbox.width, bbox.height), interpolation=cv2.INTER_NEAREST)
        native_silhouette[bbox.top:bbox.bottom, bbox.left:bbox.right] = resized
        self.last_silhouette_native = native_silhouette
        protected_pixels = int(np.count_nonzero(native_silhouette))
        observation = SelfVisualObservation(
            True,
            bbox,
            feet,
            fixed.contains(feet),
            score,
            score,
            SelfVisualState.SELF_TRACKED,
            "SELF body visually confirmed inside immutable fixed cell",
            matched_template_id=self.last_template_id,
            preserved_from_frame=self.last_confirmed_frame,
            missing_frames=0,
            template_update_allowed=update_allowed,
            template_update_block_reason=block_reason,
            protected_mask_pixels=protected_pixels,
        )
        self.frame_index += 1
        return observation

    def protected_mask(self, shape: tuple[int, int]) -> np.ndarray:
        height, width = shape
        mask = np.zeros((height, width), dtype=np.uint8)
        if self.last_silhouette_native is not None and self.last_silhouette_native.shape == mask.shape:
            return self.last_silhouette_native.copy()
        if self.last_bbox is not None:
            rect = self.last_bbox.intersect(NativeRect(0, 0, width, height))
            if rect is not None:
                mask[rect.top:rect.bottom, rect.left:rect.right] = 255
        return mask


__all__ = [
    "FixedSelfDetector",
    "SelfTemplate",
    "SelfTemplateBank",
    "SelfVisualObservation",
    "SelfVisualState",
]
