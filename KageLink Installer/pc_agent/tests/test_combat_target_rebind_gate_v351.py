from __future__ import annotations

from types import SimpleNamespace
import unittest

from pc_agent.kage_pilot.combat_target_config_v351 import CombatTargetConfig
from pc_agent.kage_pilot.combat_target_memory_v351 import PersistentCombatTargetMemory
from pc_agent.kage_pilot.combat_target_model_v351 import CombatTargetState


class _Track:
    def __init__(self, track_id: int, *, bbox, score: float = 80.0) -> None:
        self.track_id = track_id
        self.bbox = bbox
        x, y, width, height = bbox
        self.center = (x + width / 2.0, y + height / 2.0)
        self.residual_velocity = (0.0, 0.0)
        self.enemy_score = score


class _Tracker:
    def __init__(self, contexts) -> None:
        self.contexts = contexts

    def context_for(self, track_id):
        return self.contexts[track_id]


class _Observer:
    def __init__(self, metrics) -> None:
        self.metrics = metrics

    def metrics_for(self, track_id):
        return self.metrics.get(track_id)


class CombatTargetRebindGateV351Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = CombatTargetConfig(
            local_rebind_radius=56.0,
            minimum_rebind_score=0.48,
            contact_hold_seconds=0.5,
            local_rebind_seconds=0.7,
            hard_lost_timeout=1.5,
            structured_logging_enabled=False,
        )
        self.player = (100.0, 100.0)

    @staticmethod
    def context(*, appearance=(), state="VISIBLE"):
        return SimpleNamespace(appearance=appearance, state=state)

    @staticmethod
    def metrics(distance=1):
        return SimpleNamespace(grid_distance=distance)

    def acquired_memory(self) -> PersistentCombatTargetMemory:
        memory = PersistentCombatTargetMemory(self.config)
        memory.acquire(
            _Track(1, bbox=(120, 60, 30, 50)),
            self.context(appearance=(1.0, 0.0)),
            self.metrics(1),
            player_center=self.player,
            now=1.0,
            frame_index=1,
        )
        memory.mark_missing(now=1.4, frame_index=4)
        return memory

    def test_candidate_near_player_but_far_from_prediction_is_rejected(self):
        memory = self.acquired_memory()
        # Feet at roughly (75,100): only 25px from PLAYER but over 60px from the
        # target feet near (135,105). This is the exact OR-gate regression.
        spurious = _Track(9, bbox=(60, 50, 30, 55), score=99.0)
        tracker = _Tracker({9: self.context()})
        observer = _Observer({9: self.metrics(1)})

        selected, score = memory.choose_local_rebind(
            [spurious],
            tracker=tracker,
            observer=observer,
            player_center=self.player,
        )

        self.assertIsNone(selected)
        self.assertEqual(score, 0.0)
        self.assertEqual(memory.combat_target_id, 1)

    def test_candidate_near_prediction_can_enter_fallback_selection(self):
        memory = self.acquired_memory()
        candidate = _Track(7, bbox=(123, 58, 30, 52))
        tracker = _Tracker({7: self.context(appearance=(1.0, 0.0))})
        observer = _Observer({7: self.metrics(1)})

        selected, score = memory.choose_local_rebind(
            [candidate],
            tracker=tracker,
            observer=observer,
            player_center=self.player,
        )

        self.assertIs(selected, candidate)
        self.assertGreaterEqual(score, self.config.minimum_rebind_score)

    def test_player_center_is_fallback_only_without_target_position(self):
        memory = PersistentCombatTargetMemory(self.config)
        near_player = _Track(4, bbox=(90, 48, 24, 54))
        tracker = _Tracker({4: self.context()})
        observer = _Observer({4: self.metrics(1)})

        selected, _score = memory.choose_local_rebind(
            [near_player],
            tracker=tracker,
            observer=observer,
            player_center=self.player,
        )

        self.assertIs(selected, near_player)

    def test_missing_appearance_and_movement_give_no_artificial_bonus(self):
        memory = self.acquired_memory()
        memory._appearance = ()
        memory._last_direction = "-"
        candidate = _Track(5, bbox=(123, 58, 30, 52))

        appearance_score, appearance_available = memory._appearance_evidence(self.context())
        movement_score, movement_available = memory._movement_evidence(
            memory._track_position(candidate),
            self.player,
        )

        self.assertEqual(appearance_score, 0.0)
        self.assertFalse(appearance_available)
        self.assertEqual(movement_score, 0.0)
        self.assertFalse(movement_available)
        # Renormalization preserves a good spatial/size match instead of using fake
        # evidence or making the maximum reachable score artificially too low.
        score = memory.rebind_score(
            candidate,
            self.context(),
            self.metrics(1),
            player_center=self.player,
        )
        self.assertGreaterEqual(score, self.config.minimum_rebind_score)

    def test_spurious_candidate_does_not_renew_timeout(self):
        memory = self.acquired_memory()
        last_seen = memory._last_seen_at
        spurious = _Track(9, bbox=(60, 50, 30, 55), score=99.0)
        tracker = _Tracker({9: self.context()})
        observer = _Observer({9: self.metrics(1)})
        selected, _score = memory.choose_local_rebind(
            [spurious],
            tracker=tracker,
            observer=observer,
            player_center=self.player,
        )
        self.assertIsNone(selected)
        self.assertEqual(memory._last_seen_at, last_seen)

    def test_lost_clears_prediction_and_movement_authority(self):
        memory = self.acquired_memory()
        memory.mark_missing(now=4.0, frame_index=20)
        snapshot = memory.snapshot(now=4.0, frame_index=20)
        self.assertEqual(memory.state, CombatTargetState.LOST)
        self.assertIsNone(snapshot.predicted_position)
        self.assertEqual(snapshot.movement_mode, "NONE")
        self.assertEqual(snapshot.last_contact_direction, "-")


if __name__ == "__main__":
    unittest.main()
