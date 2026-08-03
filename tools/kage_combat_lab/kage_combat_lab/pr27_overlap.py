from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .pr27_identity import bbox_iou
from .pr27_model import PR27Config, SpriteObservation, SpriteRole, TrackedSprite


def bbox_contains_point(bbox: tuple[int, int, int, int] | None, point: tuple[float, float] | None) -> bool:
    if bbox is None or point is None:
        return False
    x, y, width, height = bbox
    return x <= point[0] < x + width and y <= point[1] < y + height


def bbox_area(bbox: tuple[int, int, int, int] | None) -> int:
    return 0 if bbox is None else max(0, bbox[2]) * max(0, bbox[3])


@dataclass(frozen=True, slots=True)
class MergedBodyEvidence:
    observation_ids: frozenset[int] = frozenset()
    bbox: tuple[int, int, int, int] | None = None
    self_enemy_iou: float = 0.0
    reason: str = "-"

    @property
    def detected(self) -> bool:
        return bool(self.observation_ids)


class MergedBodyDetector:
    """Rejects one visual mass that covers both predicted role authorities."""

    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()

    def detect(
        self,
        observations: Sequence[SpriteObservation],
        *,
        self_track: TrackedSprite | None,
        enemy_track: TrackedSprite | None,
    ) -> MergedBodyEvidence:
        if self_track is None or enemy_track is None:
            return MergedBodyEvidence()
        if self_track.body_bbox is None or enemy_track.body_bbox is None:
            return MergedBodyEvidence()
        self_anchor = self_track.predicted_anchor or self_track.body_anchor
        enemy_anchor = enemy_track.predicted_anchor or enemy_track.body_anchor
        role_iou = bbox_iou(self_track.body_bbox, enemy_track.body_bbox)
        ids: set[int] = set()
        selected_bbox: tuple[int, int, int, int] | None = None
        selected_reason = "-"
        self_area = max(1, bbox_area(self_track.body_bbox))
        enemy_area = max(1, bbox_area(enemy_track.body_bbox))
        for observation in observations:
            if observation.body_bbox is None or observation.body_anchor is None:
                continue
            covers_self = bbox_contains_point(observation.body_bbox, self_anchor) or bbox_iou(observation.body_bbox, self_track.body_bbox) >= self.config.merged_body_iou_threshold
            covers_enemy = bbox_contains_point(observation.body_bbox, enemy_anchor) or bbox_iou(observation.body_bbox, enemy_track.body_bbox) >= self.config.merged_body_iou_threshold
            if not (covers_self and covers_enemy):
                continue
            observation_area = bbox_area(observation.body_bbox)
            large_mass = observation_area >= self.config.merged_body_area_ratio * max(self_area, enemy_area)
            anchors_close = False
            if self_anchor is not None and enemy_anchor is not None:
                anchors_close = math.hypot(self_anchor[0] - enemy_anchor[0], self_anchor[1] - enemy_anchor[1]) <= 48.0
            if not (large_mass or anchors_close or role_iou >= self.config.merged_body_iou_threshold):
                continue
            observation.merged_body = True
            observation.reserved_role = SpriteRole.MERGED_BODY
            observation.role_conflict_reason = "MERGED_SELF_ENEMY_VISUAL_MASS"
            ids.add(observation.observation_id)
            selected_bbox = observation.body_bbox
            selected_reason = "covers predicted SELF and ENEMY authorities"
        return MergedBodyEvidence(frozenset(ids), selected_bbox, role_iou, selected_reason)


@dataclass(frozen=True, slots=True)
class RoleConflictEvidence:
    conflict: bool
    shared_observation: bool
    self_enemy_iou: float
    reason: str | None = None


def role_conflict(
    self_track: TrackedSprite | None,
    enemy_track: TrackedSprite | None,
) -> RoleConflictEvidence:
    if self_track is None or enemy_track is None:
        return RoleConflictEvidence(False, False, 0.0, None)
    shared = (
        self_track.observation_id is not None
        and self_track.observation_id == enemy_track.observation_id
    )
    overlap = bbox_iou(self_track.body_bbox, enemy_track.body_bbox)
    role_flip = self_track.effective_role is not SpriteRole.SELF or enemy_track.effective_role is SpriteRole.SELF
    conflict = shared or role_flip
    reason = None
    if shared:
        reason = "SHARED_OBSERVATION_BLOCKED"
    elif role_flip:
        reason = "ROLE_FLIP_BLOCKED"
    return RoleConflictEvidence(conflict, shared, overlap, reason)
