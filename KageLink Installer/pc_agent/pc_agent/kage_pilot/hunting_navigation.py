from __future__ import annotations


class SceneMotionProbe:
    """Detect lack of scene displacement and request an early direction flip."""

    def __init__(self) -> None:
        self.previous = None
        self.previous_at = -1e9

    def moved(self, frame_bgr, now: float) -> bool | None:
        import cv2
        import numpy as np

        if now - self.previous_at < 0.65:
            return None
        height, _width = frame_bgr.shape[:2]
        roi = frame_bgr[: max(1, int(height * 0.72)), :]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (96, 54), interpolation=cv2.INTER_AREA)
        result = None
        if self.previous is not None:
            result = float(np.mean(cv2.absdiff(small, self.previous))) >= 1.15
        self.previous = small
        self.previous_at = now
        return result


__all__ = ["SceneMotionProbe"]
