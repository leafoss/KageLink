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


def target_state(track_id: int, score: float = 82.0):
    return SimpleNamespace(target=SimpleNamespace(track_id=track_id, enemy_score=score))


def contact_metrics(cell=(10, 8), player_cell=(9, 8)):
    return SimpleNamespace(
        cell=cell,
        player_cell=player_cell,
        grid_distance=1,
        toward_steps=2,
        away_steps=0,
    )


class ShadowEngagementMemoryTests(unittest.TestCase):
    def test_combat_session_keeps_r_on_during_target_gap(self):
        engine = ShadowCombatDecisionEngine(combat_active_on_start=True)
        decision = engine.decide(
            SimpleNamespace(target=None),
            FakeObserver(None),
            FakeTracker(),
            now=1.0,
        )
        self.assertEqual(decision.mode, "ENGAGED_SEARCH")
        self.assertTrue(decision.base_r)

    def test_entity_id_switch_does_not_reset_h_stability(self):
        engine = ShadowCombatDecisionEngine(
            h_stable_seconds=0.6,
            h_cooldown_seconds=2.0,
            combat_active_on_start=True,
        )
        observer = FakeObserver(contact_metrics(), mode="OCCLUDED")
        tracker = FakeTracker(state="OCCLUDED", side="RIGHT")

        first = engine.decide(target_state(10), observer, tracker, now=1.0)
        second = engine.decide(target_state(99), observer, tracker, now=1.7)

        self.assertFalse(first.h_opportunity)
        self.assertTrue(second.h_opportunity)
        self.assertGreaterEqual(second.engagement_stable_seconds, 0.6)

    def test_contact_memory_preserves_last_visual_face(self):
        engine = ShadowCombatDecisionEngine(combat_active_on_start=True)
        visual_observer = FakeObserver(contact_metrics(), mode="OCCLUDED")
        visual_tracker = FakeTracker(state="OCCLUDED", side="RIGHT")
        engine.decide(target_state(1), visual_observer, visual_tracker, now=1.0)

        stale_metrics = contact_metrics(cell=(8, 8), player_cell=(9, 8))
        memory_observer = FakeObserver(stale_metrics, mode="CONTACT_MEMORY")
        memory_tracker = FakeTracker(state="LOST", side="LEFT")
        decision = engine.decide(target_state(2), memory_observer, memory_tracker, now=1.2)

        self.assertEqual(decision.face, "RIGHT")
        self.assertEqual(decision.navigation, "FACE_RIGHT")
        self.assertFalse(decision.h_opportunity)

    def test_long_visual_gap_resets_h_stability_but_not_r(self):
        engine = ShadowCombatDecisionEngine(
            engagement_gap_seconds=0.75,
            combat_active_on_start=True,
        )
        observer = FakeObserver(contact_metrics(), mode="OCCLUDED")
        tracker = FakeTracker(state="OCCLUDED", side="RIGHT")
        engine.decide(target_state(1), observer, tracker, now=1.0)

        short_gap = engine.decide(SimpleNamespace(target=None), observer, tracker, now=1.4)
        long_gap = engine.decide(SimpleNamespace(target=None), observer, tracker, now=2.0)

        self.assertTrue(short_gap.base_r)
        self.assertGreater(short_gap.engagement_stable_seconds, 0.0)
        self.assertTrue(long_gap.base_r)
        self.assertEqual(long_gap.engagement_stable_seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
