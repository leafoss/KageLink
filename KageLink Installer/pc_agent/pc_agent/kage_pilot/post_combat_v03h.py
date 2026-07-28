from __future__ import annotations

import math

from .post_combat_v03 import PostCombatDecision
from .post_combat_v03d import PostCombatRecoveryEngineV4
from .post_combat_v03e import ObstacleAwarePostCombatRecoveryEngine


class VisualProgressPostCombatRecoveryEngine(ObstacleAwarePostCombatRecoveryEngine):
    """Prefer authoritative trainer visual progress over camera-only obstacle guesses.

    In BYOND the player can move while the global camera-flow estimator remains near zero.
    When the trainer is visible, its screen displacement and the grid distance to it are better
    movement evidence than global flow. A shorter visual distance or a shifted trainer sprite
    clears a stale blocked direction immediately. Real no-progress still requires the existing
    repeated obstacle confirmations before a perpendicular detour is allowed.
    """

    def __init__(
        self,
        *,
        trainer_motion_threshold_px: float = 3.0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.trainer_motion_threshold_px = max(1.0, min(16.0, float(trainer_motion_threshold_px)))
        self._probe_visual_center: tuple[float, float] | None = None
        self._last_visual_distance: int | None = None
        self._last_visual_center: tuple[float, float] | None = None

    @staticmethod
    def _visual_center(match) -> tuple[float, float] | None:
        if match is None or getattr(match, "source", None) != "visual":
            return None
        left, top, width, height = match.bbox
        return (float(left) + float(width) * 0.5, float(top) + float(height) * 0.5)

    def begin_post_combat(self) -> None:
        super().begin_post_combat()
        self._probe_visual_center = self._visual_center(
            getattr(self.leader_detector, "_last_visual", None)
        )
        self._last_visual_center = self._probe_visual_center
        self._last_visual_distance = None

    def arm_movement_probe(self, direction: str, *, now: float | None = None) -> None:
        self._probe_visual_center = self._visual_center(
            getattr(self.leader_detector, "_last_visual", None)
        )
        super().arm_movement_probe(direction, now=now)

    def observe_movement_frame(self, frame_bgr, observer_state, *, now: float) -> None:
        pending = self._pending_probe
        baseline_center = self._probe_visual_center

        # Obtain an authoritative visual on this frame without applying camera flow twice.
        visual = None
        if pending is not None:
            try:
                visual = self.leader_detector.find(
                    frame_bgr,
                    arena_rect=observer_state.arena_rect,
                    flow=None,
                    now=float(now),
                )
            except TypeError:
                visual = self.leader_detector.find(
                    frame_bgr,
                    arena_rect=observer_state.arena_rect,
                )

        super().observe_movement_frame(frame_bgr, observer_state, now=float(now))

        if pending is None or baseline_center is None:
            return
        current_center = self._visual_center(visual)
        if current_center is None:
            return
        displacement = math.hypot(
            current_center[0] - baseline_center[0],
            current_center[1] - baseline_center[1],
        )
        if displacement < self.trainer_motion_threshold_px:
            return

        # The trainer moved on screen after our arrow pulse, therefore Leafos moved relative to
        # the world even if global camera flow and whole-frame difference were both near zero.
        self.report_movement_result(
            pending.direction,
            moved=True,
            now=float(now),
            flow_magnitude=self.last_flow_magnitude,
            frame_difference=max(self.last_frame_difference, displacement),
        )

    @staticmethod
    def _is_visual_decision(decision: PostCombatDecision) -> bool:
        if decision.leader_score is None or decision.leader_distance is None:
            return False
        reason = str(decision.reason or "").casefold()
        return "memory" not in reason and "memoria" not in reason

    def _clear_direction_block(self, direction: str | None) -> None:
        normalized = str(direction or "").strip().lower()
        if normalized not in self._blocked_until:
            return
        self._movement_failures[normalized] = 0
        self._blocked_until[normalized] = -1e9
        if self.last_movement_direction == normalized:
            self.last_movement_detected = True

    def step(self, frame_bgr, observer_state, observer, *, now: float):
        # Bypass v0.3e's final detour wrapper so visual progress can clear a false block before
        # route substitution. Dynamic dispatch still keeps the obstacle-aware blind search.
        decision = PostCombatRecoveryEngineV4.step(
            self,
            frame_bgr,
            observer_state,
            observer,
            now=float(now),
        )

        visual = self._is_visual_decision(decision)
        distance = decision.leader_distance if visual else None
        if distance is not None:
            if self._last_visual_distance is not None and distance < self._last_visual_distance:
                self._clear_direction_block(self.last_movement_direction)
            self._last_visual_distance = int(distance)
        elif decision.leader_score is None:
            self._last_visual_distance = None

        direction = decision.move_pulse
        if direction is None or not self._is_blocked(direction, now=float(now)):
            return decision

        # A current strong visual always gets one direct retry after demonstrated progress.
        if visual and self.last_movement_detected:
            self._clear_direction_block(direction)
            return decision

        alternative = self._alternate_direction(direction, now=float(now))
        if alternative is None:
            return PostCombatDecision(
                state="OBSTACLE_HOLD",
                leader_score=decision.leader_score,
                leader_distance=decision.leader_distance,
                reason=(
                    f"blocked {direction}; waiting for safe direction / "
                    f"bloqueado {direction}; aguardando direcao segura"
                ),
            )
        return PostCombatDecision(
            state="OBSTACLE_DETOUR",
            move_pulse=alternative,
            leader_score=decision.leader_score,
            leader_distance=decision.leader_distance,
            reason=(
                f"blocked {direction}; visual no-progress detour {alternative} / "
                f"bloqueado {direction}; desvio visual sem progresso {alternative}"
            ),
        )


__all__ = ["VisualProgressPostCombatRecoveryEngine"]
