from __future__ import annotations

import unittest

from pc_agent.kage_pilot.combat_strategy_v351 import (
    AttackVisualContext,
    CombatStrategyConfig,
    ObservationClass,
    adjacent,
    create_combat_target_strategy,
)
from pc_agent.kage_pilot.grid_focus_v2_strategy_v351 import (
    GridFocusV2SpatialStrategy,
)
from pc_agent.kage_pilot.combat_lab.scenarios import frame, observation


class CombatStrategyV351Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = GridFocusV2SpatialStrategy(
            CombatStrategyConfig(
                strategy="grid_focus_v2",
                attention_confirm_hits=2,
                rebind_confirm_hits=2,
                clean_visual_grace_seconds=0.2,
                local_recovery_seconds=1.2,
                hard_lost_timeout=3.0,
                minimum_enemy_score=55.0,
                minimum_rebind_score=0.62,
                direction_confirm_hits=2,
            )
        )

    def acquire(self, track_id=1, cell=(1, 0)):
        first = self.strategy.update(frame(0, (0, 0), observation(0, track_id, cell)))
        second = self.strategy.update(frame(1, (0, 0), observation(1, track_id, cell)))
        self.assertEqual(first.target_state, "ATTENTION")
        self.assertIsNotNone(second.combat_target_id)
        return second

    def test_01_weak_candidate_enters_attention_not_target(self):
        result = self.strategy.update(frame(0, (0, 0), observation(0, 1, (1, 0))))
        self.assertEqual(result.target_state, "ATTENTION")
        self.assertIsNone(result.combat_target_id)

    def test_02_occluded_observation_does_not_create_target(self):
        item = observation(
            0,
            1,
            (1, 0),
            visible=False,
            contaminated=True,
            classification=ObservationClass.UNKNOWN_BLOB.value,
        )
        result = self.strategy.update(frame(0, (0, 0), item))
        self.assertIsNone(result.combat_target_id)

    def test_03_contaminated_observation_does_not_create_target(self):
        item = observation(
            0,
            1,
            (1, 0),
            contaminated=True,
            classification=ObservationClass.TARGET_EFFECT_CONTAMINATED.value,
        )
        result = self.strategy.update(frame(0, (0, 0), item))
        self.assertIsNone(result.combat_target_id)

    def test_04_multi_cell_blob_does_not_create_target(self):
        item = observation(
            0,
            1,
            (1, 0),
            contaminated=True,
            classification=ObservationClass.MULTI_CELL_EFFECT.value,
            bbox_cells={(0, 0), (1, 0), (2, 0)},
        )
        self.strategy.update(frame(0, (0, 0), item))
        result = self.strategy.update(frame(1, (0, 0), item))
        self.assertIsNone(result.combat_target_id)
        self.assertEqual(result.confidence, 0.0)

    def test_05_multi_cell_blob_does_not_rebind(self):
        acquired = self.acquire()
        blob = observation(
            2,
            9,
            (1, 0),
            contaminated=True,
            classification=ObservationClass.MULTI_CELL_EFFECT.value,
            bbox_cells={(0, 0), (1, 0), (2, 0)},
            score=99.0,
        )
        result = self.strategy.update(frame(2, (0, 0), blob))
        self.assertEqual(result.combat_target_id, acquired.combat_target_id)
        self.assertIsNone(result.current_visual_track_id)
        self.assertIsNone(result.pending_rebind_cell)

    def test_06_multi_cell_blob_does_not_renew_clean_timeout(self):
        self.acquire()
        clean_seen = self.strategy._target.last_clean_seen_at
        blob = observation(
            2,
            9,
            (1, 0),
            timestamp=0.8,
            contaminated=True,
            classification=ObservationClass.MULTI_CELL_EFFECT.value,
            bbox_cells={(0, 0), (1, 0), (2, 0)},
        )
        self.strategy.update(frame(2, (0, 0), blob, timestamp=0.8))
        self.assertEqual(self.strategy._target.last_clean_seen_at, clean_seen)
        self.assertGreater(self.strategy._target.last_any_activity_at, clean_seen)

    def test_07_different_tracks_same_cell_feed_one_hypothesis(self):
        target = self.acquire(track_id=10)
        first = self.strategy.update(frame(2, (0, 0), observation(2, 11, (1, 0))))
        self.assertEqual(first.pending_rebind_hits, 1)
        second = self.strategy.update(frame(3, (0, 0), observation(3, 12, (1, 0))))
        self.assertEqual(second.combat_target_id, target.combat_target_id)
        self.assertEqual(second.current_visual_track_id, 12)

    def test_08_different_track_impossible_cell_is_rejected(self):
        target = self.acquire(track_id=10)
        self.strategy.update(frame(2, (0, 0), observation(2, 99, (5, 5), score=99)))
        result = self.strategy.update(frame(3, (0, 0), observation(3, 99, (5, 5), score=99)))
        self.assertEqual(result.combat_target_id, target.combat_target_id)
        self.assertEqual(result.confirmed_target_cell, (1, 0))
        self.assertNotEqual(result.current_visual_track_id, 99)

    def test_09_pending_rebind_does_not_change_main_memory(self):
        target = self.acquire(track_id=10)
        candidate = observation(2, 11, (0, 1), timestamp=0.5)
        result = self.strategy.update(
            frame(2, (0, 0), candidate, timestamp=0.5)
        )
        self.assertEqual(result.combat_target_id, target.combat_target_id)
        self.assertEqual(result.confirmed_target_cell, (1, 0))
        self.assertEqual(result.pending_rebind_cell, (0, 1))
        self.assertEqual(result.pending_rebind_hits, 1)

    def test_10_rebind_requires_clean_observations(self):
        self.acquire(track_id=10)
        dirty = observation(
            2,
            11,
            (1, 0),
            contaminated=True,
            classification=ObservationClass.UNKNOWN_BLOB.value,
        )
        first = self.strategy.update(frame(2, (0, 0), dirty))
        second = self.strategy.update(frame(3, (0, 0), dirty))
        self.assertIsNone(first.pending_rebind_cell)
        self.assertIsNone(second.current_visual_track_id)

    def test_11_confirmed_rebind_preserves_combat_target_id(self):
        target = self.acquire(track_id=10)
        self.strategy.update(frame(2, (0, 0), observation(2, 11, (1, 0))))
        result = self.strategy.update(frame(3, (0, 0), observation(3, 11, (1, 0))))
        self.assertEqual(result.combat_target_id, target.combat_target_id)
        self.assertEqual(result.current_visual_track_id, 11)

    def test_12_rebind_does_not_jump_prediction_multiple_cells(self):
        self.acquire(track_id=10)
        first = observation(2, 11, (1, 1), timestamp=0.5)
        second = observation(3, 11, (1, 1), timestamp=0.6)
        self.strategy.update(frame(2, (0, 0), first, timestamp=0.5))
        result = self.strategy.update(frame(3, (0, 0), second, timestamp=0.6))
        self.assertTrue(adjacent(result.confirmed_target_cell, result.predicted_target_cell))

    def test_13_pending_rebind_does_not_change_direction(self):
        acquired = self.acquire(track_id=10, cell=(1, 0))
        candidate = observation(2, 11, (0, 1), timestamp=0.5)
        result = self.strategy.update(frame(2, (0, 0), candidate, timestamp=0.5))
        self.assertEqual(result.last_contact_direction, acquired.last_contact_direction)

    def test_14_diagonal_is_adjacent(self):
        for cell in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
            self.assertTrue(adjacent((0, 0), cell))

    def test_15_distant_candidates_do_not_compete_after_lock(self):
        self.acquire(track_id=10)
        self.strategy.update(frame(2, (0, 0), observation(2, 99, (5, 5), score=100)))
        result = self.strategy.update(frame(3, (0, 0), observation(3, 10, (1, 0))))
        self.assertEqual(result.current_visual_track_id, 10)
        self.assertEqual(result.confirmed_target_cell, (1, 0))

    def test_16_lock_uses_focused_perception_scope(self):
        result = self.acquire()
        self.assertEqual(result.perception_scope, "LOCKED_CELL_FOCUS")

    def test_17_loss_expands_to_local_grid_recovery(self):
        self.acquire()
        result = self.strategy.update(frame(2, (0, 0), timestamp=0.5))
        self.assertEqual(result.perception_scope, "LOCAL_GRID_RECOVERY")
        self.assertFalse(result.movement_authority)

    def test_18_global_recovery_waits_for_local_timeout(self):
        self.acquire()
        local = self.strategy.update(frame(2, (0, 0), timestamp=1.0))
        global_result = self.strategy.update(frame(3, (0, 0), timestamp=1.5))
        self.assertEqual(local.perception_scope, "LOCAL_GRID_RECOVERY")
        self.assertEqual(global_result.perception_scope, "GLOBAL_RECOVERY")

    def test_19_melee_lock_expires_without_clean_visual(self):
        acquired = self.acquire(cell=(1, 0))
        self.assertEqual(acquired.movement_mode, "MELEE_LOCK")
        result = self.strategy.update(frame(2, (0, 0), timestamp=0.5))
        self.assertNotEqual(result.movement_mode, "MELEE_LOCK")
        self.assertFalse(result.attack_authority)

    def test_20_own_attack_effect_does_not_create_identity(self):
        context = AttackVisualContext(
            attack_id=1,
            started_at=0.0,
            origin_cell=(0, 0),
            direction="RIGHT",
            expected_cells=frozenset({(1, 0), (2, 0)}),
            expires_at=1.0,
        )
        first = self.strategy.update(
            frame(0, (0, 0), observation(0, 1, (1, 0)), attack=context)
        )
        second = self.strategy.update(
            frame(1, (0, 0), observation(1, 1, (1, 0)), attack=context)
        )
        self.assertIsNone(first.combat_target_id)
        self.assertIsNone(second.combat_target_id)

    def test_21_motion_burst_suppresses_new_identity(self):
        item = observation(0, 1, (1, 0), motion_burst=True)
        self.strategy.update(frame(0, (0, 0), item, motion_burst=True))
        result = self.strategy.update(frame(1, (0, 0), item, motion_burst=True))
        self.assertIsNone(result.combat_target_id)

    def test_22_ko_disables_combat(self):
        self.acquire()
        result = self.strategy.update(frame(2, (0, 0), ko=True))
        self.assertEqual(result.combat_phase, "POST_COMBAT")
        self.assertEqual(result.perception_scope, "COMBAT_DISABLED")
        self.assertFalse(result.active)

    def test_23_no_target_can_appear_after_ko(self):
        self.acquire()
        self.strategy.update(frame(2, (0, 0), ko=True))
        self.strategy.update(frame(3, (0, 0), observation(3, 99, (1, 0), score=100)))
        result = self.strategy.update(frame(4, (0, 0), observation(4, 99, (1, 0), score=100)))
        self.assertIsNone(result.combat_target_id)
        self.assertFalse(result.track_creation_enabled)

    def test_24_strategy_fallback_is_selectable(self):
        for name in ("legacy_safe", "persistent_hardened", "grid_focus_v2"):
            self.assertEqual(create_combat_target_strategy(name).name, name)

    def test_25_unknown_strategy_falls_back_to_persistent_hardened(self):
        self.assertEqual(create_combat_target_strategy("unknown").name, "persistent_hardened")

    def test_26_attention_does_not_authorize_h(self):
        result = self.strategy.update(frame(0, (0, 0), observation(0, 1, (1, 0))))
        self.assertFalse(result.attack_authority)
        self.assertFalse(result.movement_authority)

    def test_27_contamination_never_raises_confidence(self):
        acquired = self.acquire()
        confidence = acquired.confidence
        dirty = observation(
            2,
            9,
            (1, 0),
            contaminated=True,
            classification=ObservationClass.TARGET_EFFECT_CONTAMINATED.value,
            score=100,
        )
        result = self.strategy.update(frame(2, (0, 0), dirty))
        self.assertLessEqual(result.confidence, confidence)

    def test_28_hard_loss_returns_to_global_recovery(self):
        self.acquire()
        result = self.strategy.update(frame(2, (0, 0), timestamp=3.5))
        self.assertIsNone(result.combat_target_id)
        self.assertEqual(result.perception_scope, "GLOBAL_RECOVERY")


if __name__ == "__main__":
    unittest.main()
