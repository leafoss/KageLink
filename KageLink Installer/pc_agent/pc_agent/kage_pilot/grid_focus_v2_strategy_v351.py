from __future__ import annotations

from . import combat_strategy_v351 as strategy_module
from .combat_strategy_v351 import (
    CombatPhase,
    CombatStrategyConfig,
    CombatStrategyFrame,
    CombatTargetSnapshotV2,
    GridFocusV2Strategy as _GridFocusV2Base,
    GridRebindHypothesis,
    PendingRebind,
    PerceptionScope,
    chebyshev_distance,
    direction_between,
)


class GridFocusV2SpatialStrategy(_GridFocusV2Base):
    """Canonical experimental strategy whose identity follows a spatial cell.

    This concrete implementation is registered through the explicit strategy registry;
    it is not a runtime monkeypatch or another hardening bridge. Even the current visual
    track cannot move the confirmed identity to a different cell after one frame. A
    clean adjacent transition is quarantined until two coherent observations agree.
    """

    name = "grid_focus_v2"

    @staticmethod
    def _step_direction(origin, target) -> tuple[int, int]:
        return (
            max(-1, min(1, int(target[0]) - int(origin[0]))),
            max(-1, min(1, int(target[1]) - int(origin[1]))),
        )

    def _begin_transition(self, current, frame: CombatStrategyFrame) -> None:
        hypothesis = GridRebindHypothesis(
            candidate_cell=current.anchor_cell,
            first_seen_at=frame.timestamp,
            last_seen_at=frame.timestamp,
            clean_hits=1,
            supporting_track_ids={current.track_id},
            best_score=current.enemy_score,
            best_observation=current,
        )
        self._rebind_hypotheses.clear()
        self._rebind_hypotheses[current.anchor_cell] = hypothesis
        self._pending_rebind = PendingRebind(
            cell=current.anchor_cell,
            track_id=current.track_id,
            first_observation=current,
            hits=1,
            score=current.enemy_score,
            hypothesis=hypothesis,
        )

    def _confirm_transition_cell(
        self,
        observation,
        frame: CombatStrategyFrame,
        *,
        reason: str,
    ) -> None:
        target = self._target
        if target is None:
            return
        self._accept_clean(observation, frame.player_cell, rebound=False)
        confirmed_direction = direction_between(
            frame.player_cell,
            observation.anchor_cell,
            target.last_confirmed_direction,
        )
        target.last_confirmed_direction = confirmed_direction
        target.pending_direction = "-"
        target.pending_direction_hits = 0
        # Prediction starts from the newly proven cell. Moving it another cell in the
        # same confirmation frame would create a two-cell jump in the black box even
        # though only one spatial transition was actually proven.
        target.predicted_cell = observation.anchor_cell
        self._scope = PerceptionScope.LOCKED_CELL_FOCUS
        self._last_reason = reason

    def _same_track_transition(self, frame: CombatStrategyFrame, clean) -> bool:
        target = self._target
        if target is None:
            return False
        current = next(
            (
                item
                for item in clean
                if item.track_id == target.clean_visual_track_id
            ),
            None,
        )
        if current is None:
            return False

        distance = chebyshev_distance(current.anchor_cell, target.confirmed_cell)
        if distance == 0:
            self._accept_clean(current, frame.player_cell, rebound=False)
            target.predicted_cell = target.confirmed_cell
            self._pending_rebind = None
            self._rebind_hypotheses.clear()
            self._scope = PerceptionScope.LOCKED_CELL_FOCUS
            self._last_reason = "clean body remains in confirmed cell"
            return True

        pending = self._pending_rebind
        if pending is not None and pending.track_id == current.track_id:
            pending_cell = pending.cell
            if current.anchor_cell == pending_cell:
                hypothesis = pending.hypothesis
                hypothesis.clean_hits += 1
                hypothesis.last_seen_at = frame.timestamp
                hypothesis.supporting_track_ids.add(current.track_id)
                hypothesis.best_score = max(
                    hypothesis.best_score,
                    current.enemy_score,
                )
                hypothesis.best_observation = current
                self._pending_rebind = PendingRebind(
                    cell=current.anchor_cell,
                    track_id=current.track_id,
                    first_observation=pending.first_observation,
                    hits=hypothesis.clean_hits,
                    score=hypothesis.best_score,
                    hypothesis=hypothesis,
                )
                target.current_clean_visible = False
                self._scope = PerceptionScope.PREDICTED_CELL_FOCUS
                self._last_reason = (
                    f"same-track cell transition quarantined cell={current.anchor_cell} "
                    f"clean_hits={hypothesis.clean_hits}"
                )
                if hypothesis.clean_hits >= self.config.rebind_confirm_hits:
                    self._confirm_transition_cell(
                        current,
                        frame,
                        reason="same-track spatial transition confirmed after quarantine",
                    )
                    self._pending_rebind = None
                    self._rebind_hypotheses.clear()
                return True

            # A fast body may traverse one new cell per frame. Two consecutive clean
            # observations in the same direction prove the *previous pending cell*,
            # not the newest cell. This advances authority one cell at a time and then
            # quarantines the newest observation as the next candidate cell.
            pending_step = self._step_direction(target.confirmed_cell, pending_cell)
            current_step = self._step_direction(pending_cell, current.anchor_cell)
            coherent_motion = (
                chebyshev_distance(pending_cell, current.anchor_cell) <= 1
                and pending_step == current_step
                and pending_step != (0, 0)
            )
            if coherent_motion:
                self._confirm_transition_cell(
                    pending.first_observation,
                    frame,
                    reason="fast trajectory proved previous pending cell",
                )
                self._begin_transition(current, frame)
                target.current_clean_visible = False
                self._scope = PerceptionScope.PREDICTED_CELL_FOCUS
                self._last_reason = (
                    f"trajectory advanced one cell; next cell quarantined "
                    f"cell={current.anchor_cell} clean_hits=1"
                )
                return True

            self._pending_rebind = None
            self._rebind_hypotheses.clear()

        distance = chebyshev_distance(current.anchor_cell, target.confirmed_cell)
        if distance > 1:
            self._last_reason = (
                "same track proposed an impossible multi-cell jump; authority denied"
            )
            return False

        # A changed bbox, animation pose, or partial effect can move the derived anchor
        # by one cell. Freeze the main memory and start a clean spatial quarantine.
        self._begin_transition(current, frame)
        target.current_clean_visible = False
        self._scope = PerceptionScope.PREDICTED_CELL_FOCUS
        self._last_reason = (
            f"same-track cell transition quarantined cell={current.anchor_cell} "
            "clean_hits=1"
        )
        return True

    def update(self, observation: CombatStrategyFrame) -> CombatTargetSnapshotV2:
        frame = observation
        self._last_frame_index = frame.frame_index
        self._last_timestamp = frame.timestamp
        self._last_player_cell = frame.player_cell
        if frame.ko:
            self.end_combat()
        if self._phase == CombatPhase.POST_COMBAT:
            return self._snapshot(frame)

        clean = self._clean_candidates(frame)
        if self._target is None:
            self._scope = (
                PerceptionScope.GLOBAL_RECOVERY
                if self._scope == PerceptionScope.GLOBAL_RECOVERY
                else PerceptionScope.GLOBAL_DISCOVERY
            )
            self._update_attention(frame, clean)
            return self._snapshot(frame)

        target = self._target
        self._contaminated_presence(frame)
        if self._same_track_transition(frame, clean):
            return self._snapshot(frame)

        target.current_clean_visible = False
        elapsed = max(0.0, frame.timestamp - target.last_clean_seen_at)
        if elapsed <= self.config.clean_visual_grace_seconds:
            self._scope = PerceptionScope.PREDICTED_CELL_FOCUS
        elif elapsed < self.config.local_recovery_seconds:
            self._scope = PerceptionScope.LOCAL_GRID_RECOVERY
        else:
            self._scope = PerceptionScope.GLOBAL_RECOVERY

        self._update_rebind(frame, clean)
        if self._target is not None and elapsed >= self.config.hard_lost_timeout:
            self._target = None
            self._pending_rebind = None
            self._rebind_hypotheses.clear()
            self._attention = None
            self._scope = PerceptionScope.GLOBAL_RECOVERY
            self._last_reason = "hard clean-visual loss; global recovery re-enabled"
        return self._snapshot(frame)


def register_grid_focus_v2_strategy() -> type[GridFocusV2SpatialStrategy]:
    strategy_module.STRATEGY_TYPES[GridFocusV2SpatialStrategy.name] = (
        GridFocusV2SpatialStrategy
    )
    return GridFocusV2SpatialStrategy


register_grid_focus_v2_strategy()


__all__ = ["GridFocusV2SpatialStrategy", "register_grid_focus_v2_strategy"]
