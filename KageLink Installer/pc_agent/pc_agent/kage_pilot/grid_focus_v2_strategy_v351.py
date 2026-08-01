from __future__ import annotations

import json
import math

from . import combat_strategy_v351 as strategy_module
from .combat_strategy_v351 import (
    AttentionHypothesis,
    CombatPhase,
    CombatStrategyConfig,
    CombatStrategyFrame,
    CombatTargetSnapshotV2,
    GridFocusV2Strategy as _GridFocusV2Base,
    GridObservation,
    GridRebindHypothesis,
    ObservationClass,
    PendingRebind,
    PerceptionScope,
    chebyshev_distance,
    direction_between,
    size_similarity,
)
from .grid_geometry_v351 import current_grid_geometry


class GridFocusV2SpatialStrategy(_GridFocusV2Base):
    """Cell-authoritative target strategy with strong confirmed-track adhesion.

    A clean track first becomes ATTENTION and is confirmed only after coherent spatial
    evidence. Once confirmed, the same visual tracker may preserve presence through a
    short normal melee occlusion without updating cell, direction, appearance, size or
    clean confidence. A different tracker is quarantined by cell and can never inherit
    identity merely because it is close to the player.
    """

    name = "grid_focus_v2"
    _MAX_CONTACT_SUSPENSION_SECONDS = 6.0
    _CONTACT_ACTIVITY_FRESH_SECONDS = 0.45
    _ATTENTION_GAP_SECONDS = 0.75
    _STARVATION_EMIT_FRAMES = 8

    def __init__(self, config: CombatStrategyConfig | None = None) -> None:
        super().__init__(config)
        self._attention_has_nonoverlap_evidence = False
        self._starvation_track_id: int | None = None
        self._starvation_frames = 0
        self._starvation_last_frame = -1
        self._starvation_status: dict[str, object] = {}
        self._same_track_contact_started_at = -1e9

    @staticmethod
    def _step_direction(origin, target) -> tuple[int, int]:
        return (
            max(-1, min(1, int(target[0]) - int(origin[0]))),
            max(-1, min(1, int(target[1]) - int(origin[1]))),
        )

    @staticmethod
    def _appearance_evidence(
        first: tuple[float, ...],
        second: tuple[float, ...],
    ) -> tuple[float, bool]:
        if not first or not second or len(first) != len(second):
            return 0.0, False
        left = [float(value) for value in first]
        right = [float(value) for value in second]
        dot = sum(a * b for a, b in zip(left, right))
        norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
        if norm <= 1e-9:
            return 0.0, False
        return max(0.0, min(1.0, dot / norm)), True

    def end_combat(self) -> None:
        super().end_combat()
        self._starvation_track_id = None
        self._starvation_frames = 0
        self._starvation_status = {}

    def lock_starvation_status(self) -> dict[str, object]:
        return dict(self._starvation_status)

    def _clear_starvation(self) -> None:
        self._starvation_track_id = None
        self._starvation_frames = 0
        self._starvation_last_frame = -1
        self._starvation_status = {}

    def _update_lock_starvation(self, frame: CombatStrategyFrame) -> None:
        if self._target is not None or self._phase == CombatPhase.POST_COMBAT:
            self._clear_starvation()
            return
        plausible = [
            item
            for item in frame.observations
            if item.context_state in {"VISIBLE", "OCCLUDED"}
            and not item.multi_cell
            and item.classification != ObservationClass.CAMERA_OR_SCENE_MOTION.value
            and item.enemy_score >= self.config.minimum_enemy_score
            and chebyshev_distance(frame.player_cell, item.anchor_cell) <= 2
        ]
        candidate = max(
            plausible,
            key=lambda item: (
                bool(item.base_selected),
                bool(item.body_like),
                float(item.enemy_score),
            ),
            default=None,
        )
        if candidate is None:
            self._clear_starvation()
            return
        consecutive = (
            candidate.track_id == self._starvation_track_id
            and frame.frame_index == self._starvation_last_frame + 1
        )
        if consecutive:
            self._starvation_frames += 1
        else:
            self._starvation_track_id = candidate.track_id
            self._starvation_frames = 1
        self._starvation_last_frame = frame.frame_index
        geometry = current_grid_geometry()
        attention_hits = self._attention.clean_hits if self._attention else 0
        status = {
            "visual_track_id": candidate.track_id,
            "consecutive_frames": self._starvation_frames,
            "anchor_cell": list(candidate.anchor_cell),
            "grid_distance": chebyshev_distance(frame.player_cell, candidate.anchor_cell),
            "context_state": candidate.context_state,
            "body_gate_result": (
                "ACCEPTED_CLEAN" if candidate.clean else candidate.classification
            ),
            "attention_hits": attention_hits,
            "combat_target_id": None,
            "cell_size": geometry.cell_size if geometry is not None else None,
            "grid_mode": geometry.mode if geometry is not None else None,
        }
        self._starvation_status = status
        if (
            self._starvation_frames == self._STARVATION_EMIT_FRAMES
            or self._starvation_frames > self._STARVATION_EMIT_FRAMES
            and self._starvation_frames % (self._STARVATION_EMIT_FRAMES * 2) == 0
        ):
            print(
                "DOJO_COMBAT_LOCK_STARVATION "
                + json.dumps(status, sort_keys=True),
                flush=True,
            )

    def _select_attention_candidate(
        self,
        frame: CombatStrategyFrame,
        clean: list[GridObservation],
    ) -> GridObservation | None:
        if not clean:
            return None
        attention = self._attention
        if attention is not None:
            continuing = [
                item
                for item in clean
                if item.track_id in attention.supporting_track_ids
                and chebyshev_distance(attention.cell, item.anchor_cell) <= 1
            ]
            if continuing:
                return max(
                    continuing,
                    key=lambda item: (item.base_selected, item.enemy_score),
                )
        return max(
            clean,
            key=lambda item: (
                item.base_selected,
                -chebyshev_distance(frame.player_cell, item.anchor_cell),
                item.enemy_score,
            ),
        )

    def _update_attention_adherent(
        self,
        frame: CombatStrategyFrame,
        clean: list[GridObservation],
    ) -> None:
        selected = self._select_attention_candidate(frame, clean)
        if selected is None:
            if (
                self._attention is not None
                and frame.timestamp - self._attention.last_seen_at <= self._ATTENTION_GAP_SECONDS
            ):
                self._last_reason = (
                    "ATTENTION preserved through short contaminated/occluded gap; "
                    "identity not created"
                )
            else:
                self._attention = None
                self._attention_has_nonoverlap_evidence = False
                self._last_reason = "no clean acquisition evidence"
            return

        overlap = selected.anchor_cell == frame.player_cell
        attention = self._attention
        same_hypothesis = bool(
            attention is not None
            and (
                selected.track_id in attention.supporting_track_ids
                or chebyshev_distance(attention.cell, selected.anchor_cell) <= 1
            )
        )
        if not same_hypothesis:
            self._attention = AttentionHypothesis(
                cell=selected.anchor_cell,
                clean_hits=0 if overlap else 1,
                first_seen_at=frame.timestamp,
                last_seen_at=frame.timestamp,
                best_score=selected.enemy_score,
                supporting_track_ids={selected.track_id},
                best_observation=selected,
            )
            self._attention_has_nonoverlap_evidence = not overlap
        else:
            assert attention is not None
            attention.cell = selected.anchor_cell
            attention.last_seen_at = frame.timestamp
            attention.supporting_track_ids.add(selected.track_id)
            if selected.enemy_score >= attention.best_score:
                attention.best_score = selected.enemy_score
                attention.best_observation = selected
            if overlap and not self._attention_has_nonoverlap_evidence:
                # A player-only shadow or own effect can remain clean-looking in d=0.
                # It may be observed, but it never accumulates acquisition authority.
                attention.clean_hits = 0
            else:
                if not overlap:
                    self._attention_has_nonoverlap_evidence = True
                attention.clean_hits += 1

        attention = self._attention
        assert attention is not None
        overlap_state = " CONTACT_OVERLAP_HYPOTHESIS" if overlap else ""
        self._last_reason = (
            f"ATTENTION{overlap_state} cell={attention.cell} "
            f"hits={attention.clean_hits}; identity not created"
        )
        if not self._attention_has_nonoverlap_evidence:
            return
        if attention.clean_hits < self.config.attention_confirm_hits:
            return
        chosen = attention.best_observation or selected
        self._new_target(chosen, frame.player_cell)
        self._scope = PerceptionScope.LOCKED_CELL_FOCUS
        self._last_reason = "TARGET_CONFIRMED by coherent clean cell evidence"
        self._clear_starvation()

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
            self._same_track_contact_started_at = -1e9
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

        self._begin_transition(current, frame)
        target.current_clean_visible = False
        self._scope = PerceptionScope.PREDICTED_CELL_FOCUS
        self._last_reason = (
            f"same-track cell transition quarantined cell={current.anchor_cell} "
            "clean_hits=1"
        )
        return True

    def _same_track_contact_presence(self, frame: CombatStrategyFrame) -> bool:
        target = self._target
        if target is None:
            return False
        candidate = next(
            (
                item
                for item in frame.observations
                if item.track_id == target.clean_visual_track_id
                and not item.clean
                and not item.multi_cell
                and item.classification
                != ObservationClass.CAMERA_OR_SCENE_MOTION.value
                and chebyshev_distance(item.anchor_cell, target.confirmed_cell) <= 1
            ),
            None,
        )
        if candidate is None:
            self._same_track_contact_started_at = -1e9
            return False
        clean_elapsed = max(0.0, frame.timestamp - target.last_clean_seen_at)
        if clean_elapsed > self._MAX_CONTACT_SUSPENSION_SECONDS:
            self._last_reason = (
                "same-track contaminated presence exceeded finite suspension; hard loss allowed"
            )
            return False
        if self._same_track_contact_started_at < -1e8:
            self._same_track_contact_started_at = frame.timestamp
        target.current_clean_visible = False
        target.last_any_activity_at = max(target.last_any_activity_at, frame.timestamp)
        target.contamination = candidate.classification
        target.possible_presence_in_locked_cell = True
        self._scope = PerceptionScope.PREDICTED_CELL_FOCUS
        self._last_reason = (
            f"same tracker #{candidate.track_id} preserved as CONTACT_OVERLAP_HYPOTHESIS; "
            "clean memory frozen"
        )
        return True

    def _movement_mode(self, frame: CombatStrategyFrame) -> tuple[str, bool, bool, str]:
        target = self._target
        if target is not None and not target.current_clean_visible:
            activity_age = max(0.0, frame.timestamp - target.last_any_activity_at)
            clean_age = max(0.0, frame.timestamp - target.last_clean_seen_at)
            if (
                target.possible_presence_in_locked_cell
                and activity_age <= self._CONTACT_ACTIVITY_FRESH_SECONDS
                and clean_age <= self._MAX_CONTACT_SUSPENSION_SECONDS
                and chebyshev_distance(frame.player_cell, target.confirmed_cell) <= 1
            ):
                return (
                    "MELEE_HOLD",
                    False,
                    False,
                    "same confirmed tracker has recent contaminated contact presence",
                )
        return super()._movement_mode(frame)

    def _rebind_score(self, target, item: GridObservation) -> float:
        distance = chebyshev_distance(target.confirmed_cell, item.anchor_cell)
        if distance > 1:
            return 0.0
        distance_score = 1.0 if distance == 0 else 0.78
        size_score = size_similarity(target.body_size, item.body_size)
        appearance_score, appearance_available = self._appearance_evidence(
            target.appearance_signature,
            item.appearance_signature,
        )
        weighted = 0.45 * distance_score + 0.25 * size_score
        weights = 0.70
        if appearance_available:
            weighted += 0.30 * appearance_score
            weights += 0.30
        return max(0.0, min(1.0, weighted / max(1e-9, weights)))

    def _update_rebind_spatial(
        self,
        frame: CombatStrategyFrame,
        candidates: list[GridObservation],
    ) -> None:
        target = self._target
        if target is None:
            return
        focused = self._focused_cells(frame)
        eligible = [item for item in candidates if item.anchor_cell in focused]
        for item in candidates:
            if item.anchor_cell not in focused:
                self.metrics.global_candidates_after_lock += 1
        if not eligible:
            pending = self._pending_rebind
            if (
                pending is not None
                and frame.timestamp - pending.hypothesis.last_seen_at > 0.75
            ):
                self._pending_rebind = None
            return

        by_cell: dict[tuple[int, int], list[GridObservation]] = {}
        for item in eligible:
            if chebyshev_distance(target.confirmed_cell, item.anchor_cell) > 1:
                self.metrics.false_rebinds += 1
                continue
            by_cell.setdefault(item.anchor_cell, []).append(item)
        if not by_cell:
            return
        cell, items = max(
            by_cell.items(),
            key=lambda value: max(self._rebind_score(target, item) for item in value[1]),
        )
        best = max(items, key=lambda item: self._rebind_score(target, item))
        score = self._rebind_score(target, best)
        self._best_rebind_score = score
        if score < self.config.minimum_rebind_score:
            return

        hypothesis = self._rebind_hypotheses.get(cell)
        if hypothesis is None or frame.timestamp - hypothesis.last_seen_at > 0.75:
            hypothesis = GridRebindHypothesis(
                candidate_cell=cell,
                first_seen_at=frame.timestamp,
                last_seen_at=frame.timestamp,
            )
            self._rebind_hypotheses[cell] = hypothesis
        hypothesis.clean_hits += 1
        hypothesis.last_seen_at = frame.timestamp
        hypothesis.supporting_track_ids.update(item.track_id for item in items)
        if score >= hypothesis.best_score:
            hypothesis.best_score = score
            hypothesis.best_observation = best
        self._pending_rebind = PendingRebind(
            cell=cell,
            track_id=best.track_id,
            first_observation=hypothesis.best_observation or best,
            hits=hypothesis.clean_hits,
            score=hypothesis.best_score,
            hypothesis=hypothesis,
        )
        self._last_reason = (
            f"rebind quarantined cell={cell} clean_hits={hypothesis.clean_hits}"
        )
        required_hits = 2 if cell == target.confirmed_cell else 3
        if hypothesis.clean_hits < required_hits:
            return
        accepted = hypothesis.best_observation or best
        if chebyshev_distance(target.confirmed_cell, accepted.anchor_cell) > 1:
            self.metrics.false_rebinds += 1
            self._pending_rebind = None
            return
        elapsed = max(0.0, frame.timestamp - hypothesis.first_seen_at)
        self._accept_clean(accepted, frame.player_cell, rebound=True)
        self.metrics.clean_rebinds += 1
        self.metrics.rebind_count += 1
        self.metrics.rebind_time_total += elapsed
        self._pending_rebind = None
        self._rebind_hypotheses.clear()
        self._scope = PerceptionScope.LOCKED_CELL_FOCUS
        self._same_track_contact_started_at = -1e9
        self._last_reason = "spatial rebind confirmed after clean cell quarantine"

    def update(self, observation: CombatStrategyFrame) -> CombatTargetSnapshotV2:
        frame = observation
        self._last_frame_index = frame.frame_index
        self._last_timestamp = frame.timestamp
        self._last_player_cell = frame.player_cell
        if frame.ko:
            self.end_combat()
        if self._phase == CombatPhase.POST_COMBAT:
            self._clear_starvation()
            return self._snapshot(frame)

        clean = self._clean_candidates(frame)
        if self._target is None:
            self._scope = (
                PerceptionScope.GLOBAL_RECOVERY
                if self._scope == PerceptionScope.GLOBAL_RECOVERY
                else PerceptionScope.GLOBAL_DISCOVERY
            )
            self._update_attention_adherent(frame, clean)
            self._update_lock_starvation(frame)
            return self._snapshot(frame)

        self._clear_starvation()
        target = self._target
        self._contaminated_presence(frame)
        if self._same_track_transition(frame, clean):
            return self._snapshot(frame)
        if self._same_track_contact_presence(frame):
            return self._snapshot(frame)

        target.current_clean_visible = False
        elapsed = max(0.0, frame.timestamp - target.last_clean_seen_at)
        if elapsed <= self.config.clean_visual_grace_seconds:
            self._scope = PerceptionScope.PREDICTED_CELL_FOCUS
        elif elapsed < self.config.local_recovery_seconds:
            self._scope = PerceptionScope.LOCAL_GRID_RECOVERY
        else:
            self._scope = PerceptionScope.GLOBAL_RECOVERY

        self._update_rebind_spatial(frame, clean)
        if self._target is not None and elapsed >= self.config.hard_lost_timeout:
            self._target = None
            self._pending_rebind = None
            self._rebind_hypotheses.clear()
            self._attention = None
            self._attention_has_nonoverlap_evidence = False
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
