from __future__ import annotations

import unittest

from pc_agent.kage_pilot.trainer_search_v03k import TrainerSearchMotionGate


class KagePilotV03KTrainerSearchGateTests(unittest.TestCase):
    def test_initial_scan_holds_without_movement(self):
        gate = TrainerSearchMotionGate(initial_scan_seconds=1.5)
        action, direction = gate.next_action(now=10.0)
        self.assertEqual(action, "INITIAL_SCAN_HOLD")
        self.assertIsNone(direction)

        action, direction = gate.next_action(now=11.49)
        self.assertEqual(action, "INITIAL_SCAN_HOLD")
        self.assertIsNone(direction)

    def test_one_lateral_reveal_probe_after_initial_scan(self):
        gate = TrainerSearchMotionGate(
            initial_scan_seconds=1.5,
            reveal_scan_seconds=0.75,
            reveal_direction="right",
        )
        gate.next_action(now=10.0)
        action, direction = gate.next_action(now=11.5)
        self.assertEqual(action, "SELF_OCCLUSION_REVEAL")
        self.assertEqual(direction, "right")
        self.assertTrue(gate.reveal_sent)

    def test_reveal_probe_is_never_repeated(self):
        gate = TrainerSearchMotionGate(
            initial_scan_seconds=1.0,
            reveal_scan_seconds=0.5,
        )
        gate.next_action(now=0.0)
        self.assertEqual(gate.next_action(now=1.0), ("SELF_OCCLUSION_REVEAL", "right"))
        self.assertEqual(gate.next_action(now=1.1), ("REVEAL_SCAN_HOLD", None))
        self.assertEqual(gate.next_action(now=1.5), ("SEARCH_ALLOWED", None))
        self.assertEqual(gate.next_action(now=2.0), ("SEARCH_ALLOWED", None))

    def test_reveal_scan_holds_all_inputs(self):
        gate = TrainerSearchMotionGate(
            initial_scan_seconds=1.0,
            reveal_scan_seconds=0.75,
        )
        gate.next_action(now=5.0)
        gate.next_action(now=6.0)
        action, direction = gate.next_action(now=6.5)
        self.assertEqual(action, "REVEAL_SCAN_HOLD")
        self.assertIsNone(direction)
        self.assertAlmostEqual(gate.remaining(now=6.5), 0.25, places=6)

    def test_each_ring_pulse_arms_a_stationary_scan_dwell(self):
        gate = TrainerSearchMotionGate(
            initial_scan_seconds=0.5,
            reveal_scan_seconds=0.25,
            post_move_scan_seconds=0.35,
        )
        gate.next_action(now=0.0)
        gate.next_action(now=0.5)
        self.assertEqual(gate.next_action(now=0.75), ("SEARCH_ALLOWED", None))

        gate.record_search_move(now=1.0)
        self.assertEqual(gate.next_action(now=1.1), ("POST_MOVE_SCAN_HOLD", None))
        self.assertEqual(gate.next_action(now=1.35), ("SEARCH_ALLOWED", None))

    def test_reveal_direction_is_always_lateral(self):
        self.assertEqual(
            TrainerSearchMotionGate(reveal_direction="left").reveal_direction,
            "left",
        )
        self.assertEqual(
            TrainerSearchMotionGate(reveal_direction="up").reveal_direction,
            "right",
        )


if __name__ == "__main__":
    unittest.main()
