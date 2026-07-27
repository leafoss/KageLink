from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from .entity_observer import (
    EntityObserver,
    FlowEstimate,
    ObserverConfig,
    ObserverState,
    arena_rect_for_frame,
    detect_candidates,
    estimate_global_flow,
)
from .entity_tracker_v03 import MeleeAwareEntityTracker


@dataclass(slots=True)
class V03ObserverConfig(ObserverConfig):
    """Real-game calibration and lock settings for the v0.3 observer."""

    player_box_width: float = 18.0
    player_box_height: float = 38.0
    target_acquire_threshold: float = 55.0
    target_keep_threshold: float = 38.0

    # Dynamic background memory: repeated dense and visually similar motion, such
    # as animated water, is learned as scenery instead of spawning endless ENTITYs.
    dynamic_background_enabled: bool = True
    background_cell_size: float = 32.0
    background_neighbor_radius: float = 58.0
    background_min_neighbors: int = 3
    background_min_dense_hits: float = 8.0
    background_min_age: float = 0.8
    background_similarity: float = 0.88
    background_player_guard: float = 78.0
    background_memory_ttl: float = 12.0

    # Dormant identity memory used after a track has exceeded the active TTL.
    reacquire_ttl: float = 5.0
    reacquire_distance: float = 180.0
    reacquire_similarity: float = 0.82

    def normalized(self) -> "V03ObserverConfig":
        # dataclass(slots=True) may replace the class object during decoration,
        # which makes zero-argument super() unsafe on some Python versions.
        ObserverConfig.normalized(self)
        self.player_box_width = max(6.0, min(80.0, float(self.player_box_width)))
        self.player_box_height = max(10.0, min(120.0, float(self.player_box_height)))
        self.target_acquire_threshold = max(0.0, min(100.0, float(self.target_acquire_threshold)))
        self.target_keep_threshold = max(
            0.0,
            min(self.target_acquire_threshold, float(self.target_keep_threshold)),
        )
        self.background_cell_size = max(12.0, min(96.0, float(self.background_cell_size)))
        self.background_neighbor_radius = max(20.0, min(180.0, float(self.background_neighbor_radius)))
        self.background_min_neighbors = max(1, min(12, int(self.background_min_neighbors)))
        self.background_min_dense_hits = max(2.0, float(self.background_min_dense_hits))
        self.background_min_age = max(0.1, float(self.background_min_age))
        self.background_similarity = max(0.0, min(1.0, float(self.background_similarity)))
        self.background_player_guard = max(20.0, float(self.background_player_guard))
        self.background_memory_ttl = max(2.0, float(self.background_memory_ttl))
        self.reacquire_ttl = max(0.5, float(self.reacquire_ttl))
        self.reacquire_distance = max(30.0, float(self.reacquire_distance))
        self.reacquire_similarity = max(0.0, min(1.0, float(self.reacquire_similarity)))
        return self


def player_box_rect(
    player_center: tuple[float, float],
    config: V03ObserverConfig,
) -> tuple[int, int, int, int]:
    """Return arena-local x, y, width, height for the vertical player box."""

    width = max(1, round(config.player_box_width))
    height = max(1, round(config.player_box_height))
    x = round(player_center[0] - width / 2.0)
    y = round(player_center[1] - height / 2.0)
    return x, y, width, height


def choose_locked_target(
    tracks,
    *,
    current_target_id: int | None,
    acquire_threshold: float,
    keep_threshold: float,
) -> int | None:
    """Target hysteresis: keeping a known target is easier than acquiring a new one."""

    tracks = tuple(tracks)
    if current_target_id is not None:
        current = next((track for track in tracks if track.track_id == current_target_id), None)
        if current is not None and current.enemy_score >= keep_threshold:
            return current_target_id

    candidate = max(tracks, key=lambda track: track.enemy_score, default=None)
    if candidate is not None and candidate.enemy_score >= acquire_threshold:
        return candidate.track_id
    return None


class StableTargetObserver(EntityObserver):
    """EntityObserver with context-aware tracking and persistent target lock."""

    def __init__(self, config: V03ObserverConfig) -> None:
        EntityObserver.__init__(self, config)
        self.config = config
        self._locked_target_id: int | None = None

    def reset(self) -> None:
        EntityObserver.reset(self)
        self._locked_target_id = None

    def process(self, frame_bgr: np.ndarray, *, timestamp: float | None = None) -> ObserverState:
        """Run the same OpenCV pipeline while giving the v0.3 tracker frame context."""

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
            if isinstance(self.tracker, MeleeAwareEntityTracker):
                self.tracker.prepare_frame(contrast)
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
        if isinstance(self.tracker, MeleeAwareEntityTracker):
            self.tracker.prepare_frame(contrast)
        tracks = self.tracker.update(candidates, flow=flow, player_center=player_center, now=now)

        self._locked_target_id = choose_locked_target(
            tracks,
            current_target_id=self._locked_target_id,
            acquire_threshold=self.config.target_acquire_threshold,
            keep_threshold=self.config.target_keep_threshold,
        )
        self._previous_gray = contrast
        return ObserverState(
            timestamp=now,
            arena_rect=arena_rect,
            player_center=player_center,
            global_flow=flow,
            tracks=tracks,
            target_id=self._locked_target_id,
            motion_mask=motion_mask,
        )


