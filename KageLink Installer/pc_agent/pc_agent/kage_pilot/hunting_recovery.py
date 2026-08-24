from __future__ import annotations

import cv2
import numpy as np

from .post_combat_v03 import HudResourceReader


_HEALTH_X, _HEALTH_Y, _HEALTH_W, _HEALTH_H = HudResourceReader.HEALTH_ROI


class StaminaHudReader:
    """Read Shinobi Story Stamina from the bar directly below HEALTH.

    The bar keeps a fixed position relative to the already-calibrated HEALTH HUD and
    changes fill color as it drains: green -> yellow -> orange -> no color. The
    unfilled tail is dark brown/black. We measure the longest horizontal run of
    saturated filled-bar pixels while deliberately rejecting the darker empty tail.
    """

    calibrated = True

    # Anchor the Stamina search to the validated HEALTH neighborhood rather than
    # inventing an independent screen origin. The supplied HUD reference shows the
    # Stamina bar below and slightly right of the red HEALTH bar.
    STAMINA_ROI = (
        _HEALTH_X + _HEALTH_W * 0.18,
        _HEALTH_Y + _HEALTH_H * 0.34,
        _HEALTH_W * 0.46,
        _HEALTH_H * 0.34,
    )
    STAMINA_FULL_PX_960 = 30.0

    @staticmethod
    def _crop(frame: np.ndarray, region) -> np.ndarray:
        h, w = frame.shape[:2]
        x, y, rw, rh = region
        x0 = max(0, int(round(x * w)))
        y0 = max(0, int(round(y * h)))
        x1 = min(w, int(round((x + rw) * w)))
        y1 = min(h, int(round((y + rh) * h)))
        return frame[y0:y1, x0:x1]

    @staticmethod
    def _longest_column_run(mask: np.ndarray) -> int:
        if mask.size == 0:
            return 0
        minimum_pixels = 2 if mask.shape[0] >= 4 else 1
        active = np.count_nonzero(mask, axis=0) >= minimum_pixels
        best = current = 0
        for value in active.tolist():
            if value:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return int(best)

    def read(self, frame_bgr: np.ndarray) -> float | None:
        if frame_bgr is None or frame_bgr.size == 0:
            return None

        roi = self._crop(frame_bgr, self.STAMINA_ROI)
        if roi.size == 0:
            return None

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        hue, saturation, value = cv2.split(hsv)

        # OpenCV hue is 0..179. Green/yellow remain valid at lower brightness so
        # the darker left edge of the filled bar is counted. Orange overlaps the
        # hue of the empty brown tail, so orange requires a higher brightness gate.
        green_yellow = (
            (hue >= 25)
            & (hue <= 80)
            & (value >= 95)
        )
        orange = (
            (hue >= 5)
            & (hue < 25)
            & (value >= 125)
        )
        stamina_mask = (saturation >= 70) & (green_yellow | orange)

        fill_px = self._longest_column_run(stamina_mask)
        scale = max(0.25, float(frame_bgr.shape[1]) / 960.0)
        full_px = self.STAMINA_FULL_PX_960 * scale
        return min(1.0, float(fill_px) / full_px) if fill_px > 0 else 0.0


__all__ = ["StaminaHudReader"]
