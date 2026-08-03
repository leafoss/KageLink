from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .pr27_entity_validation import EntityCandidate
from .pr27_fixed_grid import NativeRect


@dataclass(frozen=True, slots=True)
class SpawnDeltaEvidence:
    available: bool
    mask: np.ndarray
    active_pixels: int
    candidate_ids: tuple[int, ...]
    reason: str


class SpawnDeltaDetector:
    """Detect humanoids that appear after the Dojo pre-spawn scene."""

    def __init__(self, pre_spawn_bgr: np.ndarray | None = None, *, threshold: int = 24) -> None:
        self.pre_spawn_bgr = None if pre_spawn_bgr is None else np.ascontiguousarray(pre_spawn_bgr.copy())
        self.threshold = max(4, int(threshold))

    def set_pre_spawn(self, frame_bgr: np.ndarray) -> None:
        self.pre_spawn_bgr = np.ascontiguousarray(frame_bgr.copy())

    def difference_mask(
        self,
        frame_bgr: np.ndarray,
        *,
        aligned_pre_spawn: np.ndarray | None = None,
        self_mask: np.ndarray | None = None,
        animated_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        reference = aligned_pre_spawn if aligned_pre_spawn is not None else self.pre_spawn_bgr
        if reference is None or reference.shape != frame_bgr.shape:
            return np.zeros(frame_bgr.shape[:2], dtype=np.uint8)
        delta = cv2.absdiff(frame_bgr, reference)
        gray = cv2.cvtColor(delta, cv2.COLOR_BGR2GRAY)
        mask = np.where(gray >= self.threshold, 255, 0).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2)
        for exclusion in (self_mask, animated_mask):
            if exclusion is not None and exclusion.shape == mask.shape:
                mask[exclusion > 0] = 0
        return mask

    @staticmethod
    def candidate_ids(
        mask: np.ndarray,
        candidates: tuple[EntityCandidate, ...],
        *,
        minimum_bbox_ratio: float = 0.18,
    ) -> tuple[int, ...]:
        ids: list[int] = []
        for candidate in candidates:
            rect = candidate.bbox.intersect(NativeRect(0, 0, mask.shape[1], mask.shape[0]))
            if rect is None:
                continue
            patch = mask[rect.top:rect.bottom, rect.left:rect.right]
            ratio = float(np.count_nonzero(patch) / max(1, patch.size))
            if ratio >= minimum_bbox_ratio:
                ids.append(candidate.candidate_id)
        return tuple(ids)

    def observe(
        self,
        frame_bgr: np.ndarray,
        candidates: tuple[EntityCandidate, ...],
        *,
        aligned_pre_spawn: np.ndarray | None = None,
        self_mask: np.ndarray | None = None,
        animated_mask: np.ndarray | None = None,
    ) -> SpawnDeltaEvidence:
        if self.pre_spawn_bgr is None and aligned_pre_spawn is None:
            empty = np.zeros(frame_bgr.shape[:2], dtype=np.uint8)
            return SpawnDeltaEvidence(False, empty, 0, (), "PRE_SPAWN_UNAVAILABLE")
        mask = self.difference_mask(
            frame_bgr,
            aligned_pre_spawn=aligned_pre_spawn,
            self_mask=self_mask,
            animated_mask=animated_mask,
        )
        ids = self.candidate_ids(mask, candidates)
        return SpawnDeltaEvidence(
            True,
            mask,
            int(np.count_nonzero(mask)),
            ids,
            "NEW_VISUAL_CONTENT_AFTER_DOJO_SPAWN" if ids else "NO_PERSISTENT_HUMANOID_IN_SPAWN_DELTA",
        )


__all__ = ["SpawnDeltaDetector", "SpawnDeltaEvidence"]