def render_overlay_v03(
    frame_bgr: np.ndarray,
    state: ObserverState,
    config: V03ObserverConfig,
    tracker: MeleeAwareEntityTracker | None = None,
) -> np.ndarray:
    """Render read-only v0.3 diagnostics including contextual tracking state."""

    frame = frame_bgr.copy()
    x0, y0, x1, y1 = state.arena_rect
    cv2.rectangle(frame, (x0, y0), (x1, y1), (120, 120, 120), 1)

    px, py, pw, ph = player_box_rect(state.player_center, config)
    player_full = (x0 + px, y0 + py, pw, ph)
    cv2.rectangle(
        frame,
        (player_full[0], player_full[1]),
        (player_full[0] + pw, player_full[1] + ph),
        (255, 255, 255),
        2,
    )
    cv2.putText(
        frame,
        "PLAYER #000",
        (player_full[0] + pw + 6, max(18, player_full[1] + 14)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )

    for track in state.tracks:
        tx, ty, tw, th = track.bbox
        full_box = (x0 + tx, y0 + ty, tw, th)
        is_target = track.track_id == state.target_id
        context = tracker.context_for(track.track_id) if tracker is not None else None
        is_occluded = context is not None and context.state == "OCCLUDED"
        color = (0, 220, 255) if is_target else (0, 190, 0)
        if is_occluded:
            color = (0, 165, 255)
        thickness = 2 if is_target or is_occluded else 1
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
        if context is not None and context.relative_side != "-":
            label += f" {context.relative_side}"
        if is_occluded:
            label += " OCCLUDED"
        if is_target:
            label += " TARGET LOCK"
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

    panel_width = 400
    panel = np.zeros((frame.shape[0], panel_width, 3), dtype=np.uint8)
    background_suppressed = tracker.background.suppressed_last_frame if tracker is not None else 0
    background_cells = tracker.background.mature_cells if tracker is not None else 0
    dormant = tracker.dormant_count if tracker is not None else 0
    lines = [
        "KAGE PILOT v0.3 - ENTITY OBSERVER",
        "READ ONLY / SOMENTE OBSERVACAO",
        "",
        f"global flow: dx={state.global_flow.dx:+.1f} dy={state.global_flow.dy:+.1f}",
        f"LK points: {state.global_flow.points}",
        f"entities: {len(state.tracks)}",
        f"dynamic bg suppressed: {background_suppressed}",
        f"dynamic bg cells: {background_cells}",
        f"dormant identities: {dormant}",
        f"PLAYER box: {config.player_box_width:.0f}x{config.player_box_height:.0f}px",
        f"target acquire/keep: {config.target_acquire_threshold:.0f}%/{config.target_keep_threshold:.0f}%",
        "",
    ]

    target = state.target
    if target is None:
        lines.extend(["TARGET: searching / procurando", "", "Q or ESC = exit / sair"])
    else:
        info = target.to_dict(state.player_center, now=state.timestamp)
        context = tracker.context_for(target.track_id) if tracker is not None else None
        state_name = context.state if context is not None else "VISIBLE"
        side = context.relative_side if context is not None else "-"
        appearance = context.appearance_similarity if context is not None else 0.0
        lines.extend(
            [
                f"LOCKED ENTITY #{target.track_id:03d}",
                f"state / estado: {state_name}",
                f"relative side / lado: {side}",
                f"appearance sim.: {appearance:.2f}",
                f"position / posicao: {info['center'][0]:.0f},{info['center'][1]:.0f}",
                f"observed / observado: {info['observed_seconds']:.1f}s",
                f"displacement / desloc.: {info['total_residual_displacement']:.0f}px",
                f"direction / direcao: {info['direction']}",
                f"speed / velocidade: {info['residual_speed']:.1f}px/s",
                f"real motion: {'YES / SIM' if info['movement_real'] else 'NO / NAO'}",
                f"approaches player: {'YES / SIM' if info['approaching_player'] else 'NO / NAO'}",
                f"distance player: {info['distance_to_player']:.0f}px",
                f"memory / memoria: {info['hostility_memory']:.2f}",
                "",
                f"ENEMY SCORE: {info['enemy_score']:.0f}%",
                "",
                "Q or ESC = exit / sair",
            ]
        )

    y = 28
    for line in lines:
        cv2.putText(
            panel,
            line,
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (230, 230, 230),
            1,
            cv2.LINE_AA,
        )
        y += 20

    if state.motion_mask is not None and state.motion_mask.size:
        inset_width = min(panel_width - 24, 360)
        scale = inset_width / state.motion_mask.shape[1]
        inset_height = max(1, round(state.motion_mask.shape[0] * scale))
        inset = cv2.resize(
            state.motion_mask,
            (inset_width, inset_height),
            interpolation=cv2.INTER_NEAREST,
        )
        inset_bgr = cv2.cvtColor(inset, cv2.COLOR_GRAY2BGR)
        start_y = max(0, panel.shape[0] - inset_height - 12)
        panel[start_y:start_y + inset_height, 12:12 + inset_width] = inset_bgr

    return np.hstack([frame, panel])
