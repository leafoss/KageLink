from __future__ import annotations

import unittest

from pc_agent.kage_pilot.combat_strategy_v351 import (
    CombatStrategyConfig,
    CombatStrategyFrame,
    GridObservation,
    ObservationClass,
)
from pc_agent.kage_pilot.grid_focus_v2_strategy_v351 import (
    GridFocusV2SpatialStrategy,
)
from pc_agent.kage_pilot.grid_geometry_v351 import GridGeometry, emit_grid_geometry


def clean_observation(
    frame_index: int,
    track_id: int,
    cell: tuple[int, int],
    *,
    score: float = 80.0,
    appearance: tuple[float, ...] = (1.0, 0.0),
    base_selected: bool = False,
) -> GridObservation:
    return GridObservation(
        frame_index=frame_index,
        timestamp=frame_index * 0.1,
        track_id=track_id,
        anchor_cell=cell,
        bbox_cells=frozenset({cell}),
        visible=True,
        body_like=True,
        contaminated=False,
        enemy_score=score,
        appearance_signature=appearance,
        body_size=(28.0, 52.0),
        body_cell_coverage=0.80,
        classification=ObservationClass.CLEAN_SINGLE_CELL_BODY.value,
        context_state="VISIBLE",
        base_selected=base_selected,
    )


def contaminated_observation(
    frame_index: int,
    track_id: int,
    cell: tuple[int, int],
    *,
    score: float = 80.0,
    context_state: str = "OCCLUDED",
    base_selected: bool = True,
) -> GridObservation:
    return GridObservation(
        frame_index=frame_index,
        timestamp=frame_index * 0.1,
        track_id=track_id,
        anchor_cell=cell,
        bbox_cells=frozenset({cell}),
        visible=context_state == "VISIBLE",
        body_like=False,
        contaminated=True,
        enemy_score=score,
        appearance_signature=(),
        body_size=(30.0, 54.0),
        body_cell_coverage=0.72,
        classification=ObservationClass.UNKNOWN_BLOB.value,
        context_state=context_state,
        base_selected=base_selected,
    )


def frame(
    index: int,
    observations,
    *,
    player_cell: tuple[int, int] = (2, 2),
) -> CombatStrategyFrame:
    return CombatStrategyFrame(
        frame_index=index,
        timestamp=index * 0.1,
        player_cell=player_cell,
        observations=tuple(observations),
    )


