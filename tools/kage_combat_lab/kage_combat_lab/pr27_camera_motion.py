from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np


class CameraMode(str, Enum):
    STATIONARY_PERCEPTION = "STATIONARY_PERCEPTION"
    COMMAND_EXPECTED_CAMERA_SHIFT = "COMMAND_EXPECTED_CAMERA_SHIFT"
    UNKNOWN_CAMERA_STATE = "UNKNOWN_CAMERA_STATE"


@dataclass(frozen=True, slots=True)
class CameraMotionResult:
    dx_px: float = 0.0
    dy_px: float = 0.0
    confidence: float = 0.0
    source: str = "INITIAL_FRAME"
    consensus: float = 0.0
    compensated: bool = False
    phase_dx: float = 0.0
    phase_dy: float = 0.0
    phase_confidence: float = 0.0
    flow_dx: float = 0.0
    flow_dy: float = 0.0
    flow_consensus: float = 0.0
    phase_flow_disagreement: float = 0.0
    stationary_mode: bool = False
    shift_accepted: bool = False
    shift_rejection_reason: str | None = None
    feature_count: int = 0

    @property
    def shift(self) -> tuple[float, float]:
        return self.dx_px, self.dy_px

    @property
    def raw_shift(self) -> tuple[float, float]:
        return self.phase_dx, self.phase_dy


