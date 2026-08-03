from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

import cv2
import numpy as np

from .pr27_entity_validation import CandidateClass, EntityCandidate
from .pr27_fixed_grid import FixedNativeGridCalibration, NativeRect


class ObjectTrackState(str, Enum):
    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    RGB_PREDICTED = "RGB_PREDICTED"
    TEMPORARILY_MISSING = "TEMPORARILY_MISSING"
    LOST = "LOST"


@dataclass(slots=True)
class PersistentObjectTrack:
    track_id: int
    candidate: EntityCandidate
    first_seen_frame: int
    last_seen_frame: int
    observations: int = 1
    missing_frames: int = 0
    visible: bool = True
    state: ObjectTrackState = ObjectTrackState.TENTATIVE
    velocity: tuple[float, float] = (0.0, 0.0)
    appearance_descriptor: np.ndarray = field(default_factory=lambda: np.zeros(32, dtype=np.float32))
    edge_descriptor: np.ndarray = field(default_factory=lambda: np.zeros((24, 24), dtype=np.uint8))
    silhouette_descriptor: np.ndarray = field(default_factory=lambda: np.zeros((24, 24), dtype=np.uint8))
    rgb_template: np.ndarray = field(default_factory=lambda: np.zeros((1, 1, 3), dtype=np.uint8))
    size_history: deque[tuple[int, int]] = field(default_factory=lambda: deque(maxlen=16))
    anchor_history: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=24))
    confidence_history: deque[float] = field(default_factory=lambda: deque(maxlen=24))
    source: str = "RAW_DIFFERENCE"
    noise_gate_overrides: int = 0
    trainer_similarity: float = 0.0
    self_similarity: float = 0.0
    lineage: tuple[int, ...] = ()
    spawned_after_dojo: bool = False

    @property
    def bbox(self) -> NativeRect:
        return self.candidate.bbox

    @property
    def feet_anchor(self) -> tuple[float, float]:
        return self.candidate.feet_anchor

    @property
    def relative_cell(self) -> tuple[int, int] | None:
        return self.candidate.relative_cell

    @property
    def confirmed(self) -> bool:
        return self.state in {ObjectTrackState.CONFIRMED, ObjectTrackState.RGB_PREDICTED}


