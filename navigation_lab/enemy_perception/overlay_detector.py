from __future__ import annotations

from typing import Any

from .models import OverlayMetrics, OverlayResult


class OverlayDetector:
    """Compare a current tile crop against an empty reference with light pixel-art-safe processing."""

    def __init__(
        self,
        pixel_threshold: int = 24,
        min_changed_ratio: float = 0.03,
        min_component_area: int = 12,
        morphology_kernel: int = 3,
    ) -> None:
        self.pixel_threshold = int(pixel_threshold)
        self.min_changed_ratio = float(min_changed_ratio)
        self.min_component_area = max(1, int(min_component_area))
        self.morphology_kernel = max(1, int(morphology_kernel))

    def detect(self, current: Any, background: Any) -> OverlayResult:
        import cv2
        import numpy as np

        if current.shape[:2] != background.shape[:2]:
            background = cv2.resize(
                background,
                (current.shape[1], current.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
        difference = cv2.absdiff(current[:, :, :3], background[:, :, :3])
        intensity = difference.max(axis=2).astype(np.uint8)
        raw = (intensity >= self.pixel_threshold).astype(np.uint8) * 255
        if self.morphology_kernel > 1:
            kernel = np.ones((self.morphology_kernel, self.morphology_kernel), np.uint8)
            raw = cv2.morphologyEx(raw, cv2.MORPH_OPEN, kernel)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(raw, 8)
        mask = np.zeros_like(raw)
        areas: list[int] = []
        for label in range(1, count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area >= self.min_component_area:
                mask[labels == label] = 255
                areas.append(area)
        changed = int(np.count_nonzero(mask))
        ratio = changed / float(mask.size)
        metrics = OverlayMetrics(
            difference_mean=float(intensity.mean()),
            difference_max=float(intensity.max()),
            changed_pixel_count=changed,
            changed_pixel_ratio=ratio,
            component_count=len(areas),
            largest_component_area=max(areas, default=0),
            overlay_detected=bool(ratio >= self.min_changed_ratio and areas),
        )
        return OverlayResult(metrics, difference, mask)
