from __future__ import annotations

import unittest
from types import SimpleNamespace

from pc_agent.kage_pilot.live_control_v03 import LiveCombatControlPlanner
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


def state_with_target(track_id=7, score=80.0):
    return SimpleNamespace(target=SimpleNamespace(track_id=track_id, enemy_score=score))


def metrics(*, cell=(10, 8), player=(9, 8), distance=1, background_strength=0.0):
    return SimpleNamespace(
        cell=cell,
        player_cell=player,
        grid_distance=distance,
        toward_steps=2,
        away_steps=0,
        background_strength=background_strength,
    )


class KagePilotV03LiveControlTests(unittest.TestCase):
    def test_contact_memory_at_two_cells_holds_instead_of_blind_recover(self):
        engine = ShadowCombatDecisionEngine(combat_active_on_start=True)
        decision = engine.decide(
            state_with_target(),
            FakeObserver(metrics(cell=(11, 8), player=(9, 8), distance=2), mode="CONTACT_MEMORY"),
            FakeTracker(state="LOST", side="RIGHT"),
            now=1.0,
        )
        self.assertEqual(decision.mode, "MEMORY_HOLD")
        self.assertEqual(decision.navigation, "HOLD")
        self.assertTrue(decision.base_r)
        self.assertFalse(decision.h_opportunity)

    def test_visible_target_at_two_cells_still_recovers(self):
        engine = ShadowCombatDecisionEngine(combat_active_on_start=True)
        decision = engine.decide(
            state_with_target(),
            FakeObserver(metrics(cell=(11, 8), player=(9, 8), distance=2), mode="VISIBLE"),
            FakeTracker(state="VISIBLE", side="RIGHT"),
            now=1.0,
        )
        self.assertEqual(decision.mode, "APPROACH")
        self.assertEqual(decision.navigation, "MOVE_RIGHT")
        self.assertTrue(decision.base_r)

    def test_strong_dynamic_background_blocks_visible_pursuit(self):
        engine = ShadowCombatDecisionEngine(combat_active_on_start=True, pursuit_background_block=0.50)
        decision = engine.decide(
            state_with_target(),
            FakeObserver(
                metrics(cell=(11, 8), player=(9, 8), distance=2, background_strength=0.92),
                mode="VISIBLE",
            ),
            FakeTracker(state="VISIBLE", side="RIGHT"),
            now=1.0,
        )
        self.assertEqual(decision.mode, "BACKGROUND_HOLD")
        self.assertEqual(decision.navigation, "HOLD")

    def test_move_holds_r_and_direction(self):
        planner = LiveCombatControlPlanner()
        decision = SimpleNamespace(
            base_r=True,
            navigation="MOVE_RIGHT",
            h_opportunity=False,
            reason="recover",
        )
        command = planner.plan(decision, now=1.0)
        self.assertEqual(command.held_keys, ("r", "right"))
        self.assertIsNone(command.face_pulse)

    def test_face_is_short_pulse_not_continuous_hold(self):
        planner = LiveCombatControlPlanner(face_refresh_seconds=0.45)
        decision = SimpleNamespace(
            base_r=True,
            navigation="FACE_LEFT",
            h_opportunity=False,
            reason="melee",
        )
        first = planner.plan(decision, now=1.0)
        second = planner.plan(decision, now=1.1)
        refreshed = planner.plan(decision, now=1.6)
        self.assertEqual(first.held_keys, ("r",))
        self.assertEqual(first.face_pulse, "left")
        self.assertIsNone(second.face_pulse)
        self.assertEqual(refreshed.face_pulse, "left")

    def test_h_ready_remains_shadow_only(self):
        planner = LiveCombatControlPlanner()
        decision = SimpleNamespace(
            base_r=True,
            navigation="FACE_RIGHT",
            h_opportunity=True,
            reason="skill window",
        )
        command = planner.plan(decision, now=2.0)
        self.assertTrue(command.h_shadow_ready)
        self.assertNotIn("h", command.held_keys)
        self.assertNotEqual(command.face_pulse, "h")


if __name__ == "__main__":
    unittest.main()
