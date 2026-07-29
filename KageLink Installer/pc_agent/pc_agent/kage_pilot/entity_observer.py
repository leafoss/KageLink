from __future__ import annotations

import io
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

import cv2
import numpy as np


@dataclass(slots=True)
class ObserverConfig:
    """Configuration for the read-only v0.3 entity observer.

    Coordinates are normalized against the captured game frame. The defaults
    intentionally exclude a small outer border and the lowest UI-heavy strip.
    Player position is initially treated as a camera-relative anchor; the entity
    tracker can therefore learn enemy motion before a dedicated player visual
    model exists.
    """

    arena_left: float = 0.04
    arena_top: float = 0.04
    arena_right: float = 0.96
    arena_bottom: float = 0.86
    player_x: float = 0.50
    player_y: float = 0.55
    player_exclusion_radius: float = 26.0
    max_flow_corners: int = 350
    flow_quality: float = 0.01
    flow_min_distance: float = 7.0
    max_flow_per_frame: float = 70.0
    min_candidate_area: float = 45.0
    max_candidate_area: float = 5500.0
    min_candidate_width: int = 6
    min_candidate_height: int = 10
    max_candidate_width: int = 150
    max_candidate_height: int = 180
    track_match_distance: float = 90.0
    track_ttl_seconds: float = 1.25
    enemy_threshold: float = 55.0

    def normalized(self) -> "ObserverConfig":
        self.arena_left = max(0.0, min(0.95, float(self.arena_left)))
        self.arena_top = max(0.0, min(0.95, float(self.arena_top)))
        self.arena_right = max(self.arena_left + 0.01, min(1.0, float(self.arena_right)))
        self.arena_bottom = max(self.arena_top + 0.01, min(1.0, float(self.arena_bottom)))
        self.player_x = max(0.0, min(1.0, float(self.player_x)))
        self.player_y = max(0.0, min(1.0, float(self.player_y)))
        self.player_exclusion_radius = max(4.0, float(self.player_exclusion_radius))
        self.enemy_threshold = max(0.0, min(100.0, float(self.enemy_threshold)))
        return self


@dataclass(frozen=True, slots=True)
class FlowEstimate:
    dx: float = 0.0
    dy: float = 0.0
    points: int = 0
    residual_median: float = 0.0


@dataclass(frozen=True, slots=True)
class Candidate:
    bbox: tuple[int, int, int, int]
    center: tuple[float, float]
    contour_area: float
    motion_energy: float
    edge_density: float
    shape_score: float


