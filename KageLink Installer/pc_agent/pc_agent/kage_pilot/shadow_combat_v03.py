from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShadowDecision:
    mode: str
    navigation: str
    face: str
    base_r: bool
    h_opportunity: bool
    target_id: int | None
    grid_distance: int | None
    reason: str


class ShadowCombatDecisionEngine:
    """Read-only combat decision layer for Kage Pilot v0.3.

    This class never sends input. It converts the validated TARGET + 32px grid state
    into the action that a future controller *would* take. Keeping this separate from
    keyboard control lets real BYOND fights validate decision quality before automation.
    """

    def __init__(
        self,
        *,
        h_stable_seconds: float = 0.60,
        h_cooldown_seconds: float = 2.0,
        h_min_score: float = 55.0,
    ) -> None:
        self.h_stable_seconds = max(0.0, float(h_stable_seconds))
        self.h_cooldown_seconds = max(0.0, float(h_cooldown_seconds))
        self.h_min_score = max(0.0, min(100.0, float(h_min_score)))
        self._target_id: int | None = None
        self._target_since = 0.0
        self._last_h_opportunity = -1e9

    def reset(self) -> None:
        self._target_id = None
        self._target_since = 0.0
        self._last_h_opportunity = -1e9

    @staticmethod
    def _face_from_delta(dx: int, dy: int, fallback: str) -> str:
        if abs(dx) >= abs(dy) and dx != 0:
            return "RIGHT" if dx > 0 else "LEFT"
        if dy != 0:
            return "DOWN" if dy > 0 else "UP"
        return fallback if fallback in {"LEFT", "RIGHT", "UP", "DOWN"} else "-"

    def decide(self, state, observer, tracker, *, now: float) -> ShadowDecision:
        target = state.target
        if target is None:
            self._target_id = None
            self._target_since = 0.0
            return ShadowDecision(
                mode="SEARCH",
                navigation="HOLD",
                face="-",
                base_r=False,
                h_opportunity=False,
                target_id=None,
                grid_distance=None,
                reason="no validated target / sem alvo validado",
            )

        metrics = observer.metrics_for(target.track_id)
        context = tracker.context_for(target.track_id)
        if metrics is None:
            return ShadowDecision(
                mode="TRACK",
                navigation="HOLD",
                face=context.relative_side,
                base_r=True,
                h_opportunity=False,
                target_id=target.track_id,
                grid_distance=None,
                reason="target has no grid metrics yet / alvo ainda sem metricas da grade",
            )

        if self._target_id != target.track_id:
            self._target_id = target.track_id
            self._target_since = float(now)

        stable_for = max(0.0, float(now) - self._target_since)
        dx = int(metrics.cell[0] - metrics.player_cell[0])
        dy = int(metrics.cell[1] - metrics.player_cell[1])
        fallback_side = context.last_visible_side if context.last_visible_side != "-" else context.relative_side
        face = self._face_from_delta(dx, dy, fallback_side)

        contact_like = observer.target_mode in {
            "OCCLUDED",
            "CONTACT_MEMORY",
            "CONTACT_REBIND",
        } or metrics.grid_distance <= 1

        if contact_like:
            navigation = f"FACE_{face}" if face != "-" else "HOLD_MELEE"
            mode = "MELEE"
            reason = f"validated contact d={metrics.grid_distance} mode={observer.target_mode}"
        else:
            navigation = f"MOVE_{face}" if face != "-" else "HOLD"
            mode = "APPROACH"
            reason = (
                f"target {dx:+d},{dy:+d} cells from player; "
                f"toward={metrics.toward_steps} away={metrics.away_steps}"
            )

        visible_for_skill = context.state in {"VISIBLE", "OCCLUDED"}
        skill_ready = (
            contact_like
            and visible_for_skill
            and target.enemy_score >= self.h_min_score
            and stable_for >= self.h_stable_seconds
            and float(now) - self._last_h_opportunity >= self.h_cooldown_seconds
        )
        if skill_ready:
            self._last_h_opportunity = float(now)

        return ShadowDecision(
            mode=mode,
            navigation=navigation,
            face=face,
            base_r=True,
            h_opportunity=skill_ready,
            target_id=target.track_id,
            grid_distance=metrics.grid_distance,
            reason=reason,
        )
