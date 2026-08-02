from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from .domain import (
    BACKGROUND_REJECT_SCORE,
    REID_ACCEPT_SCORE,
    REID_MIN_APPEARANCE_SCORE,
    CandidateObservation,
    CombatFrame,
    GridCell,
    ObservationKind,
    cardinal_face,
)


@dataclass(slots=True)
class VisualDescriptor:
    hsv_hist: np.ndarray
    gray_signature: np.ndarray
    edge_signature: np.ndarray
    width: int
    height: int

    @property
    def aspect(self) -> float:
        return float(self.height) / float(max(1, self.width))


@dataclass(slots=True)
class TargetExemplar:
    descriptor: VisualDescriptor
    timestamp: float
    confidence: float
    filename: str | None
    face: str | None
    grid_distance: int | None


@dataclass(slots=True)
class _BackgroundEntry:
    descriptor: VisualDescriptor
    observations: int
    last_seen: float


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _cosine01(left: np.ndarray, right: np.ndarray) -> float:
    left_flat = left.astype(np.float32, copy=False).reshape(-1)
    right_flat = right.astype(np.float32, copy=False).reshape(-1)
    denominator = float(np.linalg.norm(left_flat) * np.linalg.norm(right_flat))
    if denominator <= 1e-8:
        return 0.0
    cosine = float(np.dot(left_flat, right_flat) / denominator)
    return _clamp01((cosine + 1.0) * 0.5)