@dataclass(slots=True)
class EntityTrack:
    track_id: int
    bbox: tuple[int, int, int, int]
    center: tuple[float, float]
    created_at: float
    last_seen: float
    observations: int = 1
    total_residual_displacement: float = 0.0
    residual_velocity: tuple[float, float] = (0.0, 0.0)
    screen_velocity: tuple[float, float] = (0.0, 0.0)
    approach_speed: float = 0.0
    approaching_player: bool = False
    motion_energy: float = 0.0
    edge_density: float = 0.0
    shape_score: float = 0.0
    hostility_memory: float = 0.0
    enemy_score: float = 0.0
    history: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=28))

    def __post_init__(self) -> None:
        if not self.history:
            self.history.append(self.center)

    @property
    def age(self) -> float:
        return max(0.0, self.last_seen - self.created_at)

    @property
    def residual_speed(self) -> float:
        vx, vy = self.residual_velocity
        return math.hypot(vx, vy)

    @property
    def movement_real(self) -> bool:
        return self.residual_speed >= 5.0

    def predicted_center(self, flow: FlowEstimate) -> tuple[float, float]:
        return self.center[0] + flow.dx, self.center[1] + flow.dy

    def shift_with_camera(self, flow: FlowEstimate) -> None:
        if not flow.dx and not flow.dy:
            return
        x, y, w, h = self.bbox
        self.bbox = (round(x + flow.dx), round(y + flow.dy), w, h)
        self.center = (self.center[0] + flow.dx, self.center[1] + flow.dy)

    def observe(
        self,
        candidate: Candidate,
        *,
        now: float,
        player_center: tuple[float, float],
        predicted_center: tuple[float, float],
    ) -> None:
        dt = max(1e-3, now - self.last_seen)
        previous_screen = self.center
        previous_distance = _point_distance(previous_screen, player_center)
        current_distance = _point_distance(candidate.center, player_center)

        residual_dx = candidate.center[0] - predicted_center[0]
        residual_dy = candidate.center[1] - predicted_center[1]
        screen_dx = candidate.center[0] - previous_screen[0]
        screen_dy = candidate.center[1] - previous_screen[1]

        self.residual_velocity = (residual_dx / dt, residual_dy / dt)
        self.screen_velocity = (screen_dx / dt, screen_dy / dt)
        self.total_residual_displacement += math.hypot(residual_dx, residual_dy)
        self.approach_speed = (previous_distance - current_distance) / dt
        self.approaching_player = self.approach_speed >= 4.0
        self.bbox = candidate.bbox
        self.center = candidate.center
        self.last_seen = now
        self.observations += 1
        self.motion_energy = candidate.motion_energy
        self.edge_density = candidate.edge_density
        self.shape_score = candidate.shape_score
        self.history.append(candidate.center)

        evidence = 0.0
        if self.approaching_player:
            evidence += min(0.22, self.approach_speed / 180.0)
        if self.movement_real:
            evidence += min(0.12, self.residual_speed / 300.0)
        self.hostility_memory = max(0.0, min(1.0, self.hostility_memory * 0.94 + evidence))
        self.enemy_score = score_enemy(self, player_center)

    def decay(self, *, now: float, player_center: tuple[float, float]) -> None:
        self.hostility_memory *= 0.97
        self.approaching_player = False
        self.approach_speed = 0.0
        self.residual_velocity = (0.0, 0.0)
        self.enemy_score = score_enemy(self, player_center, now=now)

    def to_dict(self, player_center: tuple[float, float], *, now: float | None = None) -> dict:
        observed_for = max(0.0, (now if now is not None else self.last_seen) - self.created_at)
        return {
            "id": self.track_id,
            "bbox": list(self.bbox),
            "center": [round(self.center[0], 2), round(self.center[1], 2)],
            "observed_seconds": round(observed_for, 3),
            "observations": self.observations,
            "distance_to_player": round(_point_distance(self.center, player_center), 2),
            "total_residual_displacement": round(self.total_residual_displacement, 2),
            "residual_velocity": [round(self.residual_velocity[0], 2), round(self.residual_velocity[1], 2)],
            "residual_speed": round(self.residual_speed, 2),
            "direction": direction_name(self.residual_velocity),
            "movement_real": self.movement_real,
            "approaching_player": self.approaching_player,
            "approach_speed": round(self.approach_speed, 2),
            "shape_score": round(self.shape_score, 3),
            "motion_energy": round(self.motion_energy, 3),
            "edge_density": round(self.edge_density, 3),
            "hostility_memory": round(self.hostility_memory, 3),
            "enemy_score": round(self.enemy_score, 1),
        }


@dataclass(frozen=True, slots=True)
class ObserverState:
    timestamp: float
    arena_rect: tuple[int, int, int, int]
    player_center: tuple[float, float]
    global_flow: FlowEstimate
    tracks: tuple[EntityTrack, ...]
    target_id: int | None
    motion_mask: np.ndarray | None = None

    @property
    def target(self) -> EntityTrack | None:
        if self.target_id is None:
            return None
        return next((track for track in self.tracks if track.track_id == self.target_id), None)


class EntityTracker:
    def __init__(self, config: ObserverConfig) -> None:
        self.config = config
        self._tracks: dict[int, EntityTrack] = {}
        self._next_id = 1

    @property
    def tracks(self) -> tuple[EntityTrack, ...]:
        return tuple(sorted(self._tracks.values(), key=lambda track: track.track_id))

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    def update(
        self,
        candidates: Iterable[Candidate],
        *,
        flow: FlowEstimate,
        player_center: tuple[float, float],
        now: float,
    ) -> tuple[EntityTrack, ...]:
        candidates = [
            candidate
            for candidate in candidates
            if _point_distance(candidate.center, player_center) > self.config.player_exclusion_radius
        ]

        predicted = {track_id: track.predicted_center(flow) for track_id, track in self._tracks.items()}
        unmatched_tracks = set(self._tracks)
        unmatched_candidates = set(range(len(candidates)))
        matches: list[tuple[int, int]] = []

        pairs: list[tuple[float, int, int]] = []
        for track_id, point in predicted.items():
            for candidate_index, candidate in enumerate(candidates):
                distance = _point_distance(point, candidate.center)
                if distance <= self.config.track_match_distance:
                    pairs.append((distance, track_id, candidate_index))
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
            track.decay(now=now, player_center=player_center)
            if now - track.last_seen > self.config.track_ttl_seconds:
                del self._tracks[track_id]

        for candidate_index in sorted(unmatched_candidates):
            candidate = candidates[candidate_index]
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


