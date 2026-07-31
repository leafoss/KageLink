from __future__ import annotations

from . import combat_strategy_v351 as strategy_module
from .combat_strategy_v351 import (
    CombatPhase,
    CombatStrategyConfig,
    CombatStrategyFrame,
    CombatTargetSnapshotV2,
    GridFocusV2Strategy as _GridFocusV2Base,
    PerceptionScope,
    chebyshev_distance,
)


class GridFocusV2SpatialStrategy(_GridFocusV2Base):
    """Canonical experimental strategy whose identity follows a spatial cell.

    This concrete implementation deliberately lives in its own strategy module. It is
    registered through the explicit strategy registry; it is not a runtime monkeypatch
    or another hardening bridge. A clean visual track may move the confirmed target by
    one adjacent cell in the same frame. Larger jumps remain quarantined/rejected.
    """

    name = "grid_focus_v2"

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

        # Same visual body is allowed to advance only to one neighbouring cell. This
        # is the missing transition that previously froze the confirmed cell when an
        # enemy crossed the player. An impossible same-track jump receives no special
        # authority and must pass through spatial rebind quarantine instead.
        current = next(
            (
                item
                for item in clean
                if item.track_id == target.clean_visual_track_id
                and chebyshev_distance(item.anchor_cell, target.confirmed_cell) <= 1
            ),
            None,
        )
        if current is not None:
            self._accept_clean(current, frame.player_cell, rebound=False)
            self._pending_rebind = None
            self._rebind_hypotheses.clear()
            self._scope = PerceptionScope.LOCKED_CELL_FOCUS
            self._last_reason = "clean body advanced within one physically plausible cell"
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
