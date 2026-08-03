from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .pr27_camera_motion import CameraMotionResult
from .pr27_fixed_grid import NativeRect


@dataclass(frozen=True, slots=True)
class TrainerMaskEvidence:
    bbox: NativeRect | None
    confidence: float
    source: str
    mask_only: bool = True
    rgb_replaced: bool = False


def output_bbox_to_native(
    bbox: tuple[int, int, int, int],
    *,
    native_width: int = 1920,
    native_height: int = 1037,
    output_width: int = 960,
    output_height: int = 540,
) -> NativeRect:
    """Invert DreamSeeker's aspect-preserving 960x540 preview mapping."""

    x, y, width, height = [float(value) for value in bbox]
    scale = min(output_width / native_width, output_height / native_height)
    rendered_width = native_width * scale
    rendered_height = native_height * scale
    offset_x = (output_width - rendered_width) / 2.0
    offset_y = (output_height - rendered_height) / 2.0
    left = int(round((x - offset_x) / scale))
    top = int(round((y - offset_y) / scale))
    right = int(round((x + width - offset_x) / scale))
    bottom = int(round((y + height - offset_y) / scale))
    return NativeRect(
        max(0, min(native_width, left)),
        max(0, min(native_height, top)),
        max(0, min(native_width, right)),
        max(0, min(native_height, bottom)),
    )


class TrainerMaskTracker:
    """Track Trainer only as a dynamic exclusion mask; never paste old RGB."""

    def __init__(
        self,
        initial_bbox: NativeRect | None = None,
        *,
        search_margin: int = 72,
        minimum_score: float = 0.60,
    ) -> None:
        self.bbox = initial_bbox
        self.search_margin = max(16, int(search_margin))
        self.minimum_score = min(1.0, max(0.1, float(minimum_score)))
        self.template: np.ndarray | None = None
        self.last = TrainerMaskEvidence(initial_bbox, 0.0, "INITIAL_BBOX" if initial_bbox else "UNAVAILABLE")

    @staticmethod
    def _clip(rect: NativeRect, shape: tuple[int, int]) -> NativeRect | None:
        height, width = shape
        return rect.intersect(NativeRect(0, 0, width, height))

    def _capture_template(self, frame_bgr: np.ndarray) -> None:
        if self.bbox is None:
            return
        clipped = self._clip(self.bbox, frame_bgr.shape[:2])
        if clipped is None or clipped.width < 6 or clipped.height < 6:
            return
        crop = frame_bgr[clipped.top : clipped.bottom, clipped.left : clipped.right]
        self.template = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    def update(
        self,
        frame_bgr: np.ndarray,
        *,
        camera_motion: CameraMotionResult | None = None,
    ) -> TrainerMaskEvidence:
        if self.bbox is None:
            self.last = TrainerMaskEvidence(None, 0.0, "NO_TRAINER_BBOX")
            return self.last
        if camera_motion is not None and camera_motion.compensated:
            dx = int(round(camera_motion.dx_px))
            dy = int(round(camera_motion.dy_px))
            self.bbox = NativeRect(
                self.bbox.left + dx,
                self.bbox.top + dy,
                self.bbox.right + dx,
                self.bbox.bottom + dy,
            )
        clipped = self._clip(self.bbox, frame_bgr.shape[:2])
        if clipped is None:
            self.last = TrainerMaskEvidence(None, 0.0, "TRAINER_OUTSIDE_FRAME")
            return self.last
        self.bbox = clipped
        if self.template is None:
            self._capture_template(frame_bgr)
            self.last = TrainerMaskEvidence(self.bbox, 0.65, "DETECTOR_BBOX_TEMPLATE_CAPTURE")
            return self.last

        search = self._clip(
            self.bbox.expand(
                left=self.search_margin,
                right=self.search_margin,
                top=self.search_margin,
                bottom=self.search_margin,
            ),
            frame_bgr.shape[:2],
        )
        if search is None or search.width < self.template.shape[1] or search.height < self.template.shape[0]:
            self.last = TrainerMaskEvidence(self.bbox, 0.25, "PREDICTED_CAMERA_SHIFT")
            return self.last
        gray = cv2.cvtColor(
            frame_bgr[search.top : search.bottom, search.left : search.right],
            cv2.COLOR_BGR2GRAY,
        )
        result = cv2.matchTemplate(gray, self.template, cv2.TM_CCOEFF_NORMED)
        _minimum, maximum, _minimum_location, maximum_location = cv2.minMaxLoc(result)
        score = float(maximum)
        if score >= self.minimum_score:
            left = search.left + int(maximum_location[0])
            top = search.top + int(maximum_location[1])
            self.bbox = NativeRect(
                left,
                top,
                left + self.template.shape[1],
                top + self.template.shape[0],
            )
            self.last = TrainerMaskEvidence(self.bbox, score, "CURRENT_FRAME_TEMPLATE_MATCH")
        else:
            self.last = TrainerMaskEvidence(self.bbox, score, "PREDICTED_CAMERA_SHIFT")
        return self.last

    @staticmethod
    def mask(shape: tuple[int, int], evidence: TrainerMaskEvidence) -> np.ndarray:
        mask = np.zeros(shape, dtype=np.uint8)
        rect = evidence.bbox
        if rect is not None:
            mask[rect.top : rect.bottom, rect.left : rect.right] = 255
        return mask


__all__ = [
    "TrainerMaskEvidence",
    "TrainerMaskTracker",
    "output_bbox_to_native",
]
