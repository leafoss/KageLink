from __future__ import annotations

from dataclasses import replace
import math
from typing import Any, Iterable

from .combat_target_config_v351 import CombatTargetConfig
from .combat_target_memory_v351 import PersistentCombatTargetMemory
from .combat_target_model_v351 import CombatTargetState


_VALID_VISUAL_STATES = {"VISIBLE"}


def _track_id(track: Any) -> int:
    return int(getattr(track, "track_id", 0) or 0)


def _context_state(tracker: Any, track: Any) -> str:
    try:
        context = tracker.context_for(_track_id(track))
    except Exception:
        return "LOST"
    return str(getattr(context, "state", "LOST") or "LOST").upper()


def _grid_distance(observer: Any, track: Any) -> int | None:
    try:
        metrics = observer.metrics_for(_track_id(track))
    except Exception:
        return None
    if metrics is None:
        return None
    try:
        return int(getattr(metrics, "grid_distance"))
    except (TypeError, ValueError):
        return None


def _track_center(track: Any) -> tuple[float, float]:
    center = getattr(track, "center", (0.0, 0.0))
    return float(center[0]), float(center[1])


def _fallback_body_like(track: Any, tile_size: float) -> bool:
    try:
        _, _, width, height = (float(value) for value in track.bbox)
    except Exception:
        return False
    tile = max(16.0, float(tile_size))
    if width < max(6.0, tile * 0.10) or height < max(12.0, tile * 0.22):
        return False
    if width > tile * 1.10 or height > tile * 1.35:
        return False
    if width / max(1.0, height) > 2.40:
        return False
    if height / max(1.0, width) > 3.00:
        return False
    return float(getattr(track, "shape_score", 0.5) or 0.0) >= 0.28


def choose_contact_candidate(
    tracks: Iterable[Any],
    *,
    tracker: Any,
    observer: Any,
    player_center: tuple[float, float],
    maximum_grid_distance: int = 2,
) -> Any | None:
    """Return only a current visible body; proximity alone grants no authority.

    Kept as a public compatibility helper for tests and diagnostics. Runtime target
    acquisition now flows through the observer's stricter body gate and confirmation
    memory instead of force-replacing the selected target after every frame.
    """

    choices: list[tuple[int, float, float, Any]] = []
    tile_size = float(getattr(observer, "tile_size", 32.0) or 32.0)
    rejection = getattr(observer, "combat_track_rejection_reason", None)
    for track in tuple(tracks or ()):
        if _context_state(tracker, track) != "VISIBLE":
            continue
        distance = _grid_distance(observer, track)
        if distance is None or distance < 1 or distance > max(1, int(maximum_grid_distance)):
            continue
        if callable(rejection):
            try:
                if rejection(track, for_acquire=False) is not None:
                    continue
            except Exception:
                continue
        elif not _fallback_body_like(track, tile_size):
            continue
        point = _track_center(track)
        pixel_distance = math.dist(point, player_center)
        enemy_score = float(getattr(track, "enemy_score", 0.0) or 0.0)
        choices.append((distance, pixel_distance, -enemy_score, track))
    choices.sort(key=lambda item: item[:3])
    return choices[0][3] if choices else None


def _clamp_vector(
    origin: tuple[float, float],
    point: tuple[float, float],
    maximum: float,
) -> tuple[float, float]:
    dx = float(point[0]) - float(origin[0])
    dy = float(point[1]) - float(origin[1])
    magnitude = math.hypot(dx, dy)
    limit = max(1.0, float(maximum))
    if magnitude <= limit or magnitude <= 1e-6:
        return float(point[0]), float(point[1])
    scale = limit / magnitude
    return float(origin[0]) + dx * scale, float(origin[1]) + dy * scale


