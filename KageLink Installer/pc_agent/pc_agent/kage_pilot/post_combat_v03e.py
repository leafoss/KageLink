from __future__ import annotations

from dataclasses import dataclass
import math
import time

import cv2
import numpy as np

from .post_combat_v03 import PostCombatDecision
from .post_combat_v03d import PostCombatRecoveryEngineV4


_DIRECTIONS = ("up", "right", "down", "left")


@dataclass(slots=True)
class PendingMovementProbe:
    direction: str
    armed_at: float
    baseline_gray: np.ndarray


class ObstacleAwarePostCombatRecoveryEngine(PostCombatRecoveryEngineV4):
    """v0.3d search plus movement feedback, temporary obstacle avoidance and visual hints.

    A post-combat arrow pulse arms a probe. The next observer frame compares global camera
    translation and arena-frame difference against the frame seen before the pulse. Two
    consecutive no-motion results temporarily block that direction. Search then skips to the
    next ring segment; direct return uses a short perpendicular detour.
    """

    def __init__(
        self,
        *,
        obstacle_confirmations: int = 2,
        obstacle_ttl_seconds: float = 2.5,
        movement_flow_threshold: float = 3.0,
        movement_frame_diff_threshold: float = 8.0,
        movement_probe_delay_seconds: float = 0.07,
        search_hint_threshold: float = 0.80,
        search_hint_hold_seconds: float = 0.45,
        search_hint_cooldown_seconds: float = 0.90,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.obstacle_confirmations = max(1, min(5, int(obstacle_confirmations)))
        self.obstacle_ttl_seconds = max(0.5, min(12.0, float(obstacle_ttl_seconds)))
        self.movement_flow_threshold = max(0.5, min(30.0, float(movement_flow_threshold)))
        self.movement_frame_diff_threshold = max(
            1.0, min(40.0, float(movement_frame_diff_threshold))
        )
        self.movement_probe_delay_seconds = max(
            0.03, min(0.50, float(movement_probe_delay_seconds))
        )
        self.search_hint_threshold = max(0.45, min(0.98, float(search_hint_threshold)))
        self.search_hint_hold_seconds = max(0.10, min(2.0, float(search_hint_hold_seconds)))
        self.search_hint_cooldown_seconds = max(
            0.20, min(5.0, float(search_hint_cooldown_seconds))
        )

        self._last_arena_gray: np.ndarray | None = None
        self._pending_probe: PendingMovementProbe | None = None
        self._movement_failures = {direction: 0 for direction in _DIRECTIONS}
        self._blocked_until = {direction: -1e9 for direction in _DIRECTIONS}
        self._search_hint_active = False
        self._search_hint_until = -1e9
        self._search_hint_cooldown_until = -1e9
        self._last_hint_location: tuple[int, int] | None = None
        self.last_movement_direction: str | None = None
        self.last_movement_detected: bool | None = None
        self.last_flow_magnitude = 0.0
        self.last_frame_difference = 0.0

    @staticmethod
    def _arena_gray(frame_bgr: np.ndarray, arena_rect) -> np.ndarray | None:
        if frame_bgr is None or frame_bgr.size == 0:
            return None
        x0, y0, x1, y1 = (int(value) for value in arena_rect)
        x0, y0 = max(0, x0), max(0, y0)
        x1 = min(frame_bgr.shape[1], x1)
        y1 = min(frame_bgr.shape[0], y1)
        crop = frame_bgr[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        return cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    def arm_movement_probe(self, direction: str, *, now: float | None = None) -> None:
        normalized = str(direction or "").strip().lower()
        if normalized not in _DIRECTIONS or self._last_arena_gray is None:
            return
        if self._pending_probe is not None:
            return
        self._pending_probe = PendingMovementProbe(
            direction=normalized,
            armed_at=time.monotonic() if now is None else float(now),
            baseline_gray=self._last_arena_gray.copy(),
        )

    def observe_movement_frame(self, frame_bgr, observer_state, *, now: float) -> None:
        gray = self._arena_gray(frame_bgr, observer_state.arena_rect)
        if gray is None:
            return

        probe = self._pending_probe
        if probe is not None and float(now) - probe.armed_at >= self.movement_probe_delay_seconds:
            baseline = probe.baseline_gray
            frame_difference = 0.0
            if baseline.shape == gray.shape:
                frame_difference = float(np.mean(cv2.absdiff(baseline, gray)))

            flow = getattr(observer_state, "global_flow", None)
            flow_dx = float(getattr(flow, "dx", 0.0) or 0.0)
            flow_dy = float(getattr(flow, "dy", 0.0) or 0.0)
            flow_magnitude = math.hypot(flow_dx, flow_dy)
            moved = (
                flow_magnitude >= self.movement_flow_threshold
                or frame_difference >= self.movement_frame_diff_threshold
            )
            self.report_movement_result(
                probe.direction,
                moved=moved,
                now=float(now),
                flow_magnitude=flow_magnitude,
                frame_difference=frame_difference,
            )
            self._pending_probe = None

        self._last_arena_gray = gray

    def report_movement_result(
        self,
        direction: str,
        *,
        moved: bool,
        now: float,
        flow_magnitude: float = 0.0,
        frame_difference: float = 0.0,
    ) -> None:
        normalized = str(direction or "").strip().lower()
        if normalized not in _DIRECTIONS:
            return
        self.last_movement_direction = normalized
        self.last_movement_detected = bool(moved)
        self.last_flow_magnitude = float(flow_magnitude)
        self.last_frame_difference = float(frame_difference)

        if moved:
            self._movement_failures[normalized] = 0
            self._blocked_until[normalized] = -1e9
            return

        failures = self._movement_failures[normalized] + 1
        self._movement_failures[normalized] = failures
        if failures >= self.obstacle_confirmations:
            self._movement_failures[normalized] = 0
            self._blocked_until[normalized] = float(now) + self.obstacle_ttl_seconds
            self._skip_current_search_segment_if_matching(normalized)

    def _is_blocked(self, direction: str, *, now: float) -> bool:
        return float(now) < self._blocked_until.get(direction, -1e9)

    def _skip_current_search_segment_if_matching(self, direction: str) -> None:
        search = getattr(self, "search", None)
        if search is None or getattr(search, "phase", None) != direction:
            return
        if getattr(search, "exhausted", False):
            return
        # ConcentricCellRingSearch deliberately exposes progress but keeps segment mechanics
        # internal. This controlled advance abandons only the blocked current segment.
        search._segment_index += 1
        search._start_segment()

    def _alternate_direction(self, preferred: str, *, now: float) -> str | None:
        alternatives = {
            "up": ("right", "left", "down"),
            "right": ("down", "up", "left"),
            "down": ("left", "right", "up"),
            "left": ("up", "down", "right"),
        }
        for candidate in alternatives.get(preferred, _DIRECTIONS):
            if not self._is_blocked(candidate, now=now):
                return candidate
        return None

    def _hint_hold_decision(self, raw_score: float) -> PostCombatDecision:
        return PostCombatDecision(
            state="SEARCH_CONFIRM_HINT",
            reason=(
                f"holding for possible trainer visual raw={raw_score:.3f} / "
                f"aguardando possivel treinador raw={raw_score:.3f}"
            ),
        )

    def _search_decision(self, *, now: float):
        now = float(now)
        detector = self.leader_detector
        raw_score = float(getattr(detector, "last_raw_score", -1.0) or -1.0)
        raw_location = getattr(detector, "last_raw_location", None)

        # A hint produces one bounded hold. It cannot renew itself forever from the same partial
        # or false candidate; after the hold, search resumes through a cooldown interval.
        if self._search_hint_active:
            if now < self._search_hint_until:
                return self._hint_hold_decision(raw_score)
            self._search_hint_active = False
            self._search_hint_cooldown_until = now + self.search_hint_cooldown_seconds
            self._last_hint_location = None

        if (
            now >= self._search_hint_cooldown_until
            and raw_score >= self.search_hint_threshold
            and raw_location is not None
        ):
            self._search_hint_active = True
            self._search_hint_until = now + self.search_hint_hold_seconds
            self._last_hint_location = raw_location
            return self._hint_hold_decision(raw_score)

        # Never spend the rest of a ring segment pressing into a recently confirmed wall.
        for _ in range(4):
            phase = getattr(self.search, "phase", None)
            if phase not in _DIRECTIONS or not self._is_blocked(phase, now=now):
                break
            self._skip_current_search_segment_if_matching(phase)

        decision = super()._search_decision(now=now)
        if decision.move_pulse is None or not self._is_blocked(decision.move_pulse, now=now):
            return decision

        alternative = self._alternate_direction(decision.move_pulse, now=now)
        if alternative is None:
            return PostCombatDecision(
                state="OBSTACLE_HOLD",
                reason="all directions temporarily blocked / todas direcoes bloqueadas temporariamente",
            )
        return PostCombatDecision(
            state="SEARCH_OBSTACLE_DETOUR",
            move_pulse=alternative,
            reason=(
                f"blocked {decision.move_pulse}; search detour {alternative} / "
                f"bloqueado {decision.move_pulse}; desvio {alternative}"
            ),
        )

    def step(self, frame_bgr, observer_state, observer, *, now: float):
        decision = super().step(frame_bgr, observer_state, observer, now=float(now))
        direction = decision.move_pulse
        if direction is None or not self._is_blocked(direction, now=float(now)):
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
                f"blocked {direction}; temporary detour {alternative} / "
                f"bloqueado {direction}; desvio temporario {alternative}"
            ),
        )


__all__ = ["ObstacleAwarePostCombatRecoveryEngine", "PendingMovementProbe"]
