from __future__ import annotations

from types import SimpleNamespace
import unittest

import kage_pilot_live_v03j_round as runtime


def _decision(
    *,
    face: str = "DOWN",
    target_id: int = 10,
    target_mode: str = "VISIBLE",
    distance: int = 1,
):
    return SimpleNamespace(
        base_r=True,
        mode="MELEE",
        navigation=f"FACE_{face}",
        face=face,
        h_opportunity=True,
        target_id=target_id,
        grid_distance=distance,
        reason=f"logical engagement d={distance} mode={target_mode}; stable=2.00s",
    )


class KagePilotV03JBurstFacingTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime.round_v03i._RESYNC.active_until = -1e9
        runtime.round_v03i._RESYNC.reason = ""

    def tearDown(self) -> None:
        runtime.round_v03i._RESYNC.active_until = -1e9
        runtime.round_v03i._RESYNC.reason = ""

    def test_visual_adjacent_direction_gets_one_face_pulse_after_two_burst_frames(self):
        planner = runtime.BurstSafeMeleeFacingPlanner(h_enabled=True)
        planner._last_face = "UP"
        decision = _decision(face="DOWN", target_mode="VISIBLE")

        first = planner.plan(
            decision,
            now=10.0,
            movement_allowed=False,
            block_reason="active_cells_spike=75",
        )
        second = planner.plan(
            decision,
            now=10.2,
            movement_allowed=False,
            block_reason="active_cells_spike=68",
        )
        third = planner.plan(
            decision,
            now=10.6,
            movement_allowed=False,
            block_reason="burst_settle",
        )

        self.assertIsNone(first.face_pulse)
        self.assertEqual(second.face_pulse, "down")
        self.assertEqual(second.held_keys, ("r",))
        self.assertIsNone(second.move_pulse)
        self.assertFalse(second.h_fire)
        self.assertEqual(second.safety_state, "BURST_FACE_CORRECT")
        self.assertIsNone(third.face_pulse)

    def test_contact_memory_never_authorizes_burst_face_exception(self):
        planner = runtime.BurstSafeMeleeFacingPlanner(h_enabled=True)
        decision = _decision(face="DOWN", target_mode="CONTACT_MEMORY")

        for index in range(4):
            command = planner.plan(
                decision,
                now=20.0 + index * 0.2,
                movement_allowed=False,
                block_reason="active_cells_spike=80",
            )
            self.assertIsNone(command.face_pulse)
            self.assertEqual(command.safety_state, "MOTION_BURST_HOLD")

    def test_non_adjacent_target_never_authorizes_burst_face_exception(self):
        planner = runtime.BurstSafeMeleeFacingPlanner(h_enabled=True)
        decision = _decision(face="DOWN", target_mode="VISIBLE", distance=2)

        for index in range(3):
            command = planner.plan(
                decision,
                now=30.0 + index * 0.2,
                movement_allowed=False,
                block_reason="active_cells_spike=70",
            )
            self.assertIsNone(command.face_pulse)

    def test_h_settle_remains_absolute_hold(self):
        planner = runtime.BurstSafeMeleeFacingPlanner(h_enabled=True)
        decision = _decision(face="DOWN", target_mode="VISIBLE")

        for index in range(3):
            command = planner.plan(
                decision,
                now=40.0 + index * 0.2,
                movement_allowed=False,
                block_reason="h_settle_remaining=0.20s",
            )
            self.assertIsNone(command.face_pulse)
            self.assertEqual(command.safety_state, "H_SETTLE_HOLD")

    def test_map_save_resync_still_releases_every_key(self):
        planner = runtime.BurstSafeMeleeFacingPlanner(h_enabled=True)
        decision = _decision(face="DOWN", target_mode="VISIBLE")
        runtime.round_v03i._RESYNC.trigger("unit_test", now=50.0, hold_seconds=2.0)

        command = planner.plan(
            decision,
            now=50.5,
            movement_allowed=False,
            block_reason="active_cells_spike=100",
        )

        self.assertEqual(command.held_keys, ())
        self.assertIsNone(command.face_pulse)
        self.assertIsNone(command.move_pulse)
        self.assertFalse(command.h_fire)
        self.assertEqual(command.safety_state, "MAP_SAVE_RESYNC")

    def test_normal_frame_resets_episode_and_allows_future_burst_correction(self):
        planner = runtime.BurstSafeMeleeFacingPlanner(h_enabled=True)
        decision = _decision(face="DOWN", target_mode="OCCLUDED")

        planner.plan(decision, now=60.0, movement_allowed=False, block_reason="burst_settle")
        first_burst = planner.plan(
            decision,
            now=60.2,
            movement_allowed=False,
            block_reason="burst_settle",
        )
        self.assertEqual(first_burst.face_pulse, "down")

        planner.plan(decision, now=61.0, movement_allowed=True)
        planner.plan(decision, now=62.0, movement_allowed=False, block_reason="burst_settle")
        second_burst = planner.plan(
            decision,
            now=62.2,
            movement_allowed=False,
            block_reason="burst_settle",
        )
        self.assertEqual(second_burst.face_pulse, "down")


if __name__ == "__main__":
    unittest.main()
