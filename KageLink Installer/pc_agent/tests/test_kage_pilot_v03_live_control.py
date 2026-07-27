from __future__ import annotations

import unittest
from types import SimpleNamespace

from pc_agent.kage_pilot.live_control_v03 import LiveCombatControlPlanner, MotionBurstGuard
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


def move_decision(*, target_id=7, distance=2, direction="RIGHT"):
    return SimpleNamespace(
        base_r=True,
        navigation=f"MOVE_{direction}",
        h_opportunity=False,
        reason="recover",
        target_id=target_id,
        grid_distance=distance,
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

    def test_move_is_deadman_pulse_not_continuous_held_direction(self):
        planner = LiveCombatControlPlanner(move_confirm_frames=2)
        decision = move_decision()
        first = planner.plan(decision, now=1.0)
        second = planner.plan(decision, now=1.1)

        self.assertEqual(first.held_keys, ("r",))
        self.assertIsNone(first.move_pulse)
        self.assertEqual(first.safety_state, "MOVE_CONFIRM")

        self.assertEqual(second.held_keys, ("r",))
        self.assertEqual(second.move_pulse, "right")
        self.assertEqual(second.safety_state, "MOVE_PULSE")
        self.assertNotIn("right", second.held_keys)

    def test_target_switch_requires_fresh_movement_confirmation(self):
        planner = LiveCombatControlPlanner(move_confirm_frames=2)
        planner.plan(move_decision(target_id=7), now=1.0)
        confirmed = planner.plan(move_decision(target_id=7), now=1.1)
        switched = planner.plan(move_decision(target_id=8), now=1.2)

        self.assertEqual(confirmed.move_pulse, "right")
        self.assertIsNone(switched.move_pulse)
        self.assertEqual(switched.safety_state, "MOVE_CONFIRM")

    def test_no_progress_watchdog_stops_repeated_pursuit(self):
        planner = LiveCombatControlPlanner(
            move_confirm_frames=2,
            max_no_progress_seconds=0.40,
            no_progress_cooldown_seconds=0.50,
        )
        planner.plan(move_decision(distance=3), now=1.0)
        moving = planner.plan(move_decision(distance=3), now=1.1)
        stopped = planner.plan(move_decision(distance=3), now=1.6)

        self.assertEqual(moving.move_pulse, "right")
        self.assertIsNone(stopped.move_pulse)
        self.assertEqual(stopped.held_keys, ("r",))
        self.assertEqual(stopped.safety_state, "NO_PROGRESS_HOLD")

    def test_grid_progress_renews_pursuit_window(self):
        planner = LiveCombatControlPlanner(
            move_confirm_frames=2,
            max_no_progress_seconds=0.40,
        )
        planner.plan(move_decision(distance=3), now=1.0)
        planner.plan(move_decision(distance=3), now=1.1)
        progressed = planner.plan(move_decision(distance=2), now=1.45)

        self.assertEqual(progressed.move_pulse, "right")
        self.assertEqual(progressed.safety_state, "MOVE_PULSE")

    def test_motion_burst_guard_blocks_sudden_particle_population(self):
        guard = MotionBurstGuard(hold_seconds=0.75, min_active_cells=18, min_entities=20)
        normal = guard.update(active_cells=3, entities=4, now=1.0)
        burst = guard.update(active_cells=40, entities=32, now=1.1)
        settling = guard.update(active_cells=4, entities=5, now=1.4)
        recovered = guard.update(active_cells=4, entities=5, now=2.0)

        self.assertFalse(normal.blocked)
        self.assertTrue(burst.blocked)
        self.assertTrue(settling.blocked)
        self.assertFalse(recovered.blocked)

    def test_motion_burst_veto_returns_to_r_only(self):
        planner = LiveCombatControlPlanner(move_confirm_frames=2)
        command = planner.plan(
            move_decision(),
            now=1.0,
            movement_allowed=False,
            block_reason="entities_spike=40",
        )
        self.assertEqual(command.held_keys, ("r",))
        self.assertIsNone(command.move_pulse)
        self.assertIsNone(command.face_pulse)
        self.assertEqual(command.safety_state, "MOTION_BURST_HOLD")

    def test_face_is_short_pulse_not_continuous_hold(self):
        planner = LiveCombatControlPlanner(face_refresh_seconds=0.45)
        decision = SimpleNamespace(
            base_r=True,
            navigation="FACE_LEFT",
            h_opportunity=False,
            reason="melee",
            target_id=7,
            grid_distance=1,
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
            target_id=7,
            grid_distance=1,
        )
        command = planner.plan(decision, now=2.0)
        self.assertTrue(command.h_shadow_ready)
        self.assertNotIn("h", command.held_keys)
        self.assertNotEqual(command.face_pulse, "h")
        self.assertNotEqual(command.move_pulse, "h")


if __name__ == "__main__":
    unittest.main()