class CameraMotionEstimator:
    """Estimate dominant terrain translation using trusted static regions."""

    def __init__(
        self,
        *,
        maximum_shift_px: float = 96.0,
        minimum_confidence: float = 0.18,
        downsample: float = 0.5,
        stationary_camera_max_shift_px: float = 2.0,
        stationary_camera_deadband_px: float = 0.75,
        stationary_outlier_confirm_frames: int = 3,
    ) -> None:
        self.maximum_shift_px = max(8.0, float(maximum_shift_px))
        self.minimum_confidence = min(1.0, max(0.0, float(minimum_confidence)))
        self.downsample = min(1.0, max(0.2, float(downsample)))
        self.stationary_camera_max_shift_px = max(0.5, float(stationary_camera_max_shift_px))
        self.stationary_camera_deadband_px = max(0.0, float(stationary_camera_deadband_px))
        self.stationary_outlier_confirm_frames = max(1, int(stationary_outlier_confirm_frames))
        self.previous_gray: np.ndarray | None = None
        self.last = CameraMotionResult()
        self._stationary_outlier_frames = 0

    @staticmethod
    def _prepare(frame_bgr: np.ndarray, exclusion_mask: np.ndarray | None, static_terrain_mask: np.ndarray | None) -> np.ndarray:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        allowed = np.ones(gray.shape, dtype=bool)
        if exclusion_mask is not None:
            if exclusion_mask.shape != gray.shape:
                raise ValueError("PR27_CAMERA_MASK_SHAPE_MISMATCH")
            allowed &= exclusion_mask == 0
        if static_terrain_mask is not None:
            if static_terrain_mask.shape != gray.shape:
                raise ValueError("PR27_CAMERA_STATIC_TERRAIN_MASK_SHAPE_MISMATCH")
            allowed &= static_terrain_mask > 0
        fill = int(np.median(gray[allowed])) if np.any(allowed) else int(np.median(gray))
        output = gray.copy()
        output[~allowed] = fill
        return output

    @staticmethod
    def _phase_shift(previous: np.ndarray, current: np.ndarray) -> tuple[float, float, float]:
        window = cv2.createHanningWindow((previous.shape[1], previous.shape[0]), cv2.CV_32F)
        shift, response = cv2.phaseCorrelate(previous.astype(np.float32), current.astype(np.float32), window)
        return float(shift[0]), float(shift[1]), float(max(0.0, min(1.0, response)))

    @staticmethod
    def _flow_shift(previous: np.ndarray, current: np.ndarray) -> tuple[float, float, float, int]:
        points = cv2.goodFeaturesToTrack(previous, maxCorners=300, qualityLevel=0.01, minDistance=8, blockSize=7)
        if points is None or len(points) < 8:
            return 0.0, 0.0, 0.0, 0
        next_points, status, _errors = cv2.calcOpticalFlowPyrLK(
            previous, current, points, None, winSize=(21, 21), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )
        if next_points is None or status is None:
            return 0.0, 0.0, 0.0, 0
        valid = status.reshape(-1) == 1
        valid_count = int(np.count_nonzero(valid))
        if valid_count < 8:
            return 0.0, 0.0, 0.0, valid_count
        vectors = next_points.reshape(-1, 2)[valid] - points.reshape(-1, 2)[valid]
        median = np.median(vectors, axis=0)
        distances = np.linalg.norm(vectors - median, axis=1)
        inliers = distances <= max(1.5, float(np.median(distances)) * 2.5)
        inlier_count = int(np.count_nonzero(inliers))
        if inlier_count < 6:
            return float(median[0]), float(median[1]), 0.0, valid_count
        refined = np.median(vectors[inliers], axis=0)
        return float(refined[0]), float(refined[1]), float(inlier_count / len(vectors)), valid_count

    def observe(
        self,
        frame_bgr: np.ndarray,
        *,
        exclusion_mask: np.ndarray | None = None,
        static_terrain_mask: np.ndarray | None = None,
        stationary_mode: bool = False,
    ) -> CameraMotionResult:
        gray = self._prepare(frame_bgr, exclusion_mask, static_terrain_mask)
        work = cv2.resize(gray, None, fx=self.downsample, fy=self.downsample, interpolation=cv2.INTER_AREA) if self.downsample != 1.0 else gray
        if self.previous_gray is None or self.previous_gray.shape != work.shape:
            self.previous_gray = work
            self.last = CameraMotionResult(stationary_mode=bool(stationary_mode))
            return self.last
        phase_dx, phase_dy, phase_confidence = self._phase_shift(self.previous_gray, work)
        flow_dx, flow_dy, flow_consensus, feature_count = self._flow_shift(self.previous_gray, work)
        scale = 1.0 / self.downsample
        phase_dx *= scale; phase_dy *= scale; flow_dx *= scale; flow_dy *= scale
        disagreement = float(np.hypot(phase_dx - flow_dx, phase_dy - flow_dy))
        agreement = max(0.0, 1.0 - disagreement / max(4.0, self.maximum_shift_px))
        if flow_consensus >= 0.25:
            raw_dx = 0.55 * flow_dx + 0.45 * phase_dx
            raw_dy = 0.55 * flow_dy + 0.45 * phase_dy
            confidence = 0.45 * phase_confidence + 0.40 * flow_consensus + 0.15 * agreement
            source = "PHASE_CORRELATION+LK_CONSENSUS"
            consensus = flow_consensus
        else:
            raw_dx, raw_dy = phase_dx, phase_dy
            confidence = 0.75 * phase_confidence + 0.25 * agreement
            source = "PHASE_CORRELATION"
            consensus = agreement
        magnitude = float(np.hypot(raw_dx, raw_dy))
        accepted = True
        rejection: str | None = None
        dx, dy = raw_dx, raw_dy
        if not np.isfinite(magnitude) or magnitude > self.maximum_shift_px:
            accepted = False; rejection = "CAMERA_SHIFT_REJECTED_OUTLIER"
        elif stationary_mode and magnitude > self.stationary_camera_max_shift_px:
            self._stationary_outlier_frames += 1
            accepted = False; rejection = "CAMERA_SHIFT_REJECTED_STATIONARY_MODE"
        elif disagreement > max(4.0, self.stationary_camera_max_shift_px * 2.0) and flow_consensus >= 0.25:
            accepted = False; rejection = "CAMERA_SHIFT_REJECTED_PHASE_FLOW_DISAGREEMENT"
        elif confidence < self.minimum_confidence:
            accepted = False; rejection = "CAMERA_SHIFT_REJECTED_LOW_CONFIDENCE"
        else:
            self._stationary_outlier_frames = 0
        if stationary_mode and accepted and magnitude <= self.stationary_camera_deadband_px:
            dx = dy = 0.0; source = "STATIONARY_DEADBAND"
        elif not accepted:
            dx = dy = 0.0
        self.previous_gray = work
        self.last = CameraMotionResult(
            dx_px=float(dx), dy_px=float(dy), confidence=float(max(0.0, min(1.0, confidence))),
            source=source, consensus=float(max(0.0, min(1.0, consensus))), compensated=bool(accepted),
            phase_dx=float(phase_dx), phase_dy=float(phase_dy), phase_confidence=float(phase_confidence),
            flow_dx=float(flow_dx), flow_dy=float(flow_dy), flow_consensus=float(flow_consensus),
            phase_flow_disagreement=disagreement, stationary_mode=bool(stationary_mode),
            shift_accepted=bool(accepted), shift_rejection_reason=rejection, feature_count=feature_count,
        )
        return self.last

    @staticmethod
    def align_previous_to_current(previous_bgr: np.ndarray, motion: CameraMotionResult) -> np.ndarray:
        if not motion.shift_accepted:
            return previous_bgr.copy()
        matrix = np.float32([[1.0, 0.0, motion.dx_px], [0.0, 1.0, motion.dy_px]])
        return cv2.warpAffine(previous_bgr, matrix, (previous_bgr.shape[1], previous_bgr.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


__all__ = ["CameraMode", "CameraMotionEstimator", "CameraMotionResult"]
