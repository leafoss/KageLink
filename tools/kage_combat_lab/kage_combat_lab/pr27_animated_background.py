from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

import cv2
import numpy as np


class BackgroundClass(str, Enum):
    STATIC_BACKGROUND = "STATIC_BACKGROUND"
    BACKGROUND_EGO_MOTION = "BACKGROUND_EGO_MOTION"
    ANIMATED_BACKGROUND = "ANIMATED_BACKGROUND"
    UNKNOWN_VISUAL_CHANGE = "UNKNOWN_VISUAL_CHANGE"


@dataclass(frozen=True, slots=True)
class BackgroundEvidence:
    background_class: BackgroundClass
    score: float
    changed_ratio: float
    mask_iou: float
    centroid_motion_px: float
    shape_instability: float
    ego_motion_match: float
    reason: str


@dataclass(slots=True)
class _CellHistory:
    masks: deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=8))
    centroids: deque[tuple[float, float] | None] = field(default_factory=lambda: deque(maxlen=8))
    changed_ratios: deque[float] = field(default_factory=lambda: deque(maxlen=8))
    animated_hits: int = 0


def _mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    left = a > 0
    right = b > 0
    union = np.count_nonzero(left | right)
    if union == 0:
        return 1.0
    return float(np.count_nonzero(left & right) / union)


def _centroid(mask: np.ndarray) -> tuple[float, float] | None:
    moments = cv2.moments((mask > 0).astype(np.uint8))
    if moments["m00"] <= 0:
        return None
    return moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]


class AnimatedBackgroundModel:
    """Memorize non-rigid recurring tile animation such as water and foam."""

    def __init__(
        self,
        *,
        minimum_changed_ratio: float = 0.012,
        confirmation_frames: int = 3,
    ) -> None:
        self.minimum_changed_ratio = max(0.001, float(minimum_changed_ratio))
        self.confirmation_frames = max(2, int(confirmation_frames))
        self._history: dict[tuple[int, int], _CellHistory] = defaultdict(_CellHistory)
        self.last_evidence: dict[tuple[int, int], BackgroundEvidence] = {}

    @staticmethod
    def _shape_instability(history: _CellHistory, current: np.ndarray) -> tuple[float, float]:
        if not history.masks:
            return 0.0, 1.0
        ious = [_mask_iou(mask, current) for mask in history.masks]
        mean_iou = float(np.mean(ious))
        return 1.0 - mean_iou, mean_iou

    @staticmethod
    def _centroid_motion(history: _CellHistory, current: tuple[float, float] | None) -> float:
        previous = next((value for value in reversed(history.centroids) if value is not None), None)
        if previous is None or current is None:
            return 0.0
        return float(np.hypot(current[0] - previous[0], current[1] - previous[1]))

    def observe_cell(
        self,
        key: tuple[int, int],
        residual_mask: np.ndarray,
        *,
        ego_motion_match: float = 0.0,
        synchronized_neighbors: int = 0,
    ) -> BackgroundEvidence:
        binary = np.where(residual_mask > 0, 255, 0).astype(np.uint8)
        changed_ratio = float(np.count_nonzero(binary) / max(1, binary.size))
        history = self._history[key]
        current_centroid = _centroid(binary)
        shape_instability, mean_iou = self._shape_instability(history, binary)
        centroid_motion = self._centroid_motion(history, current_centroid)
        ego_motion_match = float(max(0.0, min(1.0, ego_motion_match)))

        broad_animation = synchronized_neighbors >= 2 and changed_ratio >= self.minimum_changed_ratio
        non_rigid = shape_instability >= 0.38 and centroid_motion <= 4.0
        recurrent = (
            len(history.changed_ratios) >= 2
            and sum(value >= self.minimum_changed_ratio for value in history.changed_ratios) >= 2
        )
        ego = ego_motion_match >= 0.72

        if changed_ratio < self.minimum_changed_ratio:
            background_class = BackgroundClass.STATIC_BACKGROUND
            score = max(0.0, 1.0 - changed_ratio / self.minimum_changed_ratio)
            reason = "residual change below animated/background threshold"
            history.animated_hits = max(0, history.animated_hits - 1)
        elif ego:
            background_class = BackgroundClass.BACKGROUND_EGO_MOTION
            score = ego_motion_match
            reason = "residual follows dominant camera/terrain translation"
            history.animated_hits = max(0, history.animated_hits - 1)
        else:
            raw_score = (
                0.38 * shape_instability
                + 0.22 * (1.0 - min(1.0, centroid_motion / 12.0))
                + 0.20 * min(1.0, changed_ratio / 0.20)
                + 0.12 * min(1.0, synchronized_neighbors / 4.0)
                + 0.08 * (1.0 if recurrent else 0.0)
            )
            if non_rigid and (recurrent or broad_animation):
                history.animated_hits += 1
            else:
                history.animated_hits = max(0, history.animated_hits - 1)
            if history.animated_hits >= self.confirmation_frames:
                background_class = BackgroundClass.ANIMATED_BACKGROUND
                score = max(0.65, raw_score)
                reason = "recurring non-rigid local animation without rigid body trajectory"
            else:
                background_class = BackgroundClass.UNKNOWN_VISUAL_CHANGE
                score = raw_score
                reason = "visual change not yet proven as rigid entity or recurring background"

        history.masks.append(binary.copy())
        history.centroids.append(current_centroid)
        history.changed_ratios.append(changed_ratio)
        evidence = BackgroundEvidence(
            background_class=background_class,
            score=float(max(0.0, min(1.0, score))),
            changed_ratio=changed_ratio,
            mask_iou=mean_iou,
            centroid_motion_px=centroid_motion,
            shape_instability=shape_instability,
            ego_motion_match=ego_motion_match,
            reason=reason,
        )
        self.last_evidence[key] = evidence
        return evidence

    def animated_keys(self) -> frozenset[tuple[int, int]]:
        return frozenset(
            key
            for key, evidence in self.last_evidence.items()
            if evidence.background_class is BackgroundClass.ANIMATED_BACKGROUND
        )

    def summary(self) -> Mapping[str, int]:
        counts = {value.value: 0 for value in BackgroundClass}
        for evidence in self.last_evidence.values():
            counts[evidence.background_class.value] += 1
        return counts


__all__ = [
    "AnimatedBackgroundModel",
    "BackgroundClass",
    "BackgroundEvidence",
]