class HardenedCombatTargetMemory(PersistentCombatTargetMemory):
    """Conservative target memory rebuilt from the failed physical round.

    Memory may preserve who was being fought for a brief effect/occlusion window. It
    cannot promote OCCLUDED blobs, cannot hop immediately to a new track and cannot
    authorize translation. The runtime decision/planner owns the final movement veto.
    """

    def __init__(self, config: CombatTargetConfig | None = None, *, telemetry=None) -> None:
        base = config or CombatTargetConfig()
        hardened = replace(
            base,
            contact_radius=min(48.0, max(32.0, float(base.contact_radius))),
            local_rebind_radius=min(96.0, max(64.0, float(base.local_rebind_radius))),
            contact_hold_seconds=min(0.90, max(0.55, float(base.contact_hold_seconds))),
            local_rebind_seconds=min(1.20, max(0.75, float(base.local_rebind_seconds))),
            hard_lost_timeout=min(3.0, max(2.2, float(base.hard_lost_timeout))),
            minimum_rebind_score=max(0.62, float(base.minimum_rebind_score)),
        )
        super().__init__(hardened, telemetry=telemetry)
        self._last_player_center: tuple[float, float] | None = None
        self._pending_rebind_track_id: int | None = None
        self._pending_rebind_hits = 0

    @staticmethod
    def _limited_velocity(value: tuple[float, float], maximum: float = 64.0) -> tuple[float, float]:
        x, y = float(value[0]), float(value[1])
        magnitude = math.hypot(x, y)
        if magnitude <= maximum or magnitude <= 1e-6:
            return x, y
        scale = maximum / magnitude
        return x * scale, y * scale

    def acquire(self, track, context, metrics, *, player_center, now, frame_index) -> None:
        if str(getattr(context, "state", "") or "").upper() != "VISIBLE":
            return
        self._last_player_center = tuple(float(value) for value in player_center)
        self._pending_rebind_track_id = None
        self._pending_rebind_hits = 0
        super().acquire(
            track,
            context,
            metrics,
            player_center=player_center,
            now=now,
            frame_index=frame_index,
        )
        if self._movement_mode == "MELEE_LOCK":
            self._velocity = (0.0, 0.0)
        else:
            self._velocity = self._limited_velocity(self._velocity)

    def observe(
        self,
        track,
        context,
        metrics,
        *,
        player_center,
        now,
        frame_index,
        rebound=False,
        rebind_score=0.0,
    ) -> None:
        if str(getattr(context, "state", "") or "").upper() != "VISIBLE":
            self.mark_missing(now=now, frame_index=frame_index)
            return
        previous_visual = self._visual_track_id
        self._last_player_center = tuple(float(value) for value in player_center)
        super().observe(
            track,
            context,
            metrics,
            player_center=player_center,
            now=now,
            frame_index=frame_index,
            rebound=rebound,
            rebind_score=rebind_score,
        )
        visual_changed = previous_visual not in {None, self._visual_track_id}
        if rebound or visual_changed or self._movement_mode == "MELEE_LOCK":
            self._velocity = (0.0, 0.0)
        else:
            self._velocity = self._limited_velocity(self._velocity)
        self._predicted_position = self._last_position
        self._pending_rebind_track_id = None
        self._pending_rebind_hits = 0

    def mark_missing(self, *, now, frame_index, flow=(0.0, 0.0)) -> None:
        super().mark_missing(now=now, frame_index=frame_index, flow=flow)
        if self._state == CombatTargetState.LOST or self._last_position is None:
            self._pending_rebind_track_id = None
            self._pending_rebind_hits = 0
            return

        elapsed = max(0.0, float(now) - self._last_seen_at)
        horizon = min(elapsed, 0.35 if self._movement_mode == "MELEE_LOCK" else 0.60)
        velocity = self._limited_velocity(self._velocity)
        # Camera flow is diagnostic context, not a second target translation. Only a
        # tiny bounded correction is retained for local rebind scoring.
        flow_x = max(-4.0, min(4.0, float(flow[0]))) if self.config.camera_flow_compensation else 0.0
        flow_y = max(-4.0, min(4.0, float(flow[1]))) if self.config.camera_flow_compensation else 0.0
        predicted = (
            self._last_position[0] + velocity[0] * horizon + flow_x,
            self._last_position[1] + velocity[1] * horizon + flow_y,
        )
        predicted = _clamp_vector(
            self._last_position,
            predicted,
            self.config.local_rebind_radius * 0.65,
        )
        if self._movement_mode == "MELEE_LOCK" and self._last_player_center is not None:
            predicted = _clamp_vector(
                self._last_player_center,
                predicted,
                self.config.contact_radius * 1.35,
            )
        self._predicted_position = predicted

    def rebind_score(self, track, context, metrics, *, player_center) -> float:
        if str(getattr(context, "state", "") or "").upper() != "VISIBLE":
            return 0.0
        score = super().rebind_score(
            track,
            context,
            metrics,
            player_center=player_center,
        )
        try:
            grid_distance = int(getattr(metrics, "grid_distance"))
        except (TypeError, ValueError):
            return 0.0
        if self._movement_mode == "MELEE_LOCK":
            if grid_distance == 1:
                score = max(score, 0.82)
            elif grid_distance == 0:
                score = min(score, 0.20)
            elif grid_distance > 2:
                score = min(score, 0.10)
        return max(0.0, min(1.0, score))

    def choose_local_rebind(
        self,
        tracks: Iterable[Any],
        *,
        tracker: Any,
        observer: Any,
        player_center: tuple[float, float],
    ) -> tuple[Any | None, float]:
        choices: list[tuple[float, Any]] = []
        rejection = getattr(observer, "combat_track_rejection_reason", None)
        for track in tuple(tracks or ()):
            track_id = _track_id(track)
            context = tracker.context_for(track_id)
            if str(getattr(context, "state", "") or "").upper() != "VISIBLE":
                continue
            metrics = observer.metrics_for(track_id)
            if metrics is None:
                continue
            if callable(rejection):
                try:
                    if rejection(track, for_acquire=False) is not None:
                        continue
                except Exception:
                    continue
            point = self._track_position(track)
            predicted = self._predicted_position or self._last_position or player_center
            if math.dist(point, predicted) > self.config.local_rebind_radius:
                continue
            score = self.rebind_score(
                track,
                context,
                metrics,
                player_center=player_center,
            )
            if score >= self.config.minimum_rebind_score:
                choices.append((score, track))
        choices.sort(key=lambda item: item[0], reverse=True)
        if not choices:
            self._best_rebind_score = 0.0
            self._pending_rebind_track_id = None
            self._pending_rebind_hits = 0
            return None, 0.0

        score, selected = choices[0]
        selected_id = _track_id(selected)
        self._best_rebind_score = float(score)
        if selected_id == self._pending_rebind_track_id:
            self._pending_rebind_hits += 1
        else:
            self._pending_rebind_track_id = selected_id
            self._pending_rebind_hits = 1
        if self._pending_rebind_hits < 2:
            return None, float(score)
        return selected, float(score)