class EntityObserver:
    """OpenCV/Lucas-Kanade read-only perception layer for Kage Pilot v0.3."""

    def __init__(self, config: ObserverConfig | None = None) -> None:
        self.config = (config or ObserverConfig()).normalized()
        self.tracker = EntityTracker(self.config)
        self._previous_gray: np.ndarray | None = None
        self._clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8))

    def reset(self) -> None:
        self._previous_gray = None
        self.tracker.reset()

    def process(self, frame_bgr: np.ndarray, *, timestamp: float | None = None) -> ObserverState:
        now = time.monotonic() if timestamp is None else float(timestamp)
        arena_rect = arena_rect_for_frame(frame_bgr, self.config)
        x0, y0, x1, y1 = arena_rect
        arena = frame_bgr[y0:y1, x0:x1]
        gray = cv2.cvtColor(arena, cv2.COLOR_BGR2GRAY)
        contrast = self._clahe.apply(gray)
        contrast = cv2.GaussianBlur(contrast, (3, 3), 0)

        player_center = (
            max(0.0, min(float(arena.shape[1] - 1), self.config.player_x * arena.shape[1])),
            max(0.0, min(float(arena.shape[0] - 1), self.config.player_y * arena.shape[0])),
        )

        if self._previous_gray is None or self._previous_gray.shape != contrast.shape:
            self._previous_gray = contrast
            return ObserverState(
                timestamp=now,
                arena_rect=arena_rect,
                player_center=player_center,
                global_flow=FlowEstimate(),
                tracks=self.tracker.tracks,
                target_id=None,
                motion_mask=np.zeros_like(contrast),
            )

        flow = estimate_global_flow(self._previous_gray, contrast, self.config)
        candidates, motion_mask = detect_candidates(self._previous_gray, contrast, flow, self.config)
        tracks = self.tracker.update(candidates, flow=flow, player_center=player_center, now=now)
        target = max(tracks, key=lambda track: track.enemy_score, default=None)
        target_id = (
            target.track_id
            if target is not None and target.enemy_score >= self.config.enemy_threshold
            else None
        )
        self._previous_gray = contrast
        return ObserverState(
            timestamp=now,
            arena_rect=arena_rect,
            player_center=player_center,
            global_flow=flow,
            tracks=tracks,
            target_id=target_id,
            motion_mask=motion_mask,
        )


