from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np

from .pr27_entity_validation import CandidateClass, EntityCandidate
from .pr27_fixed_grid import NativeRect


class TrainerState(str, Enum):
    TRAINER_VISIBLE_CONFIRMED = "TRAINER_VISIBLE_CONFIRMED"
    TRAINER_VISUAL_UNCERTAIN = "TRAINER_VISUAL_UNCERTAIN"
    TRAINER_ABSENT = "TRAINER_ABSENT"
    TRAINER_OVERLAPPED = "TRAINER_OVERLAPPED"
    TRAINER_OUTSIDE_ROI = "TRAINER_OUTSIDE_ROI"
    TRAINER_IDENTITY_UNAVAILABLE = "TRAINER_IDENTITY_UNAVAILABLE"


@dataclass(slots=True)
class TrainerIdentity:
    template_gray: np.ndarray
    edge_map: np.ndarray
    histogram: np.ndarray
    silhouette: np.ndarray
    bbox_size: tuple[int, int]
    source_bbox: NativeRect
    detector_score: float
    detector_mode: str


@dataclass(frozen=True, slots=True)
class TrainerEvidence:
    state: TrainerState
    observed_bbox: NativeRect | None
    predicted_bbox: NativeRect | None
    identity_score: float
    current_frame_match: bool
    source: str
    candidate_vetoes: tuple[int, ...] = ()
    entity_detection_mask_pixels: int = 0


