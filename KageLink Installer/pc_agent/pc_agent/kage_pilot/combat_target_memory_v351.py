from __future__ import annotations

import json
import math
from typing import Any, Callable, Iterable

from .combat_target_config_v351 import CombatTargetConfig
from .combat_target_model_v351 import CombatTargetSnapshot, CombatTargetState


Telemetry = Callable[[str, dict[str, object]], None]
_CARDINAL = {"LEFT", "RIGHT", "UP", "DOWN"}


class PersistentCombatTargetMemory:
    """Logical combat identity independent from disposable visual track IDs."""

    def __init__(
        self,
        config: CombatTargetConfig | None = None,
        *,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.config = config or CombatTargetConfig()
        self.telemetry = telemetry
        self._next_combat_target_id = 1
        self._combat_target_id: int | None = None
        self._visual_track_id: int | None = None
        self._state = CombatTargetState.LOST
        self._confidence = 0.0
        self._acquired_at = 0.0
        self._last_seen_at = -1e9
        self._last_seen_frame = 0
        self._last_position: tuple[float, float] | None = None
        self._predicted_position: tuple[float, float] | None = None
        self._velocity = (0.0, 0.0)
        self._target_size: tuple[float, float] | None = None
        self._appearance: tuple[float, ...] = ()
        self._last_direction = "-"
        self._pending_direction = "-"
        self._pending_direction_hits = 0
        self._movement_mode = "PURSUIT"
        self._best_rebind_score = 0.0
        self._pending_switch_track_id: int | None = None
        self._pending_switch_hits = 0
        self._trail: list[tuple[float, float]] = []
        self._last_emitted_state = CombatTargetState.LOST

    @property
    def active(self) -> bool:
        return self._combat_target_id is not None and self._state != CombatTargetState.LOST

    @property
    def combat_target_id(self) -> int | None:
        return self._combat_target_id

    @property
    def visual_track_id(self) -> int | None:
        return self._visual_track_id

    @property
    def state(self) -> CombatTargetState:
        return self._state

    def reset(self, *, preserve_sequence: bool = True) -> None:
        next_id = self._next_combat_target_id if preserve_sequence else 1
        telemetry = self.telemetry
        config = self.config
        self.__init__(config, telemetry=telemetry)
        self._next_combat_target_id = next_id

    def _emit(self, event: str, fields: dict[str, object]) -> None:
        if not self.config.structured_logging_enabled:
            return
        payload = {
            "event": str(event),
            "combat_target_id": self._combat_target_id,
            "visual_track_id": self._visual_track_id,
            **fields,
        }
        if self.telemetry is not None:
            try:
                self.telemetry("DOJO_COMBAT_EVENT", {"payload": json.dumps(payload, sort_keys=True)})
                return
            except Exception:
                pass
        print("DOJO_COMBAT_EVENT " + json.dumps(payload, sort_keys=True))

    @staticmethod
    def _track_position(track: Any) -> tuple[float, float]:
        center = getattr(track, "center", (0.0, 0.0))
        return float(center[0]), float(center[1])

    @staticmethod
    def _track_size(track: Any) -> tuple[float, float]:
        bbox = getattr(track, "bbox", (0, 0, 1, 1))
        return max(1.0, float(bbox[2])), max(1.0, float(bbox[3]))

    @staticmethod
    def _context_appearance(context: Any) -> tuple[float, ...]:
        value = getattr(context, "appearance", ())
        try:
            return tuple(float(item) for item in value)
        except Exception:
            return ()

    def _direction_for(
        self,
        point: tuple[float, float] | None,
        player_center: tuple[float, float],
    ) -> str:
        if point is None:
            return self._last_direction
        dx = float(point[0]) - float(player_center[0])
        dy = float(point[1]) - float(player_center[1])
        if abs(dx) <= self.config.horizontal_dead_zone and abs(dy) <= self.config.vertical_dead_zone:
            return self._last_direction
        if abs(dx) >= abs(dy):
            return "RIGHT" if dx > 0 else "LEFT"
        return "DOWN" if dy > 0 else "UP"

    def _confirm_direction(self, candidate: str) -> None:
        if candidate not in _CARDINAL:
            return
        if self._last_direction not in _CARDINAL:
            self._last_direction = candidate
            self._pending_direction = "-"
            self._pending_direction_hits = 0
            return
        if candidate == self._last_direction:
            self._pending_direction = "-"
            self._pending_direction_hits = 0
            return
        if candidate == self._pending_direction:
            self._pending_direction_hits += 1
        else:
            self._pending_direction = candidate
            self._pending_direction_hits = 1
        if self._pending_direction_hits >= self.config.direction_confirm_frames:
            previous = self._last_direction
            self._last_direction = candidate
            self._pending_direction = "-"
            self._pending_direction_hits = 0
            self._emit("direction_changed", {"previous": previous, "current": candidate})

    def _set_state(self, value: CombatTargetState, *, now: float) -> None:
        previous = self._state
        self._state = value
        if value == previous:
            return
        mapping = {
            CombatTargetState.VISIBLE: "target_visible",
            CombatTargetState.CONTACT: "target_contact",
            CombatTargetState.OCCLUDED_PREDICTED: "target_occluded",
            CombatTargetState.LOCAL_REBIND: "local_rebind_started",
            CombatTargetState.LOST: "target_lost",
        }
        self._emit(
            mapping[value],
            {
                "previous_state": previous.value,
                "target_state": value.value,
                "time_since_last_seen": max(0.0, float(now) - self._last_seen_at),
            },
        )
        self._last_emitted_state = value

    def acquire(
        self,
        track: Any,
        context: Any,
        metrics: Any,
        *,
        player_center: tuple[float, float],
        now: float,
        frame_index: int,
    ) -> None:
        self._combat_target_id = self._next_combat_target_id
        self._next_combat_target_id += 1
        self._visual_track_id = int(getattr(track, "track_id", 0) or 0)
        self._acquired_at = float(now)
        self._last_seen_at = float(now)
        self._last_seen_frame = int(frame_index)
        self._last_position = self._track_position(track)
        self._predicted_position = self._last_position
        self._velocity = tuple(float(value) for value in getattr(track, "residual_velocity", (0.0, 0.0)))
        self._target_size = self._track_size(track)
        self._appearance = self._context_appearance(context)
        self._confidence = 0.72
        self._trail = [self._last_position]
        self._pending_switch_track_id = None
        self._pending_switch_hits = 0
        grid_distance = int(getattr(metrics, "grid_distance", 99) or 99)
        pixel_distance = math.dist(self._last_position, player_center)
        contact = grid_distance <= 1 or pixel_distance <= self.config.contact_radius
        self._movement_mode = "MELEE_LOCK" if contact else "PURSUIT"
        self._last_direction = "-"
        self._confirm_direction(self._direction_for(self._last_position, player_center))
        self._state = CombatTargetState.CONTACT if contact else CombatTargetState.VISIBLE
        self._emit(
            "target_acquired",
            {
                "target_state": self._state.value,
                "position": list(self._last_position),
                "movement_mode": self._movement_mode,
            },
        )

    def observe(
        self,
        track: Any,
        context: Any,
        metrics: Any,
        *,
        player_center: tuple[float, float],
        now: float,
        frame_index: int,
        rebound: bool = False,
        rebind_score: float = 0.0,
    ) -> None:
        position = self._track_position(track)
        previous_position = self._last_position
        previous_seen = self._last_seen_at
        if previous_position is not None and previous_seen > -1e8:
            dt = max(1e-3, float(now) - previous_seen)
            measured = (
                (position[0] - previous_position[0]) / dt,
                (position[1] - previous_position[1]) / dt,
            )
            self._velocity = (
                0.72 * self._velocity[0] + 0.28 * measured[0],
                0.72 * self._velocity[1] + 0.28 * measured[1],
            )
        previous_track = self._visual_track_id
        self._visual_track_id = int(getattr(track, "track_id", 0) or 0)
        self._last_position = position
        self._predicted_position = position
        self._last_seen_at = float(now)
        self._last_seen_frame = int(frame_index)
        self._target_size = self._track_size(track)
        appearance = self._context_appearance(context)
        if appearance:
            self._appearance = appearance
        self._confidence = min(1.0, max(0.55, self._confidence + 0.05))
        self._best_rebind_score = float(rebind_score)
        self._trail.append(position)
        self._trail = self._trail[-16:]
        grid_distance = int(getattr(metrics, "grid_distance", 99) or 99)
        pixel_distance = math.dist(position, player_center)
        contact = grid_distance <= 1 or pixel_distance <= self.config.contact_radius
        self._movement_mode = "MELEE_LOCK" if contact else "PURSUIT"
        context_state = str(getattr(context, "state", "VISIBLE") or "VISIBLE").upper()
        if contact:
            state = CombatTargetState.CONTACT
        elif context_state == "OCCLUDED":
            state = CombatTargetState.OCCLUDED_PREDICTED
        else:
            state = CombatTargetState.VISIBLE
        self._confirm_direction(self._direction_for(position, player_center))
        self._set_state(state, now=now)
        self._pending_switch_track_id = None
        self._pending_switch_hits = 0
        if rebound and previous_track != self._visual_track_id:
            self._emit(
                "local_rebind_success",
                {
                    "previous_visual_track_id": previous_track,
                    "new_visual_track_id": self._visual_track_id,
                    "score": round(float(rebind_score), 4),
                },
            )

    def mark_missing(
        self,
        *,
        now: float,
        frame_index: int,
        flow: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        if self._combat_target_id is None:
            return
        elapsed = max(0.0, float(now) - self._last_seen_at)
        dt = min(elapsed, self.config.hard_lost_timeout)
        flow_x, flow_y = flow if self.config.camera_flow_compensation else (0.0, 0.0)
        if self._last_position is not None:
            self._predicted_position = (
                self._last_position[0] + self._velocity[0] * dt + float(flow_x),
                self._last_position[1] + self._velocity[1] * dt + float(flow_y),
            )
        self._confidence = max(0.0, self._confidence - 0.035)
        rebind_start = min(self.config.contact_hold_seconds, self.config.hard_lost_timeout)
        hard_lost = max(
            self.config.hard_lost_timeout,
            self.config.contact_hold_seconds + self.config.local_rebind_seconds,
        )
        if elapsed < rebind_start:
            state = CombatTargetState.OCCLUDED_PREDICTED
        elif elapsed < hard_lost:
            state = CombatTargetState.LOCAL_REBIND
        else:
            state = CombatTargetState.LOST
            self._visual_track_id = None
            self._confidence = 0.0
        self._set_state(state, now=now)
        if state == CombatTargetState.LOST:
            self._emit(
                "local_rebind_failed",
                {"frames_since_last_seen": max(0, int(frame_index) - self._last_seen_frame)},
            )

    def _size_score(self, track: Any) -> float:
        if self._target_size is None:
            return 0.5
        width, height = self._track_size(track)
        previous_area = max(1.0, self._target_size[0] * self._target_size[1])
        current_area = max(1.0, width * height)
        return math.exp(-abs(math.log(current_area / previous_area)))

    def _appearance_score(self, context: Any) -> float:
        current = self._context_appearance(context)
        if not self._appearance or not current:
            return 0.45
        try:
            from .entity_tracker_v03 import appearance_similarity

            return float(appearance_similarity(self._appearance, current))
        except Exception:
            return 0.0

    def rebind_score(
        self,
        track: Any,
        context: Any,
        metrics: Any,
        *,
        player_center: tuple[float, float],
    ) -> float:
        point = self._track_position(track)
        predicted = self._predicted_position or self._last_position or player_center
        distance = math.dist(point, predicted)
        distance_score = max(0.0, 1.0 - distance / max(1.0, self.config.local_rebind_radius))
        size_score = self._size_score(track)
        appearance_score = self._appearance_score(context)
        direction = self._direction_for(point, player_center)
        movement_score = 0.65
        if self._last_direction in _CARDINAL and direction in _CARDINAL:
            movement_score = 1.0 if direction == self._last_direction else 0.35
        context_state = str(getattr(context, "state", "") or "").upper()
        if context_state == "OCCLUDED":
            movement_score = max(movement_score, 0.85)
        score = (
            self.config.distance_weight * distance_score
            + self.config.size_weight * size_score
            + self.config.appearance_weight * appearance_score
            + self.config.movement_weight * movement_score
        )
        grid_distance = int(getattr(metrics, "grid_distance", 99) or 99)
        if self._movement_mode == "MELEE_LOCK" and grid_distance > 2:
            score *= 0.30
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
        for track in tracks:
            track_id = int(getattr(track, "track_id", 0) or 0)
            context = tracker.context_for(track_id)
            context_state = str(getattr(context, "state", "") or "").upper()
            if context_state not in {"VISIBLE", "OCCLUDED"}:
                continue
            metrics = observer.metrics_for(track_id)
            if metrics is None:
                continue
            point = self._track_position(track)
            predicted = self._predicted_position or self._last_position or player_center
            if math.dist(point, predicted) > self.config.local_rebind_radius:
                if math.dist(point, player_center) > self.config.local_rebind_radius:
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
            return None, 0.0
        self._best_rebind_score = float(choices[0][0])
        return choices[0][1], float(choices[0][0])

    def propose_switch(self, track_id: int) -> bool:
        value = int(track_id)
        if value == self._pending_switch_track_id:
            self._pending_switch_hits += 1
        else:
            self._pending_switch_track_id = value
            self._pending_switch_hits = 1
            self._emit("target_switch_proposed", {"candidate_visual_track_id": value})
        confirmed = self._pending_switch_hits >= self.config.target_switch_confirm_frames
        if confirmed:
            self._emit(
                "target_switch_confirmed",
                {"candidate_visual_track_id": value, "hits": self._pending_switch_hits},
            )
        return confirmed

    def snapshot(self, *, now: float, frame_index: int) -> CombatTargetSnapshot:
        return CombatTargetSnapshot(
            combat_target_id=self._combat_target_id,
            current_visual_track_id=self._visual_track_id,
            target_state=self._state.value,
            confidence=max(0.0, min(1.0, self._confidence)),
            target_age=max(0.0, float(now) - self._acquired_at) if self._combat_target_id else 0.0,
            frames_since_last_seen=max(0, int(frame_index) - self._last_seen_frame),
            time_since_last_seen=max(0.0, float(now) - self._last_seen_at)
            if self._last_seen_at > -1e8
            else 0.0,
            last_known_position=self._last_position,
            predicted_position=self._predicted_position,
            last_contact_direction=self._last_direction,
            movement_mode=self._movement_mode,
            local_rebind_radius=self.config.local_rebind_radius,
            best_rebind_score=self._best_rebind_score,
            target_switch_pending=self._pending_switch_track_id,
            target_switch_confirmation=self._pending_switch_hits,
            target_size=self._target_size,
            trail=tuple(self._trail),
            active=self.active,
        )


__all__ = ["PersistentCombatTargetMemory", "Telemetry"]
