from __future__ import annotations

import math
import time

import kage_pilot_live_v03 as live_runtime
import kage_pilot_live_v03k_round as validated_round  # installs the validated v0.3k chain

from pc_agent.kage_pilot.post_combat_v03 import PostCombatDecision
from pc_agent.kage_pilot.visual_position_v351 import PositionState, VisualPositionTracker


_BASE_POST_ENGINE = live_runtime.PostCombatRecoveryEngine
_BASE_POST_LINE = live_runtime._post_line


def _telemetry(event: str, fields: dict[str, object]) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
    print(f"{event}{(' ' + suffix) if suffix else ''}")


class ClosedLoopVisualRecoveryEngine(_BASE_POST_ENGINE):
    """Return to the confirmed Trainer anchor using observed world displacement.

    Existing Trainer detection, thresholds, meditation, recovery and ring search remain owned by
    the validated engine. This layer only decides whether a safe position-aware return/local search
    should happen before the existing fallback. Keys are intentions; visual motion is authority.
    """

    def __init__(
        self,
        *args,
        return_tolerance_cells: float = 0.80,
        return_timeout_seconds: float = 75.0,
        return_max_steps: int = 320,
        return_no_progress_limit: int = 12,
        static_scan_frames: int = 8,
        relocalize_interval_seconds: float = 0.75,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.position = VisualPositionTracker(cell_size=32.0, telemetry=_telemetry)
        self.return_tolerance_cells = max(0.35, min(2.0, float(return_tolerance_cells)))
        self.return_timeout_seconds = max(8.0, min(180.0, float(return_timeout_seconds)))
        self.return_max_steps = max(20, min(2000, int(return_max_steps)))
        self.return_no_progress_limit = max(3, min(100, int(return_no_progress_limit)))
        self.static_scan_frames = max(2, min(30, int(static_scan_frames)))
        self.relocalize_interval_seconds = max(0.25, min(3.0, float(relocalize_interval_seconds)))
        self._commanded_direction: str | None = None
        self._return_started_at: float | None = None
        self._return_steps = 0
        self._return_no_progress = 0
        self._return_last_distance: float | None = None
        self._static_scans = 0
        self._last_relocalize_at = -1e9
        self._local_search_index = 0
        self._fallback_allowed = False
        self._local_search = (
            "right", "left", "down", "up",
            "right", "right", "left", "left",
            "down", "down", "up", "up",
        )

    @staticmethod
    def _current_visual(detector, *, now: float, window_seconds: float = 0.55):
        match = getattr(detector, "_last_visual", None)
        seen_at = float(getattr(detector, "_last_visual_at", -1e9) or -1e9)
        if match is None or float(now) - seen_at > window_seconds:
            return None
        return match

    def _accepted_mode(self) -> str:
        value = str(getattr(self.leader_detector, "last_accepted_template_mode", "-") or "-")
        return value if value in {"32", "64"} else "-"

    def _sync_cell_mode(self) -> str:
        mode = self._accepted_mode()
        if mode in {"32", "64"}:
            cell_size = float(mode)
            if abs(self.position.cell_size - cell_size) > 0.1:
                self.position.cell_size = cell_size
                self.position.odometry.cell_size = cell_size
                self.position.odometry.reset()
                _telemetry("DOJO_CELL_MODE", {"mode": mode, "cell_size": int(cell_size)})
        return mode

    def _set_visual_anchor(self, frame_bgr, observer_state) -> None:
        mode = self._sync_cell_mode()
        self.position.set_anchor(frame_bgr, observer_state, mode=mode)
        self._return_last_distance = 0.0
        self._return_no_progress = 0

    def begin_post_combat(self) -> None:
        super().begin_post_combat()
        self._return_started_at = time.monotonic()
        self._return_steps = 0
        self._return_no_progress = 0
        snapshot = self.position.snapshot()
        self._return_last_distance = math.hypot(snapshot.x, snapshot.y)
        self._static_scans = 0
        self._last_relocalize_at = -1e9
        self._local_search_index = 0
        self._fallback_allowed = False
        _telemetry(
            "DOJO_RETURN_BEGIN",
            {
                "x": f"{snapshot.x:.4f}",
                "y": f"{snapshot.y:.4f}",
                "state": snapshot.state.value,
                "confidence": f"{snapshot.confidence:.3f}",
            },
        )
        _telemetry("DOJO_RETURN_TARGET", {"x": 0, "y": 0})

    def arm_movement_probe(self, direction: str, *, now: float | None = None) -> None:
        self._commanded_direction = str(direction or "").strip().lower() or None
        self.position.note_command(self._commanded_direction)
        super().arm_movement_probe(direction, now=now)

    def report_movement_result(self, direction: str, *, moved: bool, now: float, **kwargs) -> None:
        super().report_movement_result(direction, moved=moved, now=now, **kwargs)
        if not moved:
            self.position.mark_blocked(direction, now=now)

    def observe_world(self, frame_bgr, observer_state, observer, *, now: float):
        self._sync_cell_mode()
        self.position.observe(frame_bgr, observer_state)
        match = super().observe_world(frame_bgr, observer_state, observer, now=now)
        if match is not None and getattr(match, "source", "") == "visual" and not self.position.anchored:
            self._set_visual_anchor(frame_bgr, observer_state)
        return match

    def observe_movement_frame(self, frame_bgr, observer_state, *, now: float) -> None:
        self._sync_cell_mode()
        commanded = self._commanded_direction
        before_distance = math.hypot(self.position.x, self.position.y)
        self.position.observe(
            frame_bgr,
            observer_state,
            commanded_direction=commanded,
        )
        after_distance = math.hypot(self.position.x, self.position.y)
        if commanded and self._return_started_at is not None:
            if after_distance <= before_distance - 0.08:
                self._return_no_progress = 0
            else:
                self._return_no_progress += 1
                _telemetry(
                    "DOJO_RETURN_NO_PROGRESS",
                    {
                        "count": self._return_no_progress,
                        "direction": commanded,
                        "before": f"{before_distance:.4f}",
                        "after": f"{after_distance:.4f}",
                    },
                )
            self._return_last_distance = after_distance
        self._commanded_direction = None
        super().observe_movement_frame(frame_bgr, observer_state, now=now)

    def _hold(self, state: str, reason: str, base: PostCombatDecision | None = None) -> PostCombatDecision:
        return PostCombatDecision(
            state=state,
            leader_score=getattr(base, "leader_score", None),
            leader_distance=getattr(base, "leader_distance", None),
            health=getattr(base, "health", None),
            chakra=getattr(base, "chakra", None),
            reason=reason,
        )

    def _return_expired(self, now: float) -> bool:
        if self._return_started_at is None:
            self._return_started_at = float(now)
        return (
            float(now) - self._return_started_at >= self.return_timeout_seconds
            or self._return_steps >= self.return_max_steps
        )

    def _safe_local_search(self, base: PostCombatDecision) -> PostCombatDecision:
        if self._local_search_index >= len(self._local_search):
            if not self._fallback_allowed:
                self._fallback_allowed = True
                _telemetry("DOJO_SEARCH_FALLBACK_BEGIN", {"reason": "local_search_exhausted"})
            return base
        direction = self._local_search[self._local_search_index]
        self._local_search_index += 1
        _telemetry(
            "DOJO_SAFE_LOCAL_SEARCH_STEP",
            {"direction": direction, "step": self._local_search_index},
        )
        return PostCombatDecision(
            state="SAFE_LOCAL_SEARCH",
            move_pulse=direction,
            leader_score=base.leader_score,
            leader_distance=base.leader_distance,
            health=base.health,
            chakra=base.chakra,
            reason="bounded local search around visual anchor / busca local limitada perto da origem",
        )

    def step(self, frame_bgr, observer_state, observer, *, now: float):
        now = float(now)
        self._sync_cell_mode()
        base = super().step(frame_bgr, observer_state, observer, now=now)
        current_visual = self._current_visual(self.leader_detector, now=now)

        # Existing visual/recovery authority always wins. The origin is refreshed only after
        # a valid nearby Trainer confirmation, never from memory or from the macro start point.
        if current_visual is not None:
            if not self.position.anchored:
                self._set_visual_anchor(frame_bgr, observer_state)
            if base.tap_v or base.state in {
                "READY", "MEDITATING", "START_MEDITATION", "RECOVERY_CONFIRM",
                "SEEK_LEADER", "SELF_OCCLUSION_ESCAPE", "SELF_OCCLUSION_WAIT",
            }:
                distance = getattr(base, "leader_distance", None)
                if distance is not None and int(distance) <= 1 and not self.position.near_origin(0.35):
                    self._set_visual_anchor(frame_bgr, observer_state)
                return base

        snapshot = self.position.snapshot()
        if not snapshot.anchored:
            if not self._fallback_allowed:
                _telemetry("DOJO_POSITION_UNKNOWN", {"reason": "anchor_not_confirmed"})
                _telemetry("DOJO_SAFE_LOCAL_SEARCH_BEGIN", {"reason": "anchor_not_confirmed"})
            return self._safe_local_search(base)

        if self._return_no_progress >= self.return_no_progress_limit:
            self.position.state = PositionState.UNCERTAIN
            _telemetry(
                "DOJO_RETURN_STALLED",
                {"count": self._return_no_progress, "x": self.position.x, "y": self.position.y},
            )

        if snapshot.state != PositionState.KNOWN or self.position.state != PositionState.KNOWN:
            if now - self._last_relocalize_at >= self.relocalize_interval_seconds:
                self._last_relocalize_at = now
                self.position.relocalize(frame_bgr, observer_state)
                snapshot = self.position.snapshot()
                if snapshot.state == PositionState.KNOWN:
                    self._return_no_progress = 0
                    self._return_last_distance = math.hypot(snapshot.x, snapshot.y)
            if snapshot.state != PositionState.KNOWN:
                self._static_scans += 1
                if self._static_scans <= self.static_scan_frames:
                    return self._hold(
                        "RELOCALIZING",
                        "position uncertain/lost; stationary relocalization / posicao incerta; relocalizar parado",
                        base,
                    )
                if not self._fallback_allowed:
                    _telemetry("DOJO_POSITION_UNKNOWN", {"state": snapshot.state.value})
                    _telemetry("DOJO_SAFE_LOCAL_SEARCH_BEGIN", {"reason": "relocalization_failed"})
                return self._safe_local_search(base)

        if self._return_expired(now):
            if not self._fallback_allowed:
                self._fallback_allowed = True
                _telemetry(
                    "DOJO_RETURN_FAILED",
                    {"reason": "timeout_or_step_limit", "steps": self._return_steps},
                )
                _telemetry("DOJO_SAFE_LOCAL_SEARCH_BEGIN", {"reason": "return_limit"})
            return self._safe_local_search(base)

        if not self.position.near_origin(self.return_tolerance_cells):
            direction = self.position.choose_return_direction(now=now)
            if direction is None:
                self.position.state = PositionState.UNCERTAIN
                return self._hold(
                    "RETURN_REPLAN",
                    "no safe direction reduces anchor distance; hold and relocalize / sem direcao segura",
                    base,
                )
            self._return_steps += 1
            remaining_x = -self.position.x
            remaining_y = -self.position.y
            _telemetry(
                "DOJO_RETURN_STEP",
                {
                    "direction": direction,
                    "step": self._return_steps,
                    "x": f"{self.position.x:.4f}",
                    "y": f"{self.position.y:.4f}",
                },
            )
            _telemetry(
                "DOJO_RETURN_REPLAN",
                {"remaining_x": f"{remaining_x:.4f}", "remaining_y": f"{remaining_y:.4f}"},
            )
            return PostCombatDecision(
                state="RETURN_TO_ANCHOR",
                move_pulse=direction,
                leader_score=base.leader_score,
                leader_distance=base.leader_distance,
                health=base.health,
                chakra=base.chakra,
                reason=(
                    f"closed-loop visual return x={self.position.x:.2f} y={self.position.y:.2f} / "
                    f"retorno visual em malha fechada"
                ),
            )

        if self._static_scans == 0:
            _telemetry(
                "DOJO_RETURN_ORIGIN_REACHED",
                {"x": f"{self.position.x:.4f}", "y": f"{self.position.y:.4f}"},
            )
        self._static_scans += 1
        if self._static_scans <= self.static_scan_frames:
            _telemetry(
                "DOJO_RETURN_STATIC_SCAN",
                {
                    "scan": self._static_scans,
                    "score": f"{float(getattr(self.leader_detector, 'last_raw_score', -1.0)):.3f}",
                },
            )
            return self._hold(
                "ANCHOR_STATIC_SCAN",
                "at origin; stationary Trainer scan before movement / na origem; procurar parado",
                base,
            )

        if not self._fallback_allowed:
            _telemetry("DOJO_SAFE_LOCAL_SEARCH_BEGIN", {"reason": "trainer_not_visible_at_origin"})
        return self._safe_local_search(base)


def _post_line_with_visual_position(decision) -> str:
    text = _BASE_POST_LINE(decision)
    try:
        import kage_pilot_live_v03e_round as round_v03e

        engine = round_v03e._ACTIVE_RECOVERY_ENGINE
    except Exception:
        engine = None
    if not isinstance(engine, ClosedLoopVisualRecoveryEngine):
        return text
    position = engine.position.snapshot()
    return (
        text
        + f" position_state={position.state.value}"
        + f" x={position.x:.3f} y={position.y:.3f}"
        + f" position_confidence={position.confidence:.3f}"
        + f" keyframes={position.keyframes}"
    )


live_runtime.PostCombatRecoveryEngine = ClosedLoopVisualRecoveryEngine
live_runtime._post_line = _post_line_with_visual_position


def main() -> int:
    print("Kage Pilot 3.5.1 ROUND: VISUAL POSITION + CLOSED-LOOP TRAINER RETURN")
    print("POSITION: observed world motion is authority; sent keys are intention only")
    print("RETURN: relocalize -> target anchor (0,0) -> static scan -> local search -> existing rings")
    return validated_round.main()


if __name__ == "__main__":
    raise SystemExit(main())
