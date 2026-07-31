from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MotionSample:
    screen_dx_px: float
    screen_dy_px: float
    response: float
    accepted: bool
    reason: str

    @classmethod
    def baseline(cls) -> "MotionSample":
        return cls(0.0, 0.0, 0.0, False, "baseline_frame")


class PhaseCorrelationMotionEstimator:
    """Estimate translational screen motion between consecutive game frames."""

    def __init__(
        self,
        min_response: float = 0.18,
        max_shift_px: float = 96.0,
        deadzone_px: float = 0.20,
        crop_top: float = 0.10,
        crop_bottom: float = 0.12,
        crop_left: float = 0.08,
        crop_right: float = 0.08,
    ) -> None:
        if not 0.0 <= min_response <= 1.0:
            raise ValueError("min_response must be between zero and one")
        self.min_response = min_response
        self.max_shift_px = max_shift_px
        self.deadzone_px = deadzone_px
        self.crop = (crop_top, crop_bottom, crop_left, crop_right)
        self._window_cache: dict[tuple[int, int], Any] = {}

    def estimate(self, previous_frame: Any, current_frame: Any) -> MotionSample:
        import cv2
        import numpy as np

        previous = self._prepare(previous_frame, cv2, np)
        current = self._prepare(current_frame, cv2, np)
        if previous.shape != current.shape:
            return MotionSample(0.0, 0.0, 0.0, False, "frame_size_changed")
        height, width = previous.shape
        window = self._window_cache.get((width, height))
        if window is None:
            window = cv2.createHanningWindow((width, height), cv2.CV_32F)
            self._window_cache[(width, height)] = window
        (dx, dy), response = cv2.phaseCorrelate(previous, current, window)
        magnitude = float((dx * dx + dy * dy) ** 0.5)
        response = float(response)
        if response < self.min_response:
            return MotionSample(float(dx), float(dy), response, False, "low_correlation")
        if magnitude > self.max_shift_px:
            return MotionSample(float(dx), float(dy), response, False, "shift_too_large")
        if magnitude < self.deadzone_px:
            return MotionSample(float(dx), float(dy), response, False, "below_deadzone")
        return MotionSample(float(dx), float(dy), response, True, "screen_translation")

    def _prepare(self, frame: Any, cv2: Any, np: Any) -> Any:
        if frame is None or not hasattr(frame, "shape"):
            raise TypeError("frame must be a numpy-compatible image")
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        elif len(frame.shape) == 2:
            gray = frame
        else:
            raise ValueError("frame must have two or three dimensions")
        height, width = gray.shape
        top, bottom, left, right = self.crop
        y0, y1 = int(height * top), int(height * (1.0 - bottom))
        x0, x1 = int(width * left), int(width * (1.0 - right))
        if y1 - y0 < 32 or x1 - x0 < 32:
            y0, x0, y1, x1 = 0, 0, height, width
        roi = gray[y0:y1, x0:x1]
        roi = cv2.GaussianBlur(roi, (5, 5), 0)
        return np.asarray(roi, dtype=np.float32)