class PersistentObjectTracker:
    """Object-first tracker.

    Raw difference may open a track. Once acquired, the track continues using RGB,
    appearance, silhouette and predicted geometry even when the next difference
    frame is quiet or fragmented.
    """

    def __init__(
        self,
        grid: FixedNativeGridCalibration,
        *,
        confirm_frames: int = 2,
        missing_frames: int = 8,
        reid_frames: int = 16,
        max_jump_px: float = 64.0,
        same_cell_max_jump_px: float = 32.0,
    ) -> None:
        self.grid = grid
        self.confirm_frames = max(1, int(confirm_frames))
        self.maximum_missing_frames = max(1, int(missing_frames))
        self.reid_frames = max(self.maximum_missing_frames, int(reid_frames))
        self.max_jump_px = max(8.0, float(max_jump_px))
        self.same_cell_max_jump_px = max(4.0, float(same_cell_max_jump_px))
        self.tracks: dict[int, PersistentObjectTrack] = {}
        self._next_track_id = 1

    @staticmethod
    def _clip(rect: NativeRect, shape: tuple[int, int]) -> NativeRect | None:
        return rect.intersect(NativeRect(0, 0, shape[1], shape[0]))

    @staticmethod
    def _crop(frame: np.ndarray, rect: NativeRect) -> np.ndarray:
        return frame[rect.top:rect.bottom, rect.left:rect.right].copy()

    @staticmethod
    def _edge_and_silhouette(crop: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if crop.size == 0:
            return np.zeros((24, 24), np.uint8), np.zeros((24, 24), np.uint8)
        resized = cv2.resize(crop, (24, 24), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        edge = cv2.Canny(gray, 30, 90)
        median = int(np.median(gray))
        silhouette = np.where(np.abs(gray.astype(np.int16) - median) >= 12, 255, 0).astype(np.uint8)
        return edge, silhouette

    @staticmethod
    def _cosine(left: np.ndarray, right: np.ndarray) -> float:
        if left.shape != right.shape or left.size == 0:
            return 0.0
        lf = left.astype(np.float32).reshape(-1)
        rf = right.astype(np.float32).reshape(-1)
        denominator = float(np.linalg.norm(lf) * np.linalg.norm(rf))
        if denominator <= 1e-9:
            return 0.0
        return float(max(0.0, min(1.0, np.dot(lf, rf) / denominator)))

    @staticmethod
    def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
        return float(np.hypot(left[0] - right[0], left[1] - right[1]))

    @staticmethod
    def _bbox_iou(left: NativeRect, right: NativeRect) -> float:
        intersection = left.intersect(right)
        if intersection is None:
            return 0.0
        inter = intersection.width * intersection.height
        union = left.width * left.height + right.width * right.height - inter
        return float(inter / max(1, union))

    def _candidate_score(self, track: PersistentObjectTrack, candidate: EntityCandidate) -> float:
        predicted = (
            track.feet_anchor[0] + track.velocity[0],
            track.feet_anchor[1] + track.velocity[1],
        )
        distance = self._distance(predicted, candidate.feet_anchor)
        same_cell = track.relative_cell is not None and track.relative_cell == candidate.relative_cell
        limit = self.same_cell_max_jump_px if same_cell else self.max_jump_px
        limit += track.missing_frames * 12.0
        if distance > limit:
            return 0.0
        proximity = max(0.0, 1.0 - distance / max(1.0, limit))
        appearance = self._cosine(track.appearance_descriptor, candidate.descriptor)
        size = min(
            track.bbox.width / max(1, candidate.bbox.width),
            candidate.bbox.width / max(1, track.bbox.width),
            track.bbox.height / max(1, candidate.bbox.height),
            candidate.bbox.height / max(1, track.bbox.height),
        )
        iou = self._bbox_iou(track.bbox, candidate.bbox)
        return float(0.42 * proximity + 0.28 * appearance + 0.18 * size + 0.12 * iou)

    def _new_track(self, frame: np.ndarray, candidate: EntityCandidate, frame_index: int) -> PersistentObjectTrack:
        rect = self._clip(candidate.bbox, frame.shape[:2])
        crop = np.zeros((1, 1, 3), dtype=np.uint8) if rect is None else self._crop(frame, rect)
        edge, silhouette = self._edge_and_silhouette(crop)
        track = PersistentObjectTrack(
            track_id=self._next_track_id,
            candidate=candidate,
            first_seen_frame=frame_index,
            last_seen_frame=frame_index,
            appearance_descriptor=candidate.descriptor.copy(),
            edge_descriptor=edge,
            silhouette_descriptor=silhouette,
            rgb_template=crop,
            lineage=(candidate.candidate_id,),
        )
        track.size_history.append((candidate.bbox.width, candidate.bbox.height))
        track.anchor_history.append(candidate.feet_anchor)
        track.confidence_history.append(candidate.humanoid_confidence)
        self.tracks[track.track_id] = track
        self._next_track_id += 1
        return track

    def _update_from_candidate(
        self,
        frame: np.ndarray,
        track: PersistentObjectTrack,
        candidate: EntityCandidate,
        frame_index: int,
        *,
        source: str = "DIFFERENCE_ASSOCIATION",
    ) -> None:
        old_anchor = track.feet_anchor
        new_anchor = candidate.feet_anchor
        track.velocity = (new_anchor[0] - old_anchor[0], new_anchor[1] - old_anchor[1])
        track.candidate = candidate
        track.last_seen_frame = frame_index
        track.observations += 1
        track.missing_frames = 0
        track.visible = True
        track.state = ObjectTrackState.CONFIRMED if track.observations >= self.confirm_frames else ObjectTrackState.TENTATIVE
        track.source = source
        track.appearance_descriptor = (0.82 * track.appearance_descriptor + 0.18 * candidate.descriptor).astype(np.float32)
        rect = self._clip(candidate.bbox, frame.shape[:2])
        if rect is not None and rect.width >= 4 and rect.height >= 4:
            crop = self._crop(frame, rect)
            edge, silhouette = self._edge_and_silhouette(crop)
            track.edge_descriptor = np.where((track.edge_descriptor > 0) | (edge > 0), 255, 0).astype(np.uint8)
            track.silhouette_descriptor = np.where((track.silhouette_descriptor > 0) | (silhouette > 0), 255, 0).astype(np.uint8)
            if track.rgb_template.size <= 3:
                track.rgb_template = crop
            else:
                template_size = (track.rgb_template.shape[1], track.rgb_template.shape[0])
                resized = cv2.resize(crop, template_size, interpolation=cv2.INTER_AREA)
                track.rgb_template = np.clip(
                    track.rgb_template.astype(np.float32) * 0.90 + resized.astype(np.float32) * 0.10,
                    0,
                    255,
                ).astype(np.uint8)
        track.size_history.append((candidate.bbox.width, candidate.bbox.height))
        track.anchor_history.append(candidate.feet_anchor)
        track.confidence_history.append(candidate.humanoid_confidence)
        track.lineage = tuple((*track.lineage[-15:], candidate.candidate_id))

    def _rgb_reacquire(self, frame: np.ndarray, track: PersistentObjectTrack, frame_index: int) -> bool:
        template = track.rgb_template
        if template.size <= 3 or template.shape[0] < 4 or template.shape[1] < 4:
            return False
        predicted_anchor = (
            track.feet_anchor[0] + track.velocity[0],
            track.feet_anchor[1] + track.velocity[1],
        )
        width, height = track.bbox.width, track.bbox.height
        predicted = NativeRect(
            int(round(predicted_anchor[0] - width / 2.0)),
            int(round(predicted_anchor[1] - height + 1.0)),
            int(round(predicted_anchor[0] - width / 2.0)) + width,
            int(round(predicted_anchor[1] - height + 1.0)) + height,
        )
        margin = int(24 + track.missing_frames * 8)
        search = self._clip(predicted.expand(left=margin, right=margin, top=margin, bottom=margin), frame.shape[:2])
        if search is None or search.width < template.shape[1] or search.height < template.shape[0]:
            return False
        search_crop = frame[search.top:search.bottom, search.left:search.right]
        gray = cv2.cvtColor(search_crop, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        response = cv2.matchTemplate(gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _mn, maximum, _mnl, maximum_location = cv2.minMaxLoc(response)
        if float(maximum) < 0.68:
            return False
        left = search.left + int(maximum_location[0])
        top = search.top + int(maximum_location[1])
        rect = NativeRect(left, top, left + template.shape[1], top + template.shape[0])
        feet = ((rect.left + rect.right) / 2.0, rect.bottom - 1.0)
        cell = self.grid.cell_for_native_point(*feet)
        candidate = EntityCandidate(
            candidate_id=track.candidate.candidate_id,
            bbox=rect,
            feet_anchor=feet,
            relative_cell=None if cell is None else cell.relative_key,
            area=rect.width * rect.height,
            component_pixels=track.candidate.component_pixels,
            occupancy=track.candidate.occupancy,
            aspect_ratio=rect.width / max(1.0, float(rect.height)),
            solidity=track.candidate.solidity,
            vertical_score=track.candidate.vertical_score,
            feet_support_score=track.candidate.feet_support_score,
            rigidity_score=max(track.candidate.rigidity_score, float(maximum)),
            entity_confidence=max(track.candidate.entity_confidence, float(maximum)),
            humanoid_confidence=track.candidate.humanoid_confidence,
            candidate_class=track.candidate.candidate_class,
            rejection_reason=None,
            descriptor=track.appearance_descriptor.copy(),
        )
        self._update_from_candidate(frame, track, candidate, frame_index, source="RGB_TEMPLATE_REACQUIRE")
        track.state = ObjectTrackState.RGB_PREDICTED
        return True

    def update(
        self,
        frame_bgr: np.ndarray,
        candidates: Iterable[EntityCandidate],
        *,
        frame_index: int,
    ) -> tuple[PersistentObjectTrack, ...]:
        body_candidates = [
            candidate
            for candidate in candidates
            if candidate.candidate_class in {
                CandidateClass.HUMANOID_CANDIDATE,
                CandidateClass.OPPONENT_CANDIDATE,
                CandidateClass.HOSTILITY_PENDING,
                CandidateClass.HOSTILE_CONFIRMED,
            }
        ]
        scored: list[tuple[float, int, int]] = []
        for track_id, track in self.tracks.items():
            if track.state is ObjectTrackState.LOST:
                continue
            for index, candidate in enumerate(body_candidates):
                score = self._candidate_score(track, candidate)
                if score >= 0.42:
                    scored.append((score, track_id, index))
        used_tracks: set[int] = set()
        used_candidates: set[int] = set()
        for _score, track_id, candidate_index in sorted(scored, reverse=True):
            if track_id in used_tracks or candidate_index in used_candidates:
                continue
            track = self.tracks[track_id]
            candidate = body_candidates[candidate_index]
            self._update_from_candidate(frame_bgr, track, candidate, frame_index)
            used_tracks.add(track_id)
            used_candidates.add(candidate_index)

        for index, candidate in enumerate(body_candidates):
            if index not in used_candidates:
                track = self._new_track(frame_bgr, candidate, frame_index)
                used_tracks.add(track.track_id)

        for track_id, track in list(self.tracks.items()):
            if track.last_seen_frame == frame_index:
                continue
            if self._rgb_reacquire(frame_bgr, track, frame_index):
                used_tracks.add(track_id)
                continue
            track.missing_frames += 1
            track.visible = False
            track.state = (
                ObjectTrackState.TEMPORARILY_MISSING
                if track.missing_frames <= self.maximum_missing_frames
                else ObjectTrackState.LOST
            )
            if track.missing_frames > self.reid_frames:
                del self.tracks[track_id]

        return tuple(sorted(self.tracks.values(), key=lambda item: item.track_id))

    def confirmed_tracks(self) -> tuple[PersistentObjectTrack, ...]:
        return tuple(
            track
            for track in sorted(self.tracks.values(), key=lambda item: item.track_id)
            if track.confirmed and track.state is not ObjectTrackState.LOST
        )

    def track_mask(self, shape: tuple[int, int], *, include_missing: bool = True) -> np.ndarray:
        mask = np.zeros(shape, dtype=np.uint8)
        for track in self.tracks.values():
            if track.state is ObjectTrackState.LOST:
                continue
            if not include_missing and not track.visible:
                continue
            rect = self._clip(track.bbox, shape)
            if rect is not None:
                mask[rect.top:rect.bottom, rect.left:rect.right] = 255
        return mask


__all__ = [
    "ObjectTrackState",
    "PersistentObjectTrack",
    "PersistentObjectTracker",
]