def describe_crop(crop_bgr: np.ndarray) -> VisualDescriptor:
    if crop_bgr is None or crop_bgr.size == 0:
        raise ValueError("TARGET_DESCRIPTOR_EMPTY_CROP")
    if crop_bgr.ndim == 2:
        crop_bgr = cv2.cvtColor(crop_bgr, cv2.COLOR_GRAY2BGR)
    elif crop_bgr.shape[2] == 4:
        crop_bgr = cv2.cvtColor(crop_bgr, cv2.COLOR_BGRA2BGR)

    height, width = crop_bgr.shape[:2]
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    hist = cv2.normalize(hist, None, alpha=1.0, norm_type=cv2.NORM_L1).reshape(-1)

    gray_u8 = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    gray_u8 = cv2.resize(gray_u8, (32, 32), interpolation=cv2.INTER_AREA)
    gray_u8 = cv2.equalizeHist(gray_u8)
    gray = gray_u8.astype(np.float32)
    gray -= float(np.mean(gray))
    std = float(np.std(gray))
    if std > 1e-6:
        gray /= std

    edges = cv2.Canny(cv2.GaussianBlur(gray_u8, (3, 3), 0), 40, 120)
    edges = cv2.resize(edges, (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

    return VisualDescriptor(
        hsv_hist=hist.astype(np.float32),
        gray_signature=gray,
        edge_signature=edges,
        width=int(width),
        height=int(height),
    )


def appearance_similarity(left: VisualDescriptor, right: VisualDescriptor) -> float:
    histogram = float(
        cv2.compareHist(
            left.hsv_hist.astype(np.float32),
            right.hsv_hist.astype(np.float32),
            cv2.HISTCMP_INTERSECT,
        )
    )
    histogram = _clamp01(histogram)
    gray = _cosine01(left.gray_signature, right.gray_signature)
    edge = 1.0 - float(
        np.mean(np.abs(left.edge_signature - right.edge_signature))
    )
    return _clamp01(histogram * 0.45 + gray * 0.35 + _clamp01(edge) * 0.20)


def shape_similarity(left: VisualDescriptor, right: VisualDescriptor) -> float:
    width_ratio = min(left.width, right.width) / max(1.0, float(max(left.width, right.width)))
    height_ratio = min(left.height, right.height) / max(
        1.0, float(max(left.height, right.height))
    )
    aspect_ratio = min(left.aspect, right.aspect) / max(
        1e-6, max(left.aspect, right.aspect)
    )
    return _clamp01((width_ratio + height_ratio + aspect_ratio) / 3.0)


def _crop_for_bbox(
    frame_bgr: np.ndarray,
    arena_rect: tuple[int, int, int, int],
    bbox: tuple[int, int, int, int],
    *,
    padding: int = 3,
) -> np.ndarray | None:
    x0, y0, _, _ = (int(value) for value in arena_rect)
    left, top, width, height = (int(value) for value in bbox)
    full_left = max(0, x0 + left - padding)
    full_top = max(0, y0 + top - padding)
    full_right = min(frame_bgr.shape[1], x0 + left + max(1, width) + padding)
    full_bottom = min(frame_bgr.shape[0], y0 + top + max(1, height) + padding)
    if full_right <= full_left or full_bottom <= full_top:
        return None
    return frame_bgr[full_top:full_bottom, full_left:full_right].copy()


class TargetCapsuleMemory:
    """Per-round visual identity and negative environment memory.

    The logical target owns a small bank of trustworthy sprite exemplars. New
    OpenCV tracks are matched against appearance, predicted position, shape,
    independent motion, and foreground evidence. Rejected stable regions become
    negative background evidence instead of future enemies.
    """

    def __init__(
        self,
        *,
        root: Path | str | None = None,
        max_exemplars: int = 12,
        exemplar_interval_seconds: float = 0.45,
        background_tile_size: int = 32,
        reid_accept_score: float = REID_ACCEPT_SCORE,
        min_appearance_score: float = REID_MIN_APPEARANCE_SCORE,
    ) -> None:
        self.root = Path(root) if root is not None else None
        self.max_exemplars = max(4, min(24, int(max_exemplars)))
        self.exemplar_interval_seconds = max(0.20, float(exemplar_interval_seconds))
        self.background_tile_size = max(16, min(64, int(background_tile_size)))
        self.reid_accept_score = _clamp01(reid_accept_score)
        self.min_appearance_score = _clamp01(min_appearance_score)

        self.logical_target_id = "round-enemy-1"
        self.exemplars: list[TargetExemplar] = []
        self.last_foot: tuple[float, float] | None = None
        self.previous_foot: tuple[float, float] | None = None
        self.last_seen_at: float | None = None
        self.velocity_px_s = (0.0, 0.0)
        self.camera_offset = [0.0, 0.0]
        self._background: dict[tuple[int, int], _BackgroundEntry] = {}
        self._last_exemplar_at = -1e9
        self._last_selected_track_id: int | None = None

        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)
            self._write_manifest()

    @property
    def ready(self) -> bool:
        return bool(self.exemplars)

    @property
    def last_selected_track_id(self) -> int | None:
        return self._last_selected_track_id

    @property
    def background_cell_count(self) -> int:
        return len(self._background)

    def _world_key(self, foot: tuple[float, float]) -> tuple[int, int]:
        world_x = float(foot[0]) - float(self.camera_offset[0])
        world_y = float(foot[1]) - float(self.camera_offset[1])
        return (
            math.floor(world_x / self.background_tile_size),
            math.floor(world_y / self.background_tile_size),
        )

    def _background_probability(
        self,
        descriptor: VisualDescriptor,
        foot: tuple[float, float],
    ) -> float:
        entry = self._background.get(self._world_key(foot))
        if entry is None or entry.observations < 3:
            return 0.0
        similarity = appearance_similarity(descriptor, entry.descriptor)
        maturity = min(1.0, float(entry.observations) / 8.0)
        return _clamp01(similarity * maturity)

    def _learn_background(
        self,
        descriptor: VisualDescriptor,
        foot: tuple[float, float],
        *,
        timestamp: float,
    ) -> None:
        key = self._world_key(foot)
        entry = self._background.get(key)
        if entry is None:
            self._background[key] = _BackgroundEntry(descriptor, 1, timestamp)
            return
        similarity = appearance_similarity(descriptor, entry.descriptor)
        if similarity >= 0.72:
            entry.observations = min(1000, entry.observations + 1)
            entry.last_seen = timestamp
        elif timestamp - entry.last_seen > 3.0:
            self._background[key] = _BackgroundEntry(descriptor, 1, timestamp)

    def predicted_foot(
        self,
        *,
        timestamp: float,
        flow: object | None = None,
    ) -> tuple[float, float] | None:
        if self.last_foot is None or self.last_seen_at is None:
            return None
        dt = max(0.0, min(1.0, float(timestamp) - float(self.last_seen_at)))
        flow_dx = float(getattr(flow, "dx", 0.0) or 0.0)
        flow_dy = float(getattr(flow, "dy", 0.0) or 0.0)
        return (
            self.last_foot[0] + self.velocity_px_s[0] * dt + flow_dx,
            self.last_foot[1] + self.velocity_px_s[1] * dt + flow_dy,
        )

    def _score_descriptor(
        self,
        descriptor: VisualDescriptor,
        *,
        foot: tuple[float, float],
        predicted_foot: tuple[float, float] | None,
        motion_score: float,
        background_probability: float,
    ) -> tuple[float, float, float]:
        if not self.exemplars:
            return 0.0, 0.0, 0.0

        appearance = max(
            appearance_similarity(descriptor, exemplar.descriptor)
            for exemplar in self.exemplars
        )
        shape = max(
            shape_similarity(descriptor, exemplar.descriptor)
            for exemplar in self.exemplars
        )
        if predicted_foot is None:
            position = 0.45
        else:
            distance = math.hypot(
                float(foot[0]) - float(predicted_foot[0]),
                float(foot[1]) - float(predicted_foot[1]),
            )
            position = math.exp(-distance / 96.0)

        foreground = 1.0 - background_probability
        identity = (
            appearance * 0.35
            + position * 0.25
            + shape * 0.15
            + _clamp01(motion_score) * 0.15
            + foreground * 0.10
        )
        return _clamp01(identity), _clamp01(appearance), _clamp01(shape)

    def enrich_candidates(
        self,
        *,
        frame_bgr: np.ndarray,
        state: object,
        candidates: Iterable[CandidateObservation],
        timestamp: float,
    ) -> tuple[CandidateObservation, ...]:
        flow = getattr(state, "global_flow", None)
        self.camera_offset[0] += float(getattr(flow, "dx", 0.0) or 0.0)
        self.camera_offset[1] += float(getattr(flow, "dy", 0.0) or 0.0)
        predicted = self.predicted_foot(timestamp=timestamp, flow=flow)
        arena_rect = tuple(int(value) for value in getattr(state, "arena_rect"))

        enriched: list[CandidateObservation] = []
        descriptor_rows: list[
            tuple[CandidateObservation, VisualDescriptor, tuple[float, float]]
        ] = []

        for candidate in candidates:
            if candidate.bbox is None or candidate.foot_point is None:
                enriched.append(candidate)
                continue
            crop = _crop_for_bbox(frame_bgr, arena_rect, candidate.bbox)
            if crop is None or crop.size == 0:
                enriched.append(candidate)
                continue
            descriptor = describe_crop(crop)
            foot = (float(candidate.foot_point[0]), float(candidate.foot_point[1]))
            background_probability = self._background_probability(descriptor, foot)
            identity, appearance, shape = self._score_descriptor(
                descriptor,
                foot=foot,
                predicted_foot=predicted,
                motion_score=candidate.motion_score,
                background_probability=background_probability,
            )

            reidentified = (
                self.ready
                and not candidate.is_clean_body
                and identity >= self.reid_accept_score
                and appearance >= self.min_appearance_score
                and background_probability < BACKGROUND_REJECT_SCORE
            )
            kind = (
                ObservationKind.REIDENTIFIED_BODY
                if reidentified
                else candidate.kind
            )
            body_like = candidate.body_like or reidentified
            if background_probability >= BACKGROUND_REJECT_SCORE:
                kind = ObservationKind.CONTAMINATED_ACTIVITY
                body_like = False
                reidentified = False

            updated = replace(
                candidate,
                kind=kind,
                body_like=body_like,
                identity_score=identity,
                appearance_score=appearance,
                position_score=(
                    0.45
                    if predicted is None
                    else _clamp01(
                        math.exp(
                            -math.hypot(foot[0] - predicted[0], foot[1] - predicted[1])
                            / 96.0
                        )
                    )
                ),
                shape_similarity=shape,
                background_probability=background_probability,
                reidentified=reidentified,
            )
            enriched.append(updated)
            descriptor_rows.append((updated, descriptor, foot))

        for candidate, descriptor, foot in descriptor_rows:
            if (
                not candidate.is_target_body
                and candidate.confidence < 0.50
                and candidate.motion_score < 0.56
                and candidate.identity_score < 0.35
            ):
                self._learn_background(descriptor, foot, timestamp=timestamp)

        return tuple(enriched)

    def best_current_candidate(
        self,
        frame: CombatFrame,
        *,
        confirmed_cell: GridCell | None,
    ) -> CandidateObservation | None:
        valid = [candidate for candidate in frame.candidates if candidate.is_target_body]
        if confirmed_cell is not None:
            valid = [
                candidate
                for candidate in valid
                if confirmed_cell.chebyshev_distance(candidate.anchor_cell) <= 2
            ]
        valid.sort(
            key=lambda candidate: (
                candidate.background_probability,
                -candidate.identity_score,
                (
                    confirmed_cell.chebyshev_distance(candidate.anchor_cell)
                    if confirmed_cell is not None
                    else frame.player_cell.chebyshev_distance(candidate.anchor_cell)
                ),
                -candidate.appearance_score,
                -candidate.confidence,
            )
        )
        return valid[0] if valid else None

    @staticmethod
    def face_for_candidate(
        frame: CombatFrame,
        candidate: CandidateObservation,
        *,
        previous: str | None = None,
        deadzone_px: float = 8.0,
    ) -> str | None:
        if candidate.anchor_cell != frame.player_cell:
            return cardinal_face(frame.player_cell, candidate.anchor_cell, previous)
        offset = candidate.relative_offset_px
        if offset is None:
            return None
        dx, dy = float(offset[0]), float(offset[1])
        if max(abs(dx), abs(dy)) < float(deadzone_px):
            return None
        if abs(dx) >= abs(dy):
            return "RIGHT" if dx > 0 else "LEFT"
        return "DOWN" if dy > 0 else "UP"

    def observe_selected(
        self,
        *,
        frame_bgr: np.ndarray,
        state: object,
        candidate: CandidateObservation | None,
        timestamp: float,
        face: str | None,
        grid_distance: int | None,
    ) -> None:
        if candidate is None or candidate.bbox is None or candidate.foot_point is None:
            return

        foot = (float(candidate.foot_point[0]), float(candidate.foot_point[1]))
        if self.last_foot is not None and self.last_seen_at is not None:
            dt = max(1e-3, float(timestamp) - float(self.last_seen_at))
            raw_vx = (foot[0] - self.last_foot[0]) / dt
            raw_vy = (foot[1] - self.last_foot[1]) / dt
            self.velocity_px_s = (
                self.velocity_px_s[0] * 0.65 + raw_vx * 0.35,
                self.velocity_px_s[1] * 0.65 + raw_vy * 0.35,
            )
        self.previous_foot = self.last_foot
        self.last_foot = foot
        self.last_seen_at = float(timestamp)
        self._last_selected_track_id = int(candidate.track_id)

        if (
            not candidate.is_clean_body
            or candidate.confidence < 0.55
            or candidate.background_probability >= 0.55
            or timestamp - self._last_exemplar_at < self.exemplar_interval_seconds
        ):
            self._write_manifest()
            return

        arena_rect = tuple(int(value) for value in getattr(state, "arena_rect"))
        crop = _crop_for_bbox(frame_bgr, arena_rect, candidate.bbox)
        if crop is None or crop.size == 0:
            return
        descriptor = describe_crop(crop)
        novelty = (
            1.0
            if not self.exemplars
            else 1.0
            - max(
                appearance_similarity(descriptor, exemplar.descriptor)
                for exemplar in self.exemplars
            )
        )
        if self.exemplars and novelty < 0.055 and len(self.exemplars) >= 4:
            self._write_manifest()
            return

        filename = None
        if self.root is not None:
            index = len(self.exemplars) + 1
            filename = f"exemplar_{index:03d}.png"
            cv2.imwrite(str(self.root / filename), crop)
            np.savez_compressed(
                self.root / f"descriptor_{index:03d}.npz",
                hsv_hist=descriptor.hsv_hist,
                gray_signature=descriptor.gray_signature,
                edge_signature=descriptor.edge_signature,
                width=np.array([descriptor.width], dtype=np.int32),
                height=np.array([descriptor.height], dtype=np.int32),
            )

        self.exemplars.append(
            TargetExemplar(
                descriptor=descriptor,
                timestamp=float(timestamp),
                confidence=float(candidate.confidence),
                filename=filename,
                face=face,
                grid_distance=grid_distance,
            )
        )
        if len(self.exemplars) > self.max_exemplars:
            self.exemplars.pop(0)
        self._last_exemplar_at = float(timestamp)
        self._write_manifest()

    def _manifest_payload(self) -> dict:
        return {
            "version": 1,
            "logical_target_id": self.logical_target_id,
            "last_selected_track_id": self._last_selected_track_id,
            "last_seen_at": self.last_seen_at,
            "last_foot": list(self.last_foot) if self.last_foot is not None else None,
            "velocity_px_s": [
                round(float(self.velocity_px_s[0]), 3),
                round(float(self.velocity_px_s[1]), 3),
            ],
            "background_cells": len(self._background),
            "scoring": {
                "appearance": 0.35,
                "predicted_position": 0.25,
                "shape": 0.15,
                "independent_motion": 0.15,
                "foreground": 0.10,
                "reid_accept": self.reid_accept_score,
                "min_appearance": self.min_appearance_score,
            },
            "exemplars": [
                {
                    "filename": exemplar.filename,
                    "timestamp": round(exemplar.timestamp, 4),
                    "confidence": round(exemplar.confidence, 4),
                    "face": exemplar.face,
                    "grid_distance": exemplar.grid_distance,
                    "width": exemplar.descriptor.width,
                    "height": exemplar.descriptor.height,
                }
                for exemplar in self.exemplars
            ],
        }

    def _write_manifest(self) -> None:
        if self.root is None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / "target_session.json.tmp"
        destination = self.root / "target_session.json"
        temporary.write_text(
            json.dumps(self._manifest_payload(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)

    def close(self) -> None:
        self._write_manifest()


__all__ = [
    "TargetCapsuleMemory",
    "TargetExemplar",
    "VisualDescriptor",
    "appearance_similarity",
    "describe_crop",
    "shape_similarity",
]