class LockStarvationTrackerAdhesionV351Tests(unittest.TestCase):
    def setUp(self) -> None:
        emit_grid_geometry(GridGeometry.from_mode("64"))
        self.config = CombatStrategyConfig(
            strategy="grid_focus_v2",
            attention_confirm_hits=2,
            rebind_confirm_hits=2,
            minimum_enemy_score=55.0,
            minimum_rebind_score=0.62,
            clean_visual_grace_seconds=0.20,
            local_recovery_seconds=1.20,
            hard_lost_timeout=3.0,
        )

    def strategy(self) -> GridFocusV2SpatialStrategy:
        return GridFocusV2SpatialStrategy(self.config)

    def confirm_target(
        self,
        strategy: GridFocusV2SpatialStrategy,
        *,
        track_id: int = 12,
        cell: tuple[int, int] = (3, 2),
    ):
        first = strategy.update(frame(1, [clean_observation(1, track_id, cell)]))
        second = strategy.update(frame(2, [clean_observation(2, track_id, cell)]))
        self.assertEqual(first.target_state, "ATTENTION")
        self.assertIsNotNone(second.combat_target_id)
        return second

    def test_player_only_d0_never_creates_target(self):
        strategy = self.strategy()
        for index in range(1, 8):
            snapshot = strategy.update(
                frame(index, [clean_observation(index, 1, (2, 2), base_selected=True)])
            )
        self.assertIsNone(snapshot.combat_target_id)
        self.assertEqual(snapshot.target_state, "ATTENTION")
        self.assertEqual(snapshot.attention_hits, 0)
        self.assertFalse(snapshot.movement_authority)
        self.assertFalse(snapshot.attack_authority)

    def test_clean_attention_can_continue_into_d0_before_lock(self):
        strategy = self.strategy()
        first = strategy.update(frame(1, [clean_observation(1, 12, (3, 2))]))
        second = strategy.update(frame(2, [clean_observation(2, 12, (2, 2))]))
        self.assertEqual(first.target_state, "ATTENTION")
        self.assertIsNotNone(second.combat_target_id)
        self.assertEqual(second.confirmed_target_cell, (2, 2))

    def test_rejected_primary_does_not_hide_valid_secondary(self):
        strategy = self.strategy()
        primary = contaminated_observation(
            1,
            90,
            (2, 2),
            context_state="OCCLUDED",
            base_selected=True,
        )
        secondary = clean_observation(1, 12, (3, 2), base_selected=False)
        first = strategy.update(frame(1, [primary, secondary]))
        second = strategy.update(
            frame(
                2,
                [
                    contaminated_observation(2, 90, (2, 2)),
                    clean_observation(2, 12, (3, 2)),
                ],
            )
        )
        self.assertEqual(first.attention_cell, (3, 2))
        self.assertIsNotNone(second.combat_target_id)
        self.assertEqual(second.current_visual_track_id, 12)

    def test_same_tracker_short_occlusion_preserves_logical_target(self):
        strategy = self.strategy()
        locked = self.confirm_target(strategy)
        logical_id = locked.combat_target_id
        target = strategy._target
        self.assertIsNotNone(target)
        clean_seen = target.last_clean_seen_at
        confirmed_cell = target.confirmed_cell
        direction = target.last_confirmed_direction
        confidence = target.confidence

        occluded = strategy.update(
            frame(3, [contaminated_observation(3, 12, confirmed_cell)])
        )

        self.assertEqual(occluded.combat_target_id, logical_id)
        self.assertEqual(occluded.confirmed_target_cell, confirmed_cell)
        self.assertEqual(occluded.movement_mode, "MELEE_HOLD")
        self.assertFalse(occluded.movement_authority)
        self.assertFalse(occluded.attack_authority)
        self.assertEqual(strategy._target.last_clean_seen_at, clean_seen)
        self.assertEqual(strategy._target.last_confirmed_direction, direction)
        self.assertEqual(strategy._target.confidence, confidence)

        visible_again = strategy.update(
            frame(4, [clean_observation(4, 12, confirmed_cell)])
        )
        self.assertEqual(visible_again.combat_target_id, logical_id)
        self.assertEqual(visible_again.current_visual_track_id, 12)

    def test_same_track_impossible_jump_keeps_prior_clean_authority(self):
        strategy = self.strategy()
        locked = self.confirm_target(strategy)
        logical_id = locked.combat_target_id
        jumped = strategy.update(frame(3, [clean_observation(3, 12, (7, 2))]))
        self.assertEqual(jumped.combat_target_id, logical_id)
        self.assertEqual(jumped.confirmed_target_cell, (3, 2))
        # The impossible observation is rejected; the last clean tracker remains the
        # logical identity, but it has no current visual movement/attack authority.
        self.assertEqual(jumped.current_visual_track_id, 12)
        self.assertFalse(jumped.movement_authority)
        self.assertFalse(jumped.attack_authority)
        self.assertIn("impossible multi-cell jump", jumped.reason)

    def test_new_track_same_cell_is_quarantined_for_two_hits(self):
        strategy = self.strategy()
        locked = self.confirm_target(strategy)
        logical_id = locked.combat_target_id
        first = strategy.update(frame(3, [clean_observation(3, 44, (3, 2))]))
        self.assertEqual(first.combat_target_id, logical_id)
        self.assertEqual(first.pending_rebind_cell, (3, 2))
        self.assertEqual(first.pending_rebind_hits, 1)
        self.assertEqual(first.last_contact_direction, locked.last_contact_direction)
        self.assertFalse(first.movement_authority)
        second = strategy.update(frame(4, [clean_observation(4, 44, (3, 2))]))
        self.assertEqual(second.combat_target_id, logical_id)
        self.assertEqual(second.current_visual_track_id, 44)

    def test_new_track_adjacent_cell_requires_three_hits(self):
        strategy = self.strategy()
        locked = self.confirm_target(strategy)
        logical_id = locked.combat_target_id
        first = strategy.update(frame(3, [clean_observation(3, 55, (4, 2))]))
        second = strategy.update(frame(4, [clean_observation(4, 55, (4, 2))]))
        self.assertEqual(first.pending_rebind_hits, 1)
        self.assertEqual(second.pending_rebind_hits, 2)
        self.assertEqual(second.confirmed_target_cell, (3, 2))
        third = strategy.update(frame(5, [clean_observation(5, 55, (4, 2))]))
        self.assertEqual(third.combat_target_id, logical_id)
        self.assertEqual(third.confirmed_target_cell, (4, 2))
        self.assertEqual(third.current_visual_track_id, 55)

    def test_missing_appearance_is_renormalized_without_bonus(self):
        strategy = self.strategy()
        self.confirm_target(strategy)
        target = strategy._target
        self.assertIsNotNone(target)
        target.appearance_signature = ()
        candidate = clean_observation(3, 88, target.confirmed_cell, appearance=())
        score = strategy._rebind_score(target, candidate)
        self.assertGreaterEqual(score, self.config.minimum_rebind_score)
        self.assertLessEqual(score, 1.0)

    def test_lock_starvation_watchdog_reports_persistent_visual_tracker(self):
        strategy = self.strategy()
        for index in range(1, 9):
            snapshot = strategy.update(
                frame(
                    index,
                    [
                        contaminated_observation(
                            index,
                            12,
                            (3, 2),
                            context_state="VISIBLE",
                            base_selected=True,
                        )
                    ],
                )
            )
        status = strategy.lock_starvation_status()
        self.assertIsNone(snapshot.combat_target_id)
        self.assertEqual(status["visual_track_id"], 12)
        self.assertEqual(status["consecutive_frames"], 8)
        self.assertEqual(status["cell_size"], 64)
        self.assertEqual(status["grid_mode"], "64")


if __name__ == "__main__":
    unittest.main()
