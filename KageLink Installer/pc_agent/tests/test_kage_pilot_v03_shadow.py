from __future__ import annotations

import unittest
from types import SimpleNamespace

from pc_agent.kage_pilot.shadow_combat_v03 import ShadowCombatDecisionEngine


class FakeObserver:
    def __init__(self, metrics, mode="VISIBLE"):
        self._metrics = metrics
        self.target_mode = mode

    def metrics_for(self, track_id):
        del track_id
        return self._metrics


class FakeTracker:
    def __init__(self, state="VISIBLE", side="RIGHT"):
        self.context = SimpleNamespace(
            state=state,
            relative_side=side,
            last_visible_side=side,
        )

    def context_for(self, track_id):
        del track_id
        return self.context


def state_with_target(*, track_id=7, score=80.0):
    target = SimpleNamespace(track_id=track_id, enemy_score=score)
    return SimpleNamespace(target=target)


class ShadowCombatV03Tests(unittest.TestCase):
    def test_no_target_is_search_and_does_not_enable_r(self):
        engine = ShadowCombatDecisionEngine()
        decision = engine.decide(
            SimpleNamespace(target=None),
            FakeObserver(None),
            FakeTracker(),
            now=1.0,
        )
        self.assertEqual(decision.mode, "SEARCH")
        self.assertEqual(decision.navigation, "HOLD")
        self.assertFalse(decision.base_r)
        self.assertFalse(decision.h_opportunity)

    def test_distant_target_recommends_move_toward_target_cell(self):
        engine = ShadowCombatDecisionEngine()
        metrics = SimpleNamespace(
            cell=(12, 8),
            player_cell=(9, 8),
            grid_distance=3,
            toward_steps=3,
            away_steps=0,
        )
        decision = engine.decide(
            state_with_target(),
            FakeObserver(metrics, mode="VISIBLE"),
            FakeTracker(state="VISIBLE", side="RIGHT"),
            now=1.0,
        )
        self.assertEqual(decision.mode, "APPROACH")
        self.assertEqual(decision.navigation, "MOVE_RIGHT")
        self.assertTrue(decision.base_r)

    def test_contact_recommends_face_and_h_only_after_stable_window(self):
        engine = ShadowCombatDecisionEngine(h_stable_seconds=0.6, h_cooldown_seconds=2.0)
        metrics = SimpleNamespace(
            cell=(10, 8),
            player_cell=(9, 8),
            grid_distance=1,
            toward_steps=2,
            away_steps=0,
        )
        state = state_with_target(score=82.0)
        observer = FakeObserver(metrics, mode="OCCLUDED")
        tracker = FakeTracker(state="OCCLUDED", side="RIGHT")

        first = engine.decide(state, observer, tracker, now=1.0)
        self.assertEqual(first.navigation, "FACE_RIGHT")
        self.assertFalse(first.h_opportunity)

        second = engine.decide(state, observer, tracker, now=1.7)
        self.assertTrue(second.h_opportunity)

        third = engine.decide(state, observer, tracker, now=2.0)
        self.assertFalse(third.h_opportunity)

    def test_contact_memory_never_recommends_h_without_visual_confirmation(self):
        engine = ShadowCombatDecisionEngine(h_stable_seconds=0.0)
        metrics = SimpleNamespace(
            cell=(10, 8),
            player_cell=(9, 8),
            grid_distance=1,
            toward_steps=0,
            away_steps=0,
        )
        decision = engine.decide(
            state_with_target(score=90.0),
            FakeObserver(metrics, mode="CONTACT_MEMORY"),
            FakeTracker(state="LOST", side="RIGHT"),
            now=3.0,
        )
        self.assertTrue(decision.base_r)
        self.assertFalse(decision.h_opportunity)


if __name__ == "__main__":
    unittest.main()