def decode_jpeg(jpeg: bytes) -> np.ndarray:
    encoded = np.frombuffer(jpeg, dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError("INVALID_JPEG_FRAME")
    return frame


def arena_rect_for_frame(frame: np.ndarray, config: ObserverConfig) -> tuple[int, int, int, int]:
    height, width = frame.shape[:2]
    x0 = max(0, min(width - 1, round(width * config.arena_left)))
    y0 = max(0, min(height - 1, round(height * config.arena_top)))
    x1 = max(x0 + 1, min(width, round(width * config.arena_right)))
    y1 = max(y0 + 1, min(height, round(height * config.arena_bottom)))
    return x0, y0, x1, y1


def estimate_global_flow(previous: np.ndarray, current: np.ndarray, config: ObserverConfig) -> FlowEstimate:
    corners = cv2.goodFeaturesToTrack(
        previous,
        maxCorners=config.max_flow_corners,
        qualityLevel=config.flow_quality,
        minDistance=config.flow_min_distance,
        blockSize=7,
    )
    if corners is None or len(corners) < 6:
        return FlowEstimate()

    next_points, status, errors = cv2.calcOpticalFlowPyrLK(
        previous,
        current,
        corners,
        None,
        winSize=(21, 21),
        maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    )
    if next_points is None or status is None:
        return FlowEstimate()

    status = status.reshape(-1).astype(bool)
    old = corners.reshape(-1, 2)[status]
    new = next_points.reshape(-1, 2)[status]
    if errors is not None:
        error_values = errors.reshape(-1)[status]
        valid_error = np.isfinite(error_values) & (error_values < 35.0)
        old = old[valid_error]
        new = new[valid_error]
    if len(old) < 6:
        return FlowEstimate(points=int(len(old)))

    displacement = new - old
    magnitudes = np.linalg.norm(displacement, axis=1)
    plausible = np.isfinite(magnitudes) & (magnitudes <= config.max_flow_per_frame)
    displacement = displacement[plausible]
    if len(displacement) < 6:
        return FlowEstimate(points=int(len(displacement)))

    median = np.median(displacement, axis=0)
    residuals = np.linalg.norm(displacement - median, axis=1)
    residual_median = float(np.median(residuals))
    mad = float(np.median(np.abs(residuals - residual_median)))
    tolerance = max(1.5, residual_median + 3.5 * max(mad, 0.25))
    inliers = displacement[residuals <= tolerance]
    if len(inliers) >= 4:
        median = np.median(inliers, axis=0)
    return FlowEstimate(
        dx=float(median[0]),
        dy=float(median[1]),
        points=int(len(inliers) if len(inliers) >= 4 else len(displacement)),
        residual_median=residual_median,
    )


def detect_candidates(
    previous: np.ndarray,
    current: np.ndarray,
    flow: FlowEstimate,
    config: ObserverConfig,
) -> tuple[list[Candidate], np.ndarray]:
    height, width = current.shape[:2]
    transform = np.float32([[1.0, 0.0, flow.dx], [0.0, 1.0, flow.dy]])
    aligned_previous = cv2.warpAffine(
        previous,
        transform,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )
    difference = cv2.absdiff(current, aligned_previous)

    percentile = float(np.percentile(difference, 88.0))
    threshold_value = int(max(10.0, min(38.0, percentile)))
    _, motion = cv2.threshold(difference, threshold_value, 255, cv2.THRESH_BINARY)
    motion = cv2.morphologyEx(motion, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    motion = cv2.morphologyEx(motion, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    motion = cv2.dilate(motion, np.ones((5, 5), np.uint8), iterations=1)

    edges = cv2.Canny(current, 45, 130)
    contours, _ = cv2.findContours(motion, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[Candidate] = []
    for contour in contours:
        contour_area = float(cv2.contourArea(contour))
        if contour_area < config.min_candidate_area or contour_area > config.max_candidate_area:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if not (config.min_candidate_width <= w <= config.max_candidate_width):
            continue
        if not (config.min_candidate_height <= h <= config.max_candidate_height):
            continue
        box_area = max(1, w * h)
        region_difference = difference[y:y + h, x:x + w]
        region_edges = edges[y:y + h, x:x + w]
        motion_energy = float(np.mean(region_difference) / 255.0)
        edge_density = float(np.count_nonzero(region_edges) / box_area)
        aspect = h / max(1.0, float(w))
        shape_score = _shape_score(aspect, contour_area, box_area, edge_density)
        candidates.append(
            Candidate(
                bbox=(int(x), int(y), int(w), int(h)),
                center=(x + w / 2.0, y + h / 2.0),
                contour_area=contour_area,
                motion_energy=motion_energy,
                edge_density=edge_density,
                shape_score=shape_score,
            )
        )

    candidates.sort(key=lambda candidate: (candidate.motion_energy, candidate.contour_area), reverse=True)
    return candidates, motion


def score_enemy(track: EntityTrack, player_center: tuple[float, float], *, now: float | None = None) -> float:
    reference_now = track.last_seen if now is None else float(now)
    observed_seconds = max(0.0, reference_now - track.created_at)
    distance = _point_distance(track.center, player_center)

    persistence = min(1.0, observed_seconds / 1.8) * 20.0
    real_motion = min(1.0, track.residual_speed / 45.0) * 15.0
    approach = min(1.0, max(0.0, track.approach_speed) / 45.0) * 25.0
    distance_score = max(0.0, 1.0 - distance / 280.0) * 10.0
    shape = max(0.0, min(1.0, track.shape_score)) * 10.0

    heading = 0.0
    vx, vy = track.residual_velocity
    speed = math.hypot(vx, vy)
    to_player = (player_center[0] - track.center[0], player_center[1] - track.center[1])
    to_player_length = math.hypot(*to_player)
    if speed >= 3.0 and to_player_length >= 1.0:
        cosine = (vx * to_player[0] + vy * to_player[1]) / (speed * to_player_length)
        heading = max(0.0, min(1.0, cosine)) * 10.0

    memory = max(0.0, min(1.0, track.hostility_memory)) * 10.0
    return max(0.0, min(100.0, persistence + real_motion + approach + distance_score + shape + heading + memory))


def direction_name(vector: tuple[float, float]) -> str:
    x, y = vector
    if math.hypot(x, y) < 1.0:
        return "-"
    horizontal = "E" if x > 2.0 else "W" if x < -2.0 else ""
    vertical = "S" if y > 2.0 else "N" if y < -2.0 else ""
    return vertical + horizontal or horizontal or vertical or "-"


def render_overlay(frame_bgr: np.ndarray, state: ObserverState, config: ObserverConfig) -> np.ndarray:
    frame = frame_bgr.copy()
    x0, y0, x1, y1 = state.arena_rect
    cv2.rectangle(frame, (x0, y0), (x1, y1), (120, 120, 120), 1)

    player_full = (round(x0 + state.player_center[0]), round(y0 + state.player_center[1]))
    cv2.circle(frame, player_full, round(config.player_exclusion_radius), (255, 255, 255), 1)
    cv2.drawMarker(frame, player_full, (255, 255, 255), cv2.MARKER_CROSS, 20, 2)
    cv2.putText(frame, "PLAYER #000", (player_full[0] + 12, player_full[1] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    for track in state.tracks:
        tx, ty, tw, th = track.bbox
        full_box = (x0 + tx, y0 + ty, tw, th)
        color = (0, 220, 255) if track.track_id == state.target_id else (0, 190, 0)
        thickness = 2 if track.track_id == state.target_id else 1
        cv2.rectangle(
            frame,
            (full_box[0], full_box[1]),
            (full_box[0] + full_box[2], full_box[1] + full_box[3]),
            color,
            thickness,
        )
        trail = [(round(x0 + point[0]), round(y0 + point[1])) for point in track.history]
        for first, second in zip(trail, trail[1:]):
            cv2.line(frame, first, second, color, 1)
        label = f"ENTITY #{track.track_id:03d}  {track.enemy_score:04.1f}%"
        if track.track_id == state.target_id:
            label += " TARGET"
        cv2.putText(
            frame,
            label,
            (full_box[0], max(18, full_box[1] - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    panel_width = 360
    panel = np.zeros((frame.shape[0], panel_width, 3), dtype=np.uint8)
    lines = [
        "KAGE PILOT v0.3 - ENTITY OBSERVER",
        "READ ONLY / SOMENTE OBSERVACAO",
        "",
        f"global flow: dx={state.global_flow.dx:+.1f} dy={state.global_flow.dy:+.1f}",
        f"LK points: {state.global_flow.points}",
        f"entities: {len(state.tracks)}",
        f"enemy threshold: {config.enemy_threshold:.0f}%",
        "",
    ]
    target = state.target
    if target is None:
        lines.extend(["TARGET: searching / procurando", "", "F10, Q or ESC = exit / sair"])
    else:
        info = target.to_dict(state.player_center, now=state.timestamp)
        lines.extend(
            [
                f"ENTITY #{target.track_id:03d}",
                f"position / posicao: {info['center'][0]:.0f},{info['center'][1]:.0f}",
                f"observed / observado: {info['observed_seconds']:.1f}s",
                f"displacement / desloc.: {info['total_residual_displacement']:.0f}px",
                f"direction / direcao: {info['direction']}",
                f"speed / velocidade: {info['residual_speed']:.1f}px/s",
                f"real motion / mov. real: {'YES / SIM' if info['movement_real'] else 'NO / NAO'}",
                f"approaches player: {'YES / SIM' if info['approaching_player'] else 'NO / NAO'}",
                f"distance player: {info['distance_to_player']:.0f}px",
                f"shape: {info['shape_score']:.2f}",
                f"memory / memoria: {info['hostility_memory']:.2f}",
                "",
                f"ENEMY SCORE: {info['enemy_score']:.0f}%",
                "",
                "F10, Q or ESC = exit / sair",
            ]
        )

    y = 28
    for line in lines:
        cv2.putText(panel, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 230), 1, cv2.LINE_AA)
        y += 22

    if state.motion_mask is not None and state.motion_mask.size:
        inset_width = min(panel_width - 24, 320)
        scale = inset_width / state.motion_mask.shape[1]
        inset_height = max(1, round(state.motion_mask.shape[0] * scale))
        inset = cv2.resize(state.motion_mask, (inset_width, inset_height), interpolation=cv2.INTER_NEAREST)
        inset_bgr = cv2.cvtColor(inset, cv2.COLOR_GRAY2BGR)
        start_y = max(0, panel.shape[0] - inset_height - 12)
        panel[start_y:start_y + inset_height, 12:12 + inset_width] = inset_bgr

    return np.hstack([frame, panel])


def _shape_score(aspect: float, contour_area: float, box_area: int, edge_density: float) -> float:
    fill = contour_area / max(1.0, float(box_area))
    aspect_score = 1.0 if 0.75 <= aspect <= 3.6 else 0.55 if 0.45 <= aspect <= 4.5 else 0.15
    fill_score = max(0.0, 1.0 - abs(fill - 0.48) / 0.55)
    edge_score = min(1.0, edge_density / 0.18)
    return max(0.0, min(1.0, 0.50 * aspect_score + 0.25 * fill_score + 0.25 * edge_score))


def _point_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