def install_combat_runtime_hardening(runtime: Any):
    """Install conservative physical-memory policy after the logical target bridge."""

    import kage_pilot_live_v03 as live_runtime

    if bool(getattr(live_runtime, "_kagelink_v351_combat_hardening_installed", False)):
        return live_runtime.ParticleSafeGridTargetObserver

    BaseObserver = live_runtime.ParticleSafeGridTargetObserver
    telemetry = getattr(runtime, "_telemetry", None)

    class PhysicallyHardenedCombatObserver(BaseObserver):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            previous = self.combat_memory
            self.combat_memory = HardenedCombatTargetMemory(
                previous.config,
                telemetry=previous.telemetry,
            )
            self._combat_last_snapshot = self.combat_memory.snapshot(
                now=0.0,
                frame_index=0,
            )

    live_runtime.ParticleSafeGridTargetObserver = PhysicallyHardenedCombatObserver
    if hasattr(runtime, "ParticleSafeGridTargetObserver"):
        runtime.ParticleSafeGridTargetObserver = PhysicallyHardenedCombatObserver
    live_runtime._kagelink_v351_combat_hardening_installed = True

    if telemetry is not None:
        telemetry(
            "DOJO_COMBAT_RUNTIME_HARDENING_INSTALLED",
            {
                "proximity_override": "disabled",
                "rebind_visibility": "VISIBLE_ONLY",
                "rebind_confirm_frames": 2,
                "prediction_horizon_melee": "0.35",
                "prediction_horizon_pursuit": "0.60",
                "hard_lost_timeout": "3.0",
                "blind_pursuit": "disabled",
            },
        )
    return PhysicallyHardenedCombatObserver


__all__ = [
    "HardenedCombatTargetMemory",
    "choose_contact_candidate",
    "install_combat_runtime_hardening",
]
