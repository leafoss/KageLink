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
    engagement_active: bool
    engagement_stable_seconds: float


class ShadowCombatDecisionEngine:
    """Read-only combat decision layer for Kage Pilot v0.3.

    The engine never sends input. It converts the validated TARGET + 32px grid state
    into the action that a future controller would take.

    Important BYOND combat semantics learned from real tests:
    - R is a combat-session base state and must remain logically ON even while visual
      TARGET is temporarily unavailable;
    - visual ENTITY ids are disposable. H stability belongs to the logical engagement,
      not one OpenCV track id;
    - CONTACT_MEMORY preserves the last visually confirmed facing direction instead of
      trusting stale geometry while sprites overlap.
    """

    def __init__(
        self,
        *,
        h_stable_seconds: float = 0.60,
        h_cooldown_seconds: float = 2.0,
        h_min_score: float = 55.0,
        engagement_gap_seconds: float = 0.75,
        combat_active_on_start: bool = True,
    ) -> None:
        self.h_stable_seconds = max(0.0, float(h_stable_seconds))
        self.h_cooldown_seconds = max(0.0, float(h_cooldown_seconds))
        self.h_min_score = max(0.0, min(100.0, float(h_min_score)))
        self.engagement_gap_seconds = max(0.1, min(3.0, float(engagement_gap_seconds)))
        self.combat_active_on_start = bool(combat_active_on_start)
        self._combat_active = self.combat_active_on_start
        self._contact_since: float | None = None
        self._last_contact_at = -1e9
        self._last_h_opportunity = -1e9
        self._last_confirmed_face = "-"

    def reset(self) -> None:
        self._combat_active = self.combat_active_on_start
        self._contact_since = None
        self._last_contact_at = -1e9
        self._last_h_opportunity = -1e9
        self._last_confirmed_face = "-"

    @staticmethod
    def _face_from_delta(dx: int, dy: int, fallback: str) -> str:
        if abs(dx) >= abs(dy) and dx != 0:
            return "RIGHT" if dx > 0 else "LEFT"
        if dy != 0:
            return "DOWN" if dy > 0 else "UP"
        return fallback if fallback in {"LEFT", "RIGHT", "UP", "DOWN"} else "-"

    def _expire_contact_if_needed(self, now: float) -> None:
        if self._contact_since is None:
            return
        if float(now) - self._last_contact_at > self.engagement_gap_seconds:
            self._contact_since = None

    def _engagement_stable_for(self, now: float) -> float:
        if self._contact_since is None:
            return 0.0
        return max(0.0, float(now) - self._contact_since)

    def decide(self, state, observer, tracker, *, now: float) -> ShadowDecision:
        now = float(now)
        target = state.target

        if target is None:
            self._expire_contact_if_needed(now)
            mode = "ENGAGED_SEARCH" if self._combat_active else "SEARCH"
            face = self._last_confirmed_face if self._combat_active else "-"
            return ShadowDecision(
                mode=mode,
                navigation="HOLD",
                face=face,
                base_r=self._combat_active,
                h_opportunity=False,
                target_id=None,
                grid_distance=None,
                reason=(
                    "combat active; target temporarily unavailable / combate ativo; alvo temporariamente indisponivel"
                    if self._combat_active
                    else "no validated target / sem alvo validado"
                ),
                engagement_active=self._combat_active,
                engagement_stable_seconds=self._engagement_stable_for(now),
            )

        self._combat_active = True
        metrics = observer.metrics_for(target.track_id)
        context = tracker.context_for(target.track_id)
        if metrics is None:
            return ShadowDecision(
                mode="TRACK",
                navigation="HOLD",
                face=self._last_confirmed_face if self._last_confirmed_face != "-" else context.relative_side,
                base_r=True,
                h_opportunity=False,
                target_id=target.track_id,
                grid_distance=None,
                reason="target has no grid metrics yet / alvo ainda sem metricas da grade",
                engagement_active=True,
                engagement_stable_seconds=self._engagement_stable_for(now),
            )

        dx = int(metrics.cell[0] - metrics.player_cell[0])
        dy = int(metrics.cell[1] - metrics.player_cell[1])
        fallback_side = context.last_visible_side if context.last_visible_side != "-" else context.relative_side
        measured_face = self._face_from_delta(dx, dy, fallback_side)

        visual_confirmation = context.state in {"VISIBLE", "OCCLUDED"}
        if visual_confirmation and measured_face != "-":
            self._last_confirmed_face = measured_face

        if observer.target_mode == "CONTACT_MEMORY" and self._last_confirmed_face != "-":
            face = self._last_confirmed_face
        else:
            face = measured_face if measured_face != "-" else self._last_confirmed_face

        contact_like = observer.target_mode in {
            "OCCLUDED",
            "CONTACT_MEMORY",
            "CONTACT_REBIND",
        } or metrics.grid_distance <= 1

        if contact_like:
            if self._contact_since is None or now - self._last_contact_at > self.engagement_gap_seconds:
                self._contact_since = now
            self._last_contact_at = now
        else:
            self._expire_contact_if_needed(now)

        stable_for = self._engagement_stable_for(now)

        if contact_like:
            navigation = f"FACE_{face}" if face != "-" else "HOLD_MELEE"
            mode = "MELEE"
            reason = (
                f"logical engagement d={metrics.grid_distance} mode={observer.target_mode}; "
                f"stable={stable_for:.2f}s"
            )
        else:
            navigation = f"MOVE_{face}" if face != "-" else "HOLD"
            mode = "APPROACH"
            reason = (
                f"target {dx:+d},{dy:+d} cells from player; "
                f"toward={metrics.toward_steps} away={metrics.away_steps}"
            )

        skill_ready = (
            contact_like
            and visual_confirmation
            and observer.target_mode != "CONTACT_MEMORY"
            and target.enemy_score >= self.h_min_score
            and stable_for >= self.h_stable_seconds
            and now - self._last_h_opportunity >= self.h_cooldown_seconds
        )
        if skill_ready:
            self._last_h_opportunity = now

        return ShadowDecision(
            mode=mode,
            navigation=navigation,
            face=face,
            base_r=True,
            h_opportunity=skill_ready,
            target_id=target.track_id,
            grid_distance=metrics.grid_distance,
            reason=reason,
            engagement_active=True,
            engagement_stable_seconds=stable_for,
        )
