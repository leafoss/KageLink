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
    predicted_neighbor,
)


class GridFocusV2SpatialStrategy(_GridFocusV2Base):
    """Canonical experimental strategy whose identity follows a spatial cell.

    This concrete implementation is registered through the explicit strategy registry;
    it is not a runtime monkeypatch or another hardening bridge. Even the current visual
    track cannot move the confirmed identity to a different cell after one frame. A
    clean adjacent transition is quarantined until two coherent observations agree.
    """

    name = "grid_focus_v2"

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
            self._pending_rebind = None
            self._rebind_hypotheses.clear()
            self._scope = PerceptionScope.LOCKED_CELL_FOCUS
            self._last_reason = "clean body remains in confirmed cell"
            return True
        if distance > 1:
            self._last_reason = (
                "same track proposed an impossible multi-cell jump; authority denied"
            )
            return False

        # A changed bbox, animation pose or partial effect can move the derived anchor
        # by one cell. Keep the main memory frozen until the same candidate cell has two
        # clean hits. The pending cell and direction are diagnostic only.
        hypothesis = self._rebind_hypotheses.get(current.anchor_cell)
        if hypothesis is None or frame.timestamp - hypothesis.last_seen_at > 0.75:
            hypothesis = GridRebindHypothesis(
                candidate_cell=current.anchor_cell,
                first_seen_at=frame.timestamp,
                last_seen_at=frame.timestamp,
            )
            self._rebind_hypotheses.clear()
            self._rebind_hypotheses[current.anchor_cell] = hypothesis
        hypothesis.clean_hits += 1
        hypothesis.last_seen_at = frame.timestamp
        hypothesis.supporting_track_ids.add(current.track_id)
        hypothesis.best_score = max(hypothesis.best_score, current.enemy_score)
        hypothesis.best_observation = current
        self._pending_rebind = PendingRebind(
            cell=current.anchor_cell,
            track_id=current.track_id,
            first_observation=current,
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
        if hypothesis.clean_hits < self.config.rebind_confirm_hits:
            return True

        self._accept_clean(current, frame.player_cell, rebound=False)
        confirmed_direction = direction_between(
            frame.player_cell,
            current.anchor_cell,
            target.last_confirmed_direction,
        )
        target.last_confirmed_direction = confirmed_direction
        target.pending_direction = "-"
        target.pending_direction_hits = 0
        target.predicted_cell = predicted_neighbor(
            current.anchor_cell,
            confirmed_direction,
        )
        self._pending_rebind = None
        self._rebind_hypotheses.clear()
        self._scope = PerceptionScope.LOCKED_CELL_FOCUS
        self._last_reason = "same-track spatial transition confirmed after quarantine"
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
