from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class CameraMotionResult:
    dx_px: float = 0.0
    dy_px: float = 0.0
    confidence: float = 0.0
    source: str = "INITIAL_FRAME"
    consensus: float = 0.0
    compensated: bool = False

    @property
    def shift(self) -> tuple[float, float]:
        return self.dx_px, self.dy_px


class CameraMotionEstimator:
    """Estimate dominant screen-space terrain translation before entity detection.

    The player is fixed on screen in this game mode. A directional input moves the
    world/camera, so the dominant background vector must be removed before
    residual motion can be interpreted as an entity.
    """

    def __init__(
        self,
        *,
        maximum_shift_px: float = 96.0,
        minimum_confidence: float = 0.18,
        downsample: float = 0.5,
    ) -> None:
        self.maximum_shift_px = max(8.0, float(maximum_shift_px))
        self.minimum_confidence = min(1.0, max(0.0, float(minimum_confidence)))
        self.downsample = min(1.0, max(0.2, float(downsample)))
        self.previous_gray: np.ndarray | None = None
        self.last = CameraMotionResult()

    @staticmethod
    def _prepare(frame_bgr: np.ndarray, exclusion_mask: np.ndarray | None) -> np.ndarray:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        if exclusion_mask is not None:
            if exclusion_mask.shape != gray.shape:
                raise ValueError("PR27_CAMERA_MASK_SHAPE_MISMATCH")
            allowed = exclusion_mask == 0
            fill = int(np.median(gray[allowed])) if np.any(allowed) else int(np.median(gray))
            gray = gray.copy()
            gray[~allowed] = fill
        return gray

    @staticmethod
    def _phase_shift(previous: np.ndarray, current: np.ndarray) -> tuple[float, float, float]:
        previous32 = previous.astype(np.float32)
        current32 = current.astype(np.float32)
        window = cv2.createHanningWindow((previous.shape[1], previous.shape[0]), cv2.CV_32F)
        shift, response = cv2.phaseCorrelate(previous32, current32, window)
        return float(shift[0]), float(shift[1]), float(max(0.0, min(1.0, response)))

    @staticmethod
    def _flow_shift(previous: np.ndarray, current: np.ndarray) -> tuple[float, float, float]:
        points = cv2.goodFeaturesToTrack(
            previous,
            maxCorners=300,
            qualityLevel=0.01,
            minDistance=8,
            blockSize=7,
        )
        if points is None or len(points) < 8:
            return 0.0, 0.0, 0.0
        next_points, status, _errors = cv2.calcOpticalFlowPyrLK(
            previous,
            current,
            points,
            None,
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )
        if next_points is None or status is None:
            return 0.0, 0.0, 0.0
        valid = status.reshape(-1) == 1
        if int(np.count_nonzero(valid)) < 8:
            return 0.0, 0.0, 0.0
        vectors = next_points.reshape(-1, 2)[valid] - points.reshape(-1, 2)[valid]
        median = np.median(vectors, axis=0)
        distances = np.linalg.norm(vectors - median, axis=1)
        inliers = distances <= max(1.5, float(np.median(distances)) * 2.5)
        if int(np.count_nonzero(inliers)) < 6:
            return float(median[0]), float(median[1]), 0.0
        refined = np.median(vectors[inliers], axis=0)
        consensus = float(np.count_nonzero(inliers) / len(vectors))
        return float(refined[0]), float(refined[1]), consensus

    def observe(
        self,
        frame_bgr: np.ndarray,
        *,
        exclusion_mask: np.ndarray | None = None,
    ) -> CameraMotionResult:
        gray = self._prepare(frame_bgr, exclusion_mask)
        if self.downsample != 1.0:
            work = cv2.resize(
                gray,
                None,
                fx=self.downsample,
                fy=self.downsample,
                interpolation=cv2.INTER_AREA,
            )
        else:
            work = gray
        if self.previous_gray is None or self.previous_gray.shape != work.shape:
            self.previous_gray = work
            self.last = CameraMotionResult()
            return self.last

        phase_dx, phase_dy, phase_confidence = self._phase_shift(self.previous_gray, work)
        flow_dx, flow_dy, flow_consensus = self._flow_shift(self.previous_gray, work)
        scale = 1.0 / self.downsample
        phase_dx *= scale
        phase_dy *= scale
        flow_dx *= scale
        flow_dy *= scale

        agreement = max(
            0.0,
            1.0
            - np.hypot(phase_dx - flow_dx, phase_dy - flow_dy)
            / max(4.0, self.maximum_shift_px),
        )
        if flow_consensus >= 0.25:
            dx = 0.55 * flow_dx + 0.45 * phase_dx
            dy = 0.55 * flow_dy + 0.45 * phase_dy
            confidence = 0.45 * phase_confidence + 0.40 * flow_consensus + 0.15 * agreement
            source = "PHASE_CORRELATION+LK_CONSENSUS"
            consensus = flow_consensus
        else:
            dx, dy = phase_dx, phase_dy
            confidence = 0.75 * phase_confidence + 0.25 * agreement
            source = "PHASE_CORRELATION"
            consensus = agreement

        magnitude = float(np.hypot(dx, dy))
        if not np.isfinite(magnitude) or magnitude > self.maximum_shift_px:
            dx = dy = 0.0
            confidence = 0.0
            source = "REJECTED_OUTLIER"
            consensus = 0.0

        compensated = confidence >= self.minimum_confidence
        if not compensated:
            dx = dy = 0.0
        self.previous_gray = work
        self.last = CameraMotionResult(
            dx_px=float(dx),
            dy_px=float(dy),
            confidence=float(max(0.0, min(1.0, confidence))),
            source=source,
            consensus=float(max(0.0, min(1.0, consensus))),
            compensated=compensated,
        )
        return self.last

    @staticmethod
    def align_previous_to_current(
        previous_bgr: np.ndarray,
        motion: CameraMotionResult,
    ) -> np.ndarray:
        matrix = np.float32([[1.0, 0.0, motion.dx_px], [0.0, 1.0, motion.dy_px]])
        return cv2.warpAffine(
            previous_bgr,
            matrix,
            (previous_bgr.shape[1], previous_bgr.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )


__all__ = ["CameraMotionEstimator", "CameraMotionResult"]
