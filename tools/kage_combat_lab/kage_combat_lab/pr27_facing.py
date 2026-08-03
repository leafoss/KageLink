from __future__ import annotations

from collections import deque
import math
from typing import Mapping, Sequence

import cv2
import numpy as np

from .pr27_fragments import DescriptorFactory
from .pr27_model import PR27Config, TrackState, TrackedSprite


_DIRECTIONS = ("LEFT", "RIGHT", "UP", "DOWN")


def direction_from_delta(dx: float, dy: float, threshold: float) -> str | None:
    if max(abs(dx), abs(dy)) < threshold:
        return None
    if abs(dx) >= abs(dy):
        return "RIGHT" if dx > 0 else "LEFT"
    return "DOWN" if dy > 0 else "UP"


def opposite(direction: str | None) -> str | None:
    return {
        "LEFT": "RIGHT",
        "RIGHT": "LEFT",
        "UP": "DOWN",
        "DOWN": "UP",
    }.get(direction)


def _normalized_body_image(arena: np.ndarray, track: TrackedSprite | None) -> np.ndarray | None:
    if track is None or track.body_bbox is None:
        return None
    x, y, width, height = track.body_bbox
    left, top = max(0, x), max(0, y)
    right = min(arena.shape[1], x + width)
    bottom = min(arena.shape[0], y + height)
    if right <= left or bottom <= top:
        return None
    crop = arena[top:bottom, left:right]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (24, 48), interpolation=cv2.INTER_AREA)
    edges = cv2.Canny(gray, 35, 110).astype(np.float32) / 255.0
    gray = gray.astype(np.float32) / 255.0
    result = 0.60 * gray + 0.40 * edges
    result -= float(np.mean(result))
    norm = float(np.linalg.norm(result))
    if norm > 1e-9:
        result /= norm
    return result


class FacingObserver:
    """Separates commanded direction from visually observed facing."""

    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.commanded: str | None = None
        self.observed: str | None = None
        self.confirmed = False
        self.confirm_frames = 0
        self.last_anchor: tuple[float, float] | None = None
        self.motion_history: deque[str | None] = deque(maxlen=max(3, self.config.facing_confirm_frames))
        self.templates: dict[str, np.ndarray] = {}
        self.template_counts: dict[str, int] = {}
        self.template_scores: dict[str, float] = {}
        self.last_invalidation_reason: str | None = "startup"

    def invalidate(self, reason: str) -> None:
        self.observed = None
        self.confirmed = False
        self.confirm_frames = 0
        self.motion_history.clear()
        self.last_invalidation_reason = str(reason)

    def note_physical_actions(self, actions: Sequence[str]) -> None:
        for action in actions:
            upper = str(action).upper()
            for direction in _DIRECTIONS:
                if f"_{direction}" in upper and (
                    upper.startswith("TURN_")
                    or upper.startswith("CHASE_")
                    or upper.startswith("SEPARATE_")
                    or f"TURN_{direction}" in upper
                    or f"CHASE_{direction}" in upper
                    or f"SEPARATE_{direction}" in upper
                ):
                    self.commanded = direction
                    return

    def _update_template(self, direction: str, image: np.ndarray) -> None:
        previous = self.templates.get(direction)
        count = self.template_counts.get(direction, 0)
        if previous is None:
            self.templates[direction] = image.copy()
            self.template_counts[direction] = 1
            return
        alpha = 1.0 / min(12.0, count + 1.0)
        blended = (1.0 - alpha) * previous + alpha * image
        norm = float(np.linalg.norm(blended))
        if norm > 1e-9:
            blended /= norm
        self.templates[direction] = blended.astype(np.float32)
        self.template_counts[direction] = count + 1

    def observe(
        self,
        arena: np.ndarray,
        track: TrackedSprite | None,
        *,
        hit_event: bool = False,
    ) -> tuple[str | None, bool, Mapping[str, float]]:
        if hit_event:
            self.invalidate("hit_event")
        if track is None or track.body_anchor is None or track.track_state is TrackState.LOST:
            self.motion_history.append(None)
            self.confirmed = False
            return self.observed, False, dict(self.template_scores)
        image = _normalized_body_image(arena, track)
        motion_direction = None
        if self.last_anchor is not None:
            motion_direction = direction_from_delta(
                track.body_anchor[0] - self.last_anchor[0],
                track.body_anchor[1] - self.last_anchor[1],
                self.config.facing_motion_min_px,
            )
        self.last_anchor = track.body_anchor
        self.motion_history.append(motion_direction)
        stable_motion = None
        non_null = [value for value in self.motion_history if value is not None]
        if len(non_null) >= self.config.facing_confirm_frames and len(set(non_null[-self.config.facing_confirm_frames:])) == 1:
            stable_motion = non_null[-1]
        if image is not None and stable_motion is not None:
            # The label is grounded by observed sprite motion; the command is only a prior.
            if self.commanded is None or self.commanded == stable_motion:
                self._update_template(stable_motion, image)
        scores: dict[str, float] = {}
        if image is not None:
            for direction, template in self.templates.items():
                scores[direction] = max(0.0, min(1.0, (float(np.dot(image.flatten(), template.flatten())) + 1.0) / 2.0))
        self.template_scores = scores
        visual = None
        if scores:
            ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            best_direction, best_score = ordered[0]
            second_score = ordered[1][1] if len(ordered) > 1 else 0.0
            if best_score >= self.config.facing_template_min_score and best_score - second_score >= self.config.facing_template_margin:
                visual = best_direction
        if visual is None:
            visual = stable_motion
        if visual is None:
            self.confirm_frames = 0
            self.confirmed = False
            return self.observed, False, dict(scores)
        if self.observed == visual:
            self.confirm_frames += 1
        else:
            self.observed = visual
            self.confirm_frames = 1
        self.confirmed = self.confirm_frames >= self.config.facing_confirm_frames
        if self.confirmed:
            self.last_invalidation_reason = None
        return self.observed, self.confirmed, dict(scores)


class HitDetector:
    """Requires combined motion and appearance evidence before declaring a hit."""

    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.previous_anchor: tuple[float, float] | None = None
        self.previous_descriptor = None
        self.last_displacement = 0.0
        self.last_similarity = 1.0
        self.last_reason = "-"

    def observe(self, track: TrackedSprite | None, *, commanded_direction: str | None) -> bool:
        if track is None or track.body_anchor is None:
            return False
        displacement = 0.0
        motion_direction = None
        if self.previous_anchor is not None:
            dx = track.body_anchor[0] - self.previous_anchor[0]
            dy = track.body_anchor[1] - self.previous_anchor[1]
            displacement = math.hypot(dx, dy)
            motion_direction = direction_from_delta(dx, dy, 1.0)
        similarity = 1.0
        if self.previous_descriptor is not None:
            similarity = DescriptorFactory.similarity(self.previous_descriptor, track.appearance_signature)
        unexpected_motion = (
            displacement >= self.config.hit_displacement_px
            and commanded_direction is not None
            and motion_direction is not None
            and motion_direction != commanded_direction
        )
        appearance_shock = similarity < self.config.hit_appearance_similarity
        very_large = displacement >= self.config.hit_displacement_px * 2.0
        hit = (unexpected_motion and appearance_shock) or (very_large and appearance_shock)
        self.last_displacement = displacement
        self.last_similarity = similarity
        self.last_reason = (
            f"displacement={displacement:.1f}px motion={motion_direction} commanded={commanded_direction} "
            f"appearance={similarity:.3f}"
        )
        self.previous_anchor = track.body_anchor
        self.previous_descriptor = track.appearance_signature
        return hit
