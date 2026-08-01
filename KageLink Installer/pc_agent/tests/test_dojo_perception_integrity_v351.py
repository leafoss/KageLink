from __future__ import annotations

from types import SimpleNamespace
import unittest

from pc_agent.kage_pilot.dojo_perception_integrity_v351 import (
    PerceptionStallLatch,
    install_round_geometry_lock,
    motion_candidate_body_rejection_reason,
)
from pc_agent.kage_pilot.grid_geometry_v351 import (
    reset_grid_geometry_telemetry_for_tests,
)


class _Position:
    def __init__(self, cell_size: float) -> None:
        self.cell_size = cell_size
        self.odometry = SimpleNamespace(
            cell_size=cell_size,
            player_patch_width=44 if cell_size == 64.0 else 22,
            player_patch_height=76 if cell_size == 64.0 else 38,
            reset=lambda: None,
        )


class _Engine:
    def __init__(self, *, cell_size: float, detected_mode: str) -> None:
        self.position = _Position(cell_size)
        self.leader_detector = SimpleNamespace(
            last_accepted_template_mode=detected_mode,
        )

    def _sync_cell_mode(self) -> str:
        return str(int(self.position.cell_size))


class DojoPerceptionIntegrityV351Tests(unittest.TestCase):
    def setUp(self) -> None:
        reset_grid_geometry_telemetry_for_tests()

    def test_round_64_grid_ignores_later_mode_32_template_conflict(self):
        events: list[tuple[str, dict[str, object]]] = []

        class Runtime:
            ClosedLoopVisualRecoveryEngine = _Engine

            @staticmethod
            def _telemetry(event: str, fields: dict[str, object]) -> None:
                events.append((event, fields))

        install_round_geometry_lock(Runtime)
        engine = _Engine(cell_size=64.0, detected_mode="32")

        self.assertEqual(engine._sync_cell_mode(), "64")
        self.assertEqual(engine.position.cell_size, 64.0)
        conflict = [fields for event, fields in events if event == "DOJO_GRID_MODE_CONFLICT"]
        self.assertEqual(len(conflict), 1)
        self.assertEqual(conflict[0]["expected_mode"], "64")
        self.assertEqual(conflict[0]["detected_mode"], "32")
        self.assertEqual(conflict[0]["action"], "IGNORED")

    def test_short_floor_motion_is_rejected_before_track_creation(self):
        floor_patch = SimpleNamespace(
            bbox=(300, 220, 40, 18),
            center=(320.0, 229.0),
            shape_score=0.76,
            edge_density=0.08,
            contour_area=420.0,
        )
        reason = motion_candidate_body_rejection_reason(
            floor_patch,
            player_center=(500.0, 300.0),
            tile_size=64.0,
            player_box_size=(36.0, 76.0),
            frame_shape=(800, 1600),
        )
        self.assertIn(
            reason,
            {"BODY_TOO_SHORT", "BODY_FLOOR_OR_HORIZONTAL_EFFECT"},
        )

    def test_vertical_body_candidate_passes_the_motion_body_gate(self):
        body = SimpleNamespace(
            bbox=(620, 250, 24, 42),
            center=(632.0, 271.0),
            shape_score=0.78,
            edge_density=0.11,
            contour_area=470.0,
        )
        reason = motion_candidate_body_rejection_reason(
            body,
            player_center=(500.0, 300.0),
            tile_size=64.0,
            player_box_size=(36.0, 76.0),
            frame_shape=(800, 1600),
        )
        self.assertIsNone(reason)

    def test_perception_stall_latch_holds_without_implying_reset(self):
        latch = PerceptionStallLatch()
        latch.mark("frame_gap=1.91s", now=10.0, hold_seconds=0.75)
        self.assertTrue(latch.active(now=10.50))
        self.assertFalse(latch.active(now=10.80))
        self.assertEqual(latch.reason, "frame_gap=1.91s")
        self.assertEqual(latch.generation, 1)


if __name__ == "__main__":
    unittest.main()
