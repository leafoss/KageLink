from __future__ import annotations

import math
from typing import Iterable

from .entity_observer import (
    Candidate,
    EntityTrack,
    EntityTracker,
    FlowEstimate,
    ObserverConfig,
    score_enemy,
)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _bbox_area(bbox: tuple[int, int, int, int]) -> float:
    return float(max(1, bbox[2] * bbox[3]))


def _bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return 0.0
    intersection = float((right - left) * (bottom - top))
    union = _bbox_area(a) + _bbox_area(b) - intersection
    return intersection / max(1.0, union)


def _player_box(
    player_center: tuple[float, float],
    config: ObserverConfig,
) -> tuple[float, float, float, float]:
    width = float(getattr(config, "player_box_width", config.player_exclusion_radius * 1.2))
    height = float(getattr(config, "player_box_height", config.player_exclusion_radius * 2.0))
    return (
        player_center[0] - width / 2.0,
        player_center[1] - height / 2.0,
        width,
        height,
    )


def _candidate_overlaps_player_box(
    candidate: Candidate,
    player_center: tuple[float, float],
    config: ObserverConfig,
) -> bool:
    px, py, pw, ph = _player_box(player_center, config)
    cx, cy = candidate.center
    if px <= cx <= px + pw and py <= cy <= py + ph:
        return True

    bx, by, bw, bh = candidate.bbox
    left = max(float(bx), px)
    top = max(float(by), py)
    right = min(float(bx + bw), px + pw)
    bottom = min(float(by + bh), py + ph)
    if right <= left or bottom <= top:
        return False
    overlap = (right - left) * (bottom - top)
    return overlap / max(1.0, float(bw * bh)) >= 0.18


def _predicted_center(track: EntityTrack, flow: FlowEstimate, now: float) -> tuple[float, float]:
    """Predict next center from camera flow plus recent entity velocity."""

    dt = max(0.0, min(0.45, now - track.last_seen))
    vx, vy = track.residual_velocity
    extra_x = vx * dt
    extra_y = vy * dt
    extra_length = math.hypot(extra_x, extra_y)
    if extra_length > 36.0:
        scale = 36.0 / extra_length
        extra_x *= scale
        extra_y *= scale
    return track.center[0] + flow.dx + extra_x, track.center[1] + flow.dy + extra_y


def _match_cost(
    track: EntityTrack,
    candidate: Candidate,
    predicted_center: tuple[float, float],
) -> tuple[float, float]:
    center_distance = _distance(predicted_center, candidate.center)
    area_ratio = _bbox_area(candidate.bbox) / max(1.0, _bbox_area(track.bbox))
    size_penalty = abs(math.log(max(1e-6, area_ratio))) * 16.0
    shape_penalty = abs(candidate.shape_score - track.shape_score) * 16.0
    overlap_bonus = _bbox_iou(track.bbox, candidate.bbox) * 12.0
    cost = center_distance + size_penalty + shape_penalty - overlap_bonus
    return cost, center_distance


class MeleeAwareEntityTracker(EntityTracker):
    """Persistent v0.3 tracker tuned for real Shinobi Story combat.

    Improvements over the base tracker:

    - the player's exclusion region is a tight vertical rectangle rather than a circle;
    - exclusion prevents only *new* tracks, so a known enemy may enter melee range;
    - matching predicts entity position from camera flow and recent residual velocity;
    - bbox size/shape consistency contributes to association, reducing ID swaps;
    - unmatched tracks retain decaying velocity until the larger TTL expires.
    """

    def __init__(self, config: ObserverConfig) -> None:
        super().__init__(config)

    def update(
        self,
        candidates: Iterable[Candidate],
        *,
        flow: FlowEstimate,
        player_center: tuple[float, float],
        now: float,
    ) -> tuple[EntityTrack, ...]:
        candidates = list(candidates)

        predicted = {
            track_id: _predicted_center(track, flow, now)
            for track_id, track in self._tracks.items()
        }
        unmatched_tracks = set(self._tracks)
        unmatched_candidates = set(range(len(candidates)))
        matches: list[tuple[int, int]] = []

        pairs: list[tuple[float, int, int]] = []
        base_gate = float(self.config.track_match_distance)
        for track_id, point in predicted.items():
            track = self._tracks[track_id]
            adaptive_gate = base_gate + min(35.0, track.residual_speed * 0.20)
            for candidate_index, candidate in enumerate(candidates):
                cost, center_distance = _match_cost(track, candidate, point)
                if center_distance <= adaptive_gate and cost <= adaptive_gate + 28.0:
                    pairs.append((cost, track_id, candidate_index))
        pairs.sort(key=lambda item: item[0])

        for _, track_id, candidate_index in pairs:
            if track_id not in unmatched_tracks or candidate_index not in unmatched_candidates:
                continue
            unmatched_tracks.remove(track_id)
            unmatched_candidates.remove(candidate_index)
            matches.append((track_id, candidate_index))

        for track_id, candidate_index in matches:
            track = self._tracks[track_id]
            track.observe(
                candidates[candidate_index],
                now=now,
                player_center=player_center,
                predicted_center=predicted[track_id],
            )

        for track_id in list(unmatched_tracks):
            track = self._tracks[track_id]
            track.shift_with_camera(flow)

            # Preserve some motion memory across short contour drop-outs. The base
            # implementation zeroed velocity immediately, which made reacquisition
            # much harder on the next frame.
            vx, vy = track.residual_velocity
            track.residual_velocity = (vx * 0.72, vy * 0.72)
            track.hostility_memory *= 0.97
            track.approaching_player = False
            track.approach_speed = 0.0
            track.enemy_score = score_enemy(track, player_center, now=now)

            if now - track.last_seen > self.config.track_ttl_seconds:
                del self._tracks[track_id]

        for candidate_index in sorted(unmatched_candidates):
            candidate = candidates[candidate_index]

            # The player box is a spawn guard only. A known entity entering this
            # box has already been matched above and therefore keeps its ID.
            if _candidate_overlaps_player_box(candidate, player_center, self.config):
                continue

            track = EntityTrack(
                track_id=self._next_id,
                bbox=candidate.bbox,
                center=candidate.center,
                created_at=now,
                last_seen=now,
                motion_energy=candidate.motion_energy,
                edge_density=candidate.edge_density,
                shape_score=candidate.shape_score,
            )
            track.enemy_score = score_enemy(track, player_center)
            self._tracks[track.track_id] = track
            self._next_id += 1

        return self.tracks
