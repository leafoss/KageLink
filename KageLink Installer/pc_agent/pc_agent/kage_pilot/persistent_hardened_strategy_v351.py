from __future__ import annotations

import math

from . import combat_strategy_v351 as strategy_module
from .combat_strategy_v351 import (
    CombatPhase,
    CombatStrategyConfig,
    CombatStrategyFrame,
    CombatTargetSnapshotV2,
    GridRebindHypothesis,
    PendingRebind,
    PerceptionScope,
    PersistentHardenedStrategy as _PersistentBase,
    chebyshev_distance,
    size_similarity,
)


class PersistentHardenedEvidenceStrategy(_PersistentBase):
    """Fail-closed fallback with evidence-aware rebind scoring.

    The strategy intentionally keeps the older track-oriented policy available for
    comparison. The only semantic correction here is that an unavailable appearance
    vector contributes zero evidence and is removed from the score denominator.
    """

    name = "persistent_hardened"

    @staticmethod
    def _appearance_evidence(first, second) -> tuple[float, bool]:
        if not first or not second or len(first) != len(second):
            return 0.0, False
        left = [float(value) for value in first]
        right = [float(value) for value in second]
        dot = sum(a * b for a, b in zip(left, right))
        norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
        if norm <= 1e-9:
            return 0.0, False
        return max(0.0, min(1.0, dot / norm)), True

    def _score(self, target, selected) -> float:
        distance = chebyshev_distance(target.predicted_cell, selected.anchor_cell)
        if distance > 1:
            return 0.0
        distance_score = 1.0 if distance == 0 else 0.75
        size_score = size_similarity(target.body_size, selected.body_size)
        appearance_score, appearance_available = self._appearance_evidence(
            target.appearance_signature,
            selected.appearance_signature,
        )
        weighted = 0.50 * distance_score + 0.25 * size_score
        weights = 0.75
        if appearance_available:
            weighted += 0.25 * appearance_score
            weights += 0.25
        return max(0.0, min(1.0, weighted / max(1e-9, weights)))

    def update(self, observation: CombatStrategyFrame) -> CombatTargetSnapshotV2:
        frame = observation
        self._last_frame_index = frame.frame_index
        self._last_timestamp = frame.timestamp
        self._last_player_cell = frame.player_cell
        if frame.ko:
            self.end_combat()
        if self._phase == CombatPhase.POST_COMBAT:
            return self._snapshot(frame)

        clean = [
            item
            for item in frame.observations
            if item.clean and item.enemy_score >= self.config.minimum_enemy_score
        ]
        if self._target is None:
            selected = max(clean, key=lambda item: item.enemy_score, default=None)
            if selected is not None:
                self._new_target(selected, frame.player_cell)
                self._scope = PerceptionScope.LOCKED_CELL_FOCUS
                self._last_reason = "hardened immediate clean acquisition"
            return self._snapshot(frame)

        target = self._target
        current = next(
            (
                item
                for item in clean
                if item.track_id == target.clean_visual_track_id
            ),
            None,
        )
        if current is not None:
            self._accept_clean(current, frame.player_cell, rebound=False)
            self._pending_track_id = None
            self._pending_track_hits = 0
            self._scope = PerceptionScope.LOCKED_CELL_FOCUS
            self._last_reason = "hardened current visible track"
            return self._snapshot(frame)

        target.current_clean_visible = False
        nearby = [
            item
            for item in clean
            if chebyshev_distance(item.anchor_cell, target.predicted_cell) <= 1
        ]
        selected = max(nearby, key=lambda item: item.enemy_score, default=None)
        if selected is not None:
            score = self._score(target, selected)
            self._best_rebind_score = score
            if score >= self.config.minimum_rebind_score:
                if selected.track_id == self._pending_track_id:
                    self._pending_track_hits += 1
                else:
                    self._pending_track_id = selected.track_id
                    self._pending_track_hits = 1
                    self._pending_started_at = frame.timestamp
                hypothesis = GridRebindHypothesis(
                    candidate_cell=selected.anchor_cell,
                    supporting_track_ids={selected.track_id},
                    clean_hits=self._pending_track_hits,
                    first_seen_at=self._pending_started_at,
                    last_seen_at=frame.timestamp,
                    best_score=score,
                    best_observation=selected,
                )
                self._pending_rebind = PendingRebind(
                    cell=selected.anchor_cell,
                    track_id=selected.track_id,
                    first_observation=selected,
                    hits=self._pending_track_hits,
                    score=score,
                    hypothesis=hypothesis,
                )
                if self._pending_track_hits >= self.config.rebind_confirm_hits:
                    elapsed = max(0.0, frame.timestamp - self._pending_started_at)
                    self._accept_clean(selected, frame.player_cell, rebound=True)
                    self.metrics.clean_rebinds += 1
                    self.metrics.rebind_count += 1
                    self.metrics.rebind_time_total += elapsed
                    self._pending_rebind = None
                    self._pending_track_id = None
                    self._pending_track_hits = 0
                    self._last_reason = "evidence-aware hardened rebind confirmed"
        elapsed = frame.timestamp - target.last_clean_seen_at
        self._scope = (
            PerceptionScope.LOCAL_GRID_RECOVERY
            if elapsed < self.config.local_recovery_seconds
            else PerceptionScope.GLOBAL_RECOVERY
        )
        if elapsed >= self.config.hard_lost_timeout:
            self._target = None
            self._pending_rebind = None
            self._last_reason = "hardened target hard-lost"
        return self._snapshot(frame)


def register_persistent_hardened_strategy() -> type[PersistentHardenedEvidenceStrategy]:
    strategy_module.STRATEGY_TYPES[PersistentHardenedEvidenceStrategy.name] = (
        PersistentHardenedEvidenceStrategy
    )
    return PersistentHardenedEvidenceStrategy


register_persistent_hardened_strategy()


__all__ = [
    "PersistentHardenedEvidenceStrategy",
    "register_persistent_hardened_strategy",
]
