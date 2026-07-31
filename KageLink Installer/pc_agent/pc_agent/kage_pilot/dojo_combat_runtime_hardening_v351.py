from __future__ import annotations

from dataclasses import replace
import math
from typing import Any, Iterable

from .combat_target_config_v351 import CombatTargetConfig
from .combat_target_memory_v351 import PersistentCombatTargetMemory
from .combat_target_model_v351 import CombatTargetState


_VALID_VISUAL_STATES = {"VISIBLE", "OCCLUDED"}


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


def choose_contact_candidate(
    tracks: Iterable[Any],
    *,
    tracker: Any,
    observer: Any,
    player_center: tuple[float, float],
    maximum_grid_distance: int = 2,
) -> Any | None:
    """Choose current local contact before any distant visual blob.

    The physical round videos showed the logical target bound to a distant track while
    another VISIBLE/OCCLUDED track at d=1 was touching the player. Contact authority is
    therefore local: valid d<=2 candidates are sorted by grid distance, player distance
    and enemy score. LOST tracker entries are never eligible.
    """

    choices: list[tuple[int, float, float, Any]] = []
    for track in tuple(tracks or ()):
        if _context_state(tracker, track) not in _VALID_VISUAL_STATES:
            continue
        distance = _grid_distance(observer, track)
        if distance is None or distance > max(1, int(maximum_grid_distance)):
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
    """Persistent target memory calibrated from the first physical PR23 videos."""

    def __init__(self, config: CombatTargetConfig | None = None, *, telemetry=None) -> None:
        base = config or CombatTargetConfig()
        hardened = replace(
            base,
            contact_radius=max(56.0, float(base.contact_radius)),
            local_rebind_radius=max(128.0, float(base.local_rebind_radius)),
            contact_hold_seconds=max(3.0, float(base.contact_hold_seconds)),
            local_rebind_seconds=max(5.0, float(base.local_rebind_seconds)),
            hard_lost_timeout=max(8.0, float(base.hard_lost_timeout)),
            minimum_rebind_score=min(0.40, float(base.minimum_rebind_score)),
        )
        super().__init__(hardened, telemetry=telemetry)
        self._last_player_center: tuple[float, float] | None = None

    @staticmethod
    def _limited_velocity(value: tuple[float, float], maximum: float = 88.0) -> tuple[float, float]:
        x, y = float(value[0]), float(value[1])
        magnitude = math.hypot(x, y)
        if magnitude <= maximum or magnitude <= 1e-6:
            return x, y
        scale = maximum / magnitude
        return x * scale, y * scale

    def acquire(self, track, context, metrics, *, player_center, now, frame_index) -> None:
        self._last_player_center = tuple(float(value) for value in player_center)
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
        # A new visual ID is not a physically measured teleport. Treating the ID swap
        # as velocity produced predictions hundreds of pixels outside the arena.
        if rebound or visual_changed or self._movement_mode == "MELEE_LOCK":
            self._velocity = (0.0, 0.0)
        else:
            self._velocity = self._limited_velocity(self._velocity)
        self._predicted_position = self._last_position

    def mark_missing(self, *, now, frame_index, flow=(0.0, 0.0)) -> None:
        super().mark_missing(now=now, frame_index=frame_index, flow=flow)
        if self._state == CombatTargetState.LOST or self._last_position is None:
            return

        elapsed = max(0.0, float(now) - self._last_seen_at)
        horizon = min(elapsed, 0.65 if self._movement_mode == "MELEE_LOCK" else 1.25)
        velocity = self._limited_velocity(self._velocity)
        flow_x = max(-8.0, min(8.0, float(flow[0]))) if self.config.camera_flow_compensation else 0.0
        flow_y = max(-8.0, min(8.0, float(flow[1]))) if self.config.camera_flow_compensation else 0.0
        predicted = (
            self._last_position[0] + velocity[0] * horizon + flow_x,
            self._last_position[1] + velocity[1] * horizon + flow_y,
        )
        predicted = _clamp_vector(
            self._last_position,
            predicted,
            self.config.local_rebind_radius,
        )
        if self._movement_mode == "MELEE_LOCK" and self._last_player_center is not None:
            predicted = _clamp_vector(
                self._last_player_center,
                predicted,
                self.config.contact_radius * 1.75,
            )
        self._predicted_position = predicted

    def rebind_score(self, track, context, metrics, *, player_center) -> float:
        if str(getattr(context, "state", "LOST") or "LOST").upper() not in _VALID_VISUAL_STATES:
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
        pixel_distance = math.dist(self._track_position(track), player_center)
        if self._movement_mode == "MELEE_LOCK":
            if grid_distance <= 1:
                score = max(score, 0.94)
            elif grid_distance == 2:
                score = max(score, 0.74)
            elif grid_distance > 3:
                score = min(score, 0.12)
        if pixel_distance <= self.config.contact_radius * 1.35:
            score = max(score, 0.88)
        return max(0.0, min(1.0, score))


