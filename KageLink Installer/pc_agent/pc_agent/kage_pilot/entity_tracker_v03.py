from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Iterable

import cv2
import numpy as np

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


def _bbox_overlaps_player_box(
    bbox: tuple[int, int, int, int],
    player_center: tuple[float, float],
    config: ObserverConfig,
) -> bool:
    x, y, w, h = bbox
    candidate = Candidate(
        bbox=bbox,
        center=(x + w / 2.0, y + h / 2.0),
        contour_area=float(w * h),
        motion_energy=0.0,
        edge_density=0.0,
        shape_score=0.0,
    )
    return _candidate_overlaps_player_box(candidate, player_center, config)


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


def _relative_side(
    point: tuple[float, float],
    player_center: tuple[float, float],
    fallback: str = "-",
) -> str:
    dx = point[0] - player_center[0]
    dy = point[1] - player_center[1]
    if abs(dx) < 2.0 and abs(dy) < 2.0:
        return fallback
    if abs(dx) >= abs(dy):
        return "RIGHT" if dx >= 0 else "LEFT"
    return "DOWN" if dy >= 0 else "UP"


def _appearance_signature(gray: np.ndarray | None, bbox: tuple[int, int, int, int]) -> tuple[float, ...]:
    """Small normalized descriptor used for similarity and reacquisition.

    It intentionally combines intensity distribution with coarse spatial structure.
    This is not a learned model; it is a lightweight memory fingerprint that makes
    repeated animated background patches easier to recognize and helps an existing
    entity recover its identity after a short visual loss.
    """

    if gray is None or gray.size == 0:
        return ()
    x, y, w, h = bbox
    height, width = gray.shape[:2]
    x0 = max(0, min(width - 1, int(x)))
    y0 = max(0, min(height - 1, int(y)))
    x1 = max(x0 + 1, min(width, int(x + w)))
    y1 = max(y0 + 1, min(height, int(y + h)))
    patch = gray[y0:y1, x0:x1]
    if patch.size < 9:
        return ()

    histogram = cv2.calcHist([patch], [0], None, [8], [0, 256]).reshape(-1).astype(np.float32)
    hist_sum = float(histogram.sum())
    if hist_sum > 0:
        histogram /= hist_sum

    edges = cv2.Canny(patch, 45, 130)
    ph, pw = patch.shape[:2]
    ymid = max(1, ph // 2)
    xmid = max(1, pw // 2)
    quadrants = [
        (0, 0, xmid, ymid),
        (xmid, 0, pw, ymid),
        (0, ymid, xmid, ph),
        (xmid, ymid, pw, ph),
    ]
    spatial: list[float] = []
    for qx0, qy0, qx1, qy1 in quadrants:
        region = patch[qy0:qy1, qx0:qx1]
        edge_region = edges[qy0:qy1, qx0:qx1]
        if region.size == 0:
            spatial.extend((0.0, 0.0))
        else:
            spatial.append(float(np.mean(region)) / 255.0)
            spatial.append(float(np.count_nonzero(edge_region)) / float(region.size))

    vector = np.asarray(list(histogram) + spatial, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if norm > 1e-9:
        vector /= norm
    return tuple(float(value) for value in vector)


def appearance_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    av = np.asarray(a, dtype=np.float32)
    bv = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
    if denom <= 1e-9:
        return 0.0
    return max(0.0, min(1.0, float(np.dot(av, bv) / denom)))


def _blend_signature(
    previous: tuple[float, ...],
    current: tuple[float, ...],
    alpha: float = 0.22,
) -> tuple[float, ...]:
    if not current:
        return previous
    if not previous or len(previous) != len(current):
        return current
    pv = np.asarray(previous, dtype=np.float32)
    cv = np.asarray(current, dtype=np.float32)
    vector = (1.0 - alpha) * pv + alpha * cv
    norm = float(np.linalg.norm(vector))
    if norm > 1e-9:
        vector /= norm
    return tuple(float(value) for value in vector)


@dataclass(slots=True)
class TrackContext:
    appearance: tuple[float, ...] = ()
    appearance_similarity: float = 0.0
    state: str = "VISIBLE"
    relative_side: str = "-"
    last_visible_side: str = "-"
    occluded_since: float | None = None


@dataclass(slots=True)
class _DynamicCell:
    first_seen: float
    last_seen: float
    dense_hits: float = 0.0
    appearance: tuple[float, ...] = ()


@dataclass(slots=True)
class _DormantTrack:
    track: EntityTrack
    context: TrackContext
    expires_at: float


class DynamicBackgroundMemory:
    """Learn repetitive dense motion regions such as animated water.

    A cell only learns when several candidates are moving close together in the
    same area. This strongly favors animated scenery and effects over a single
    coherent character. A matured cell suppresses only visually similar future
    candidates, so a different-looking entity can still cross that region.
    """

    def __init__(self, config: ObserverConfig) -> None:
        self.config = config
        self.cells: dict[tuple[int, int], _DynamicCell] = {}
        self.suppressed_last_frame = 0

    def reset(self) -> None:
        self.cells.clear()
        self.suppressed_last_frame = 0

    @property
    def mature_cells(self) -> int:
        return sum(1 for cell in self.cells.values() if self._mature(cell))

    def _cell_size(self) -> float:
        return max(12.0, float(getattr(self.config, "background_cell_size", 32.0)))

    def _key(self, center: tuple[float, float]) -> tuple[int, int]:
        size = self._cell_size()
        return int(center[0] // size), int(center[1] // size)

    def _mature(self, cell: _DynamicCell) -> bool:
        min_hits = float(getattr(self.config, "background_min_dense_hits", 8.0))
        min_age = float(getattr(self.config, "background_min_age", 0.8))
        return cell.dense_hits >= min_hits and cell.last_seen - cell.first_seen >= min_age

    def _nearby_cells(self, key: tuple[int, int]):
        kx, ky = key
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cell = self.cells.get((kx + dx, ky + dy))
                if cell is not None:
                    yield cell

    def observe_and_filter(
        self,
        candidates: list[Candidate],
        signatures: list[tuple[float, ...]],
        *,
        player_center: tuple[float, float],
        now: float,
    ) -> tuple[list[Candidate], list[tuple[float, ...]]]:
        if not bool(getattr(self.config, "dynamic_background_enabled", True)):
            self.suppressed_last_frame = 0
            return candidates, signatures

        neighbor_radius = float(getattr(self.config, "background_neighbor_radius", 58.0))
        min_neighbors = int(getattr(self.config, "background_min_neighbors", 3))
        player_guard = float(getattr(self.config, "background_player_guard", 78.0))
        similarity_threshold = float(getattr(self.config, "background_similarity", 0.88))

        neighbor_counts: list[int] = []
        for index, candidate in enumerate(candidates):
            count = 0
            for other_index, other in enumerate(candidates):
                if index == other_index:
                    continue
                if _distance(candidate.center, other.center) <= neighbor_radius:
                    count += 1
            neighbor_counts.append(count)

        # Learn only from dense, repetitive groups away from the player.
        for candidate, signature, neighbors in zip(candidates, signatures, neighbor_counts):
            if neighbors < min_neighbors:
                continue
            if _distance(candidate.center, player_center) < player_guard:
                continue
            key = self._key(candidate.center)
            cell = self.cells.get(key)
            if cell is None:
                self.cells[key] = _DynamicCell(
                    first_seen=now,
                    last_seen=now,
                    dense_hits=1.0,
                    appearance=signature,
                )
            else:
                elapsed = max(0.0, now - cell.last_seen)
                cell.dense_hits *= math.exp(-elapsed / 4.0)
                cell.dense_hits += 1.0
                cell.last_seen = now
                cell.appearance = _blend_signature(cell.appearance, signature, alpha=0.12)

        # Prune stale environmental memories so changing maps can recover naturally.
        stale_after = float(getattr(self.config, "background_memory_ttl", 12.0))
        for key in list(self.cells):
            if now - self.cells[key].last_seen > stale_after:
                del self.cells[key]

        filtered_candidates: list[Candidate] = []
        filtered_signatures: list[tuple[float, ...]] = []
        suppressed = 0
        for candidate, signature in zip(candidates, signatures):
            if _distance(candidate.center, player_center) < player_guard:
                filtered_candidates.append(candidate)
                filtered_signatures.append(signature)
                continue

            key = self._key(candidate.center)
            best_similarity = 0.0
            mature = False
            for cell in self._nearby_cells(key):
                if not self._mature(cell):
                    continue
                mature = True
                best_similarity = max(best_similarity, appearance_similarity(cell.appearance, signature))

            if mature and best_similarity >= similarity_threshold:
                suppressed += 1
                continue
            filtered_candidates.append(candidate)
            filtered_signatures.append(signature)

        self.suppressed_last_frame = suppressed
        return filtered_candidates, filtered_signatures


class MeleeAwareEntityTracker(EntityTracker):
    """Persistent context-aware tracker tuned for real Shinobi Story combat.

    In addition to camera compensation and velocity prediction, this tracker keeps
    lightweight appearance memory, relative-side memory, occlusion/contact state,
    dynamic-background memory, and a dormant identity pool for reacquisition.
    """

    def __init__(self, config: ObserverConfig) -> None:
        super().__init__(config)
        self._frame_gray: np.ndarray | None = None
        self._contexts: dict[int, TrackContext] = {}
        self._dormant: dict[int, _DormantTrack] = {}
        self.background = DynamicBackgroundMemory(config)

    def reset(self) -> None:
        super().reset()
        self._contexts.clear()
        self._dormant.clear()
        self.background.reset()
        self._frame_gray = None

    def prepare_frame(self, gray: np.ndarray) -> None:
        self._frame_gray = gray

    @property
    def dormant_count(self) -> int:
        return len(self._dormant)

    def context_for(self, track_id: int) -> TrackContext:
        return self._contexts.get(track_id, TrackContext())

    def _signature(self, candidate: Candidate) -> tuple[float, ...]:
        return _appearance_signature(self._frame_gray, candidate.bbox)

    def _context_match_cost(
        self,
        track: EntityTrack,
        context: TrackContext,
        candidate: Candidate,
        signature: tuple[float, ...],
        predicted_center: tuple[float, float],
    ) -> tuple[float, float, float]:
        cost, center_distance = _match_cost(track, candidate, predicted_center)
        similarity = appearance_similarity(context.appearance, signature)
        if context.appearance and signature:
            cost += (1.0 - similarity) * 38.0
            if similarity >= 0.92:
                cost -= 8.0
        return cost, center_distance, similarity

    def _constrain_to_player_boundary(
        self,
        candidate: Candidate,
        *,
        player_center: tuple[float, float],
        side: str,
    ) -> Candidate:
        px, py, pw, ph = _player_box(player_center, self.config)
        x, y, w, h = candidate.bbox
        side = side if side in {"LEFT", "RIGHT", "UP", "DOWN"} else _relative_side(candidate.center, player_center)
        if side == "LEFT":
            x = round(px - w)
        elif side == "RIGHT":
            x = round(px + pw)
        elif side == "UP":
            y = round(py - h)
        else:
            y = round(py + ph)
        return replace(candidate, bbox=(int(x), int(y), int(w), int(h)), center=(x + w / 2.0, y + h / 2.0))

    def _preprocess_player_contact(
        self,
        candidates: list[Candidate],
        signatures: list[tuple[float, ...]],
        *,
        predicted: dict[int, tuple[float, float]],
        player_center: tuple[float, float],
    ) -> tuple[list[Candidate], list[tuple[float, ...]], dict[int, int]]:
        processed: list[Candidate] = []
        processed_signatures: list[tuple[float, ...]] = []
        forced_track_by_index: dict[int, int] = {}

        for candidate, signature in zip(candidates, signatures):
            if not _candidate_overlaps_player_box(candidate, player_center, self.config):
                processed.append(candidate)
                processed_signatures.append(signature)
                continue

            # A candidate inside the player box may be a merged PLAYER+enemy contour.
            # Reuse it only when a known track plausibly owns that contact; otherwise
            # treat it as player motion and do not spawn a new entity.
            best: tuple[float, int] | None = None
            for track_id, point in predicted.items():
                distance = _distance(point, candidate.center)
                gate = float(self.config.track_match_distance) + 30.0
                if distance <= gate and (best is None or distance < best[0]):
                    best = (distance, track_id)
            if best is None:
                continue

            track_id = best[1]
            context = self._contexts.get(track_id, TrackContext())
            side = context.last_visible_side or context.relative_side
            if side == "-":
                side = _relative_side(self._tracks[track_id].center, player_center, "RIGHT")
            constrained = self._constrain_to_player_boundary(candidate, player_center=player_center, side=side)
            index = len(processed)
            processed.append(constrained)
            # Do not contaminate appearance memory with a merged player+enemy patch.
            processed_signatures.append(context.appearance)
            forced_track_by_index[index] = track_id

        return processed, processed_signatures, forced_track_by_index

    def _restore_dormant(
        self,
        candidate: Candidate,
        signature: tuple[float, ...],
        *,
        flow: FlowEstimate,
        player_center: tuple[float, float],
        now: float,
    ) -> EntityTrack | None:
        min_similarity = float(getattr(self.config, "reacquire_similarity", 0.82))
        max_distance = float(getattr(self.config, "reacquire_distance", 180.0))
        choices: list[tuple[float, float, int]] = []
        for track_id, dormant in self._dormant.items():
            similarity = appearance_similarity(dormant.context.appearance, signature)
            if dormant.context.appearance and signature and similarity < min_similarity:
                continue
            predicted = _predicted_center(dormant.track, flow, now)
            distance = _distance(predicted, candidate.center)
            if distance <= max_distance:
                choices.append((distance - similarity * 45.0, similarity, track_id))
        if not choices:
            return None

        choices.sort(key=lambda item: item[0])
        _, similarity, track_id = choices[0]
        dormant = self._dormant.pop(track_id)
        track = dormant.track
        context = dormant.context
        predicted = _predicted_center(track, flow, now)
        track.observe(candidate, now=now, player_center=player_center, predicted_center=predicted)
        context.appearance_similarity = similarity
        context.appearance = _blend_signature(context.appearance, signature)
        context.state = "VISIBLE"
        context.occluded_since = None
        context.relative_side = _relative_side(track.center, player_center, context.last_visible_side)
        context.last_visible_side = context.relative_side
        self._tracks[track_id] = track
        self._contexts[track_id] = context
        return track

    def update(
        self,
        candidates: Iterable[Candidate],
        *,
        flow: FlowEstimate,
        player_center: tuple[float, float],
        now: float,
    ) -> tuple[EntityTrack, ...]:
        raw_candidates = list(candidates)
        raw_signatures = [self._signature(candidate) for candidate in raw_candidates]
        candidates, signatures = self.background.observe_and_filter(
            raw_candidates,
            raw_signatures,
            player_center=player_center,
            now=now,
        )

        # Expire old dormant memories separately from active tracking TTL.
        for track_id in list(self._dormant):
            if now > self._dormant[track_id].expires_at:
                del self._dormant[track_id]

        predicted = {track_id: _predicted_center(track, flow, now) for track_id, track in self._tracks.items()}
        candidates, signatures, forced_track_by_index = self._preprocess_player_contact(
            candidates,
            signatures,
            predicted=predicted,
            player_center=player_center,
        )

        unmatched_tracks = set(self._tracks)
        unmatched_candidates = set(range(len(candidates)))
        matches: list[tuple[int, int, float, bool]] = []

        pairs: list[tuple[float, int, int, float, bool]] = []
        base_gate = float(self.config.track_match_distance)
        for track_id, point in predicted.items():
            track = self._tracks[track_id]
            context = self._contexts.get(track_id, TrackContext())
            adaptive_gate = base_gate + min(35.0, track.residual_speed * 0.20)
            for candidate_index, (candidate, signature) in enumerate(zip(candidates, signatures)):
                forced_track = forced_track_by_index.get(candidate_index)
                if forced_track is not None and forced_track != track_id:
                    continue
                cost, center_distance, similarity = self._context_match_cost(
                    track,
                    context,
                    candidate,
                    signature,
                    point,
                )
                if center_distance <= adaptive_gate and cost <= adaptive_gate + 40.0:
                    if forced_track == track_id:
                        cost -= 22.0
                    pairs.append((cost, track_id, candidate_index, similarity, forced_track == track_id))
        pairs.sort(key=lambda item: item[0])

        for _, track_id, candidate_index, similarity, is_occluded in pairs:
            if track_id not in unmatched_tracks or candidate_index not in unmatched_candidates:
                continue
            unmatched_tracks.remove(track_id)
            unmatched_candidates.remove(candidate_index)
            matches.append((track_id, candidate_index, similarity, is_occluded))

        for track_id, candidate_index, similarity, is_occluded in matches:
            track = self._tracks[track_id]
            context = self._contexts.setdefault(track_id, TrackContext())
            track.observe(
                candidates[candidate_index],
                now=now,
                player_center=player_center,
                predicted_center=predicted[track_id],
            )
            context.appearance_similarity = similarity
            if is_occluded:
                context.state = "OCCLUDED"
                if context.occluded_since is None:
                    context.occluded_since = now
                # Keep the last clean side and clean appearance during contact.
                context.relative_side = context.last_visible_side
            else:
                context.state = "VISIBLE"
                context.occluded_since = None
                side = _relative_side(track.center, player_center, context.last_visible_side)
                context.relative_side = side
                context.last_visible_side = side
                context.appearance = _blend_signature(context.appearance, signatures[candidate_index])

        dormant_ttl = float(getattr(self.config, "reacquire_ttl", 5.0))
        for track_id in list(unmatched_tracks):
            track = self._tracks[track_id]
            context = self._contexts.setdefault(track_id, TrackContext())
            track.shift_with_camera(flow)

            vx, vy = track.residual_velocity
            track.residual_velocity = (vx * 0.72, vy * 0.72)
            track.hostility_memory *= 0.97
            track.approaching_player = False
            track.approach_speed = 0.0
            track.enemy_score = score_enemy(track, player_center, now=now)

            if _bbox_overlaps_player_box(track.bbox, player_center, self.config) and context.last_visible_side != "-":
                context.state = "OCCLUDED"
                if context.occluded_since is None:
                    context.occluded_since = now
                proxy = Candidate(
                    bbox=track.bbox,
                    center=track.center,
                    contour_area=_bbox_area(track.bbox),
                    motion_energy=track.motion_energy,
                    edge_density=track.edge_density,
                    shape_score=track.shape_score,
                )
                constrained = self._constrain_to_player_boundary(
                    proxy,
                    player_center=player_center,
                    side=context.last_visible_side,
                )
                track.bbox = constrained.bbox
                track.center = constrained.center
                context.relative_side = context.last_visible_side
            else:
                context.state = "LOST"

            if now - track.last_seen > self.config.track_ttl_seconds:
                # Preserve established identities for visual reacquisition. Very
                # young one-frame noise is simply discarded.
                if track.observations >= 3 or context.appearance:
                    self._dormant[track_id] = _DormantTrack(
                        track=track,
                        context=context,
                        expires_at=now + dormant_ttl,
                    )
                del self._tracks[track_id]
                self._contexts.pop(track_id, None)

        for candidate_index in sorted(unmatched_candidates):
            candidate = candidates[candidate_index]
            signature = signatures[candidate_index]

            if _candidate_overlaps_player_box(candidate, player_center, self.config):
                continue

            restored = self._restore_dormant(
                candidate,
                signature,
                flow=flow,
                player_center=player_center,
                now=now,
            )
            if restored is not None:
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
            side = _relative_side(track.center, player_center)
            self._contexts[track.track_id] = TrackContext(
                appearance=signature,
                appearance_similarity=1.0 if signature else 0.0,
                state="VISIBLE",
                relative_side=side,
                last_visible_side=side,
            )
            self._next_id += 1

        return self.tracks