class TrainerIdentityTracker:
    """PR27.9 Trainer handling: identity veto, never a blind geometry mask."""

    def __init__(
        self,
        identity: TrainerIdentity | None = None,
        *,
        confirmed_threshold: float = 0.88,
        uncertain_threshold: float = 0.70,
        confirm_frames: int = 2,
        absent_frames: int = 2,
        search_margin: int = 96,
    ) -> None:
        self.identity = identity
        self.confirmed_threshold = float(confirmed_threshold)
        self.uncertain_threshold = float(uncertain_threshold)
        self.confirm_frames = max(1, int(confirm_frames))
        self.absent_frames = max(1, int(absent_frames))
        self.search_margin = max(16, int(search_margin))
        self.predicted_bbox = None if identity is None else identity.source_bbox
        self.confirmed_hits = 0
        self.missing_hits = 0
        self.last = TrainerEvidence(
            TrainerState.TRAINER_IDENTITY_UNAVAILABLE if identity is None else TrainerState.TRAINER_VISUAL_UNCERTAIN,
            None, self.predicted_bbox, 0.0, False, "INITIAL",
        )

    @staticmethod
    def _clip(rect: NativeRect, shape: tuple[int, int]) -> NativeRect | None:
        return rect.intersect(NativeRect(0, 0, shape[1], shape[0]))

    @staticmethod
    def _histogram(crop: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], mask, [8, 4], [0, 180, 0, 256]).reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(hist))
        return hist / norm if norm > 0 else hist

    @staticmethod
    def _cosine(left: np.ndarray, right: np.ndarray) -> float:
        if left.shape != right.shape or left.size == 0:
            return 0.0
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        if denominator <= 1e-9:
            return 0.0
        return float(max(0.0, min(1.0, np.dot(left.reshape(-1), right.reshape(-1)) / denominator)))

    @classmethod
    def capture(
        cls,
        frame_bgr: np.ndarray,
        bbox: NativeRect,
        *,
        detector_score: float = 1.0,
        detector_mode: str = "PRE_CLICK_CAPTURE",
    ) -> TrainerIdentity:
        clipped = cls._clip(bbox, frame_bgr.shape[:2])
        if clipped is None or clipped.width < 6 or clipped.height < 6:
            raise ValueError("PR27_TRAINER_IDENTITY_BBOX_INVALID")
        crop = frame_bgr[clipped.top:clipped.bottom, clipped.left:clipped.right]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edge = cv2.Canny(gray, 35, 100)
        background = int(np.median(gray))
        silhouette = np.where(np.abs(gray.astype(np.int16) - background) >= 12, 255, 0).astype(np.uint8)
        silhouette = cv2.morphologyEx(silhouette, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        return TrainerIdentity(
            template_gray=gray,
            edge_map=edge,
            histogram=cls._histogram(crop, silhouette),
            silhouette=silhouette,
            bbox_size=(clipped.width, clipped.height),
            source_bbox=clipped,
            detector_score=float(detector_score),
            detector_mode=str(detector_mode),
        )

    @staticmethod
    def _template_response(search_gray: np.ndarray, template_gray: np.ndarray) -> tuple[np.ndarray, bool]:
        if float(np.std(template_gray)) < 1.0:
            raw = cv2.matchTemplate(search_gray, template_gray, cv2.TM_SQDIFF_NORMED)
            return 1.0 - raw, True
        return cv2.matchTemplate(search_gray, template_gray, cv2.TM_CCOEFF_NORMED), False

    def observe(self, frame_bgr: np.ndarray, *, camera_dx: float = 0.0, camera_dy: float = 0.0) -> TrainerEvidence:
        if self.identity is None:
            self.last = TrainerEvidence(TrainerState.TRAINER_IDENTITY_UNAVAILABLE, None, None, 0.0, False, "NO_PRE_CLICK_IDENTITY")
            return self.last
        if self.predicted_bbox is None:
            self.predicted_bbox = self.identity.source_bbox
        self.predicted_bbox = NativeRect(
            self.predicted_bbox.left + int(round(camera_dx)),
            self.predicted_bbox.top + int(round(camera_dy)),
            self.predicted_bbox.right + int(round(camera_dx)),
            self.predicted_bbox.bottom + int(round(camera_dy)),
        )
        search = self._clip(
            self.predicted_bbox.expand(left=self.search_margin, right=self.search_margin, top=self.search_margin, bottom=self.search_margin),
            frame_bgr.shape[:2],
        )
        template = self.identity.template_gray
        if search is None or search.width < template.shape[1] or search.height < template.shape[0]:
            self.last = TrainerEvidence(TrainerState.TRAINER_OUTSIDE_ROI, None, self.predicted_bbox, 0.0, False, "SEARCH_OUTSIDE_FRAME")
            return self.last
        gray = cv2.cvtColor(frame_bgr[search.top:search.bottom, search.left:search.right], cv2.COLOR_BGR2GRAY)
        response, _constant_template = self._template_response(gray, template)
        _mn, maximum, _mnl, maximum_location = cv2.minMaxLoc(response)
        score = float(maximum)
        left = search.left + int(maximum_location[0])
        top = search.top + int(maximum_location[1])
        observed = NativeRect(left, top, left + template.shape[1], top + template.shape[0])
        if score >= self.confirmed_threshold:
            self.confirmed_hits += 1; self.missing_hits = 0; self.predicted_bbox = observed
            state = TrainerState.TRAINER_VISIBLE_CONFIRMED if self.confirmed_hits >= self.confirm_frames else TrainerState.TRAINER_VISUAL_UNCERTAIN
            source = "CURRENT_FRAME_IDENTITY_MATCH"
        elif score >= self.uncertain_threshold:
            self.confirmed_hits = 0; self.missing_hits = 0
            state = TrainerState.TRAINER_VISUAL_UNCERTAIN; source = "IDENTITY_BELOW_CONFIRMED_THRESHOLD"
        else:
            self.confirmed_hits = 0; self.missing_hits += 1
            state = TrainerState.TRAINER_ABSENT if self.missing_hits >= self.absent_frames else TrainerState.TRAINER_VISUAL_UNCERTAIN
            source = "IDENTITY_NOT_PRESENT"; observed = None
        self.last = TrainerEvidence(state, observed, self.predicted_bbox, score, state is TrainerState.TRAINER_VISIBLE_CONFIRMED, source, entity_detection_mask_pixels=0)
        return self.last

    def candidate_similarity(self, frame_bgr: np.ndarray, candidate: EntityCandidate) -> float:
        if self.identity is None:
            return 0.0
        rect = self._clip(candidate.bbox, frame_bgr.shape[:2])
        if rect is None or rect.width < 4 or rect.height < 4:
            return 0.0
        crop = frame_bgr[rect.top:rect.bottom, rect.left:rect.right]
        resized = cv2.resize(crop, self.identity.bbox_size, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        edge = cv2.Canny(gray, 35, 100)
        hist = self._histogram(resized)
        response, _constant_template = self._template_response(gray, self.identity.template_gray)
        template_match = float(response[0, 0])
        edge_union = int(np.count_nonzero((edge > 0) | (self.identity.edge_map > 0)))
        edge_iou = 1.0 if edge_union == 0 else float(np.count_nonzero((edge > 0) & (self.identity.edge_map > 0)) / edge_union)
        hist_score = self._cosine(hist, self.identity.histogram)
        size_score = min(
            rect.width / max(1, self.identity.bbox_size[0]), self.identity.bbox_size[0] / max(1, rect.width),
            rect.height / max(1, self.identity.bbox_size[1]), self.identity.bbox_size[1] / max(1, rect.height),
        )
        return float(max(0.0, min(1.0, 0.45 * template_match + 0.20 * edge_iou + 0.25 * hist_score + 0.10 * size_score)))

    def veto_candidates(
        self,
        frame_bgr: np.ndarray,
        candidates: tuple[EntityCandidate, ...],
        *,
        threshold: float = 0.82,
    ) -> tuple[tuple[EntityCandidate, ...], tuple[int, ...], dict[int, float]]:
        preserved: list[EntityCandidate] = []
        vetoed: list[int] = []
        scores: dict[int, float] = {}
        for candidate in candidates:
            score = self.candidate_similarity(frame_bgr, candidate)
            scores[candidate.candidate_id] = score
            if score >= threshold:
                candidate.candidate_class = CandidateClass.NPC
                candidate.rejection_reason = "TRAINER_IDENTITY_MATCH"
                vetoed.append(candidate.candidate_id)
            else:
                preserved.append(candidate)
        self.last = TrainerEvidence(
            state=self.last.state, observed_bbox=self.last.observed_bbox, predicted_bbox=self.last.predicted_bbox,
            identity_score=self.last.identity_score, current_frame_match=self.last.current_frame_match,
            source=self.last.source, candidate_vetoes=tuple(vetoed), entity_detection_mask_pixels=0,
        )
        return tuple(preserved), tuple(vetoed), scores


__all__ = ["TrainerEvidence", "TrainerIdentity", "TrainerIdentityTracker", "TrainerState"]