def install_combat_runtime_hardening(runtime: Any):
    """Install physical-video hardening after the logical target bridge."""

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

        def process(self, frame_bgr, *, timestamp=None):
            state = super().process(frame_bgr, timestamp=timestamp)
            tracks = tuple(getattr(state, "tracks", ()) or ())
            player_center = tuple(float(value) for value in state.player_center)
            memory = self.combat_memory

            current = state.target
            current_valid = (
                current is not None
                and _context_state(self.tracker, current) in _VALID_VISUAL_STATES
            )
            if current is not None and not current_valid:
                # The first physical video showed a new logical target acquired from a
                # tracker entry already marked LOST. Never promote stale entries.
                if memory.visual_track_id == _track_id(current):
                    memory.reset(preserve_sequence=True)
                state = replace(state, target_id=None)
                current = None

            contact = choose_contact_candidate(
                tracks,
                tracker=self.tracker,
                observer=self,
                player_center=player_center,
                maximum_grid_distance=2,
            )
            current_distance = _grid_distance(self, current) if current is not None else None
            should_prefer_contact = contact is not None and (
                current is None
                or current_distance is None
                or current_distance > 2
                or (
                    memory.active
                    and memory.state in {
                        CombatTargetState.OCCLUDED_PREDICTED,
                        CombatTargetState.LOCAL_REBIND,
                    }
                )
            )

            if should_prefer_contact:
                context = self.tracker.context_for(_track_id(contact))
                metrics = self.metrics_for(_track_id(contact))
                if metrics is not None:
                    if memory.combat_target_id is None:
                        memory.acquire(
                            contact,
                            context,
                            metrics,
                            player_center=player_center,
                            now=float(state.timestamp),
                            frame_index=self._combat_frame_index,
                        )
                    else:
                        score = memory.rebind_score(
                            contact,
                            context,
                            metrics,
                            player_center=player_center,
                        )
                        memory.observe(
                            contact,
                            context,
                            metrics,
                            player_center=player_center,
                            now=float(state.timestamp),
                            frame_index=self._combat_frame_index,
                            rebound=memory.visual_track_id != _track_id(contact),
                            rebind_score=score,
                        )
                    state = replace(state, target_id=_track_id(contact))
                    if telemetry is not None:
                        telemetry(
                            "DOJO_COMBAT_CONTACT_OVERRIDE",
                            {
                                "combat_target_id": memory.combat_target_id,
                                "visual_track_id": _track_id(contact),
                                "previous_visual_track_id": _track_id(current) if current is not None else "-",
                                "grid_distance": _grid_distance(self, contact),
                            },
                        )

            self._combat_last_snapshot = memory.snapshot(
                now=float(state.timestamp),
                frame_index=self._combat_frame_index,
            )
            return state

    live_runtime.ParticleSafeGridTargetObserver = PhysicallyHardenedCombatObserver
    if hasattr(runtime, "ParticleSafeGridTargetObserver"):
        runtime.ParticleSafeGridTargetObserver = PhysicallyHardenedCombatObserver
    live_runtime._kagelink_v351_combat_hardening_installed = True

    if telemetry is not None:
        telemetry(
            "DOJO_COMBAT_RUNTIME_HARDENING_INSTALLED",
            {
                "contact_priority": "d<=2",
                "prediction_horizon_melee": "0.65",
                "prediction_horizon_pursuit": "1.25",
                "hard_lost_timeout": "8.0",
            },
        )
    return PhysicallyHardenedCombatObserver


__all__ = [
    "HardenedCombatTargetMemory",
    "choose_contact_candidate",
    "install_combat_runtime_hardening",
]
