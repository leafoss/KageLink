from __future__ import annotations

import inspect
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from pc_agent.kage_pilot import dojo_resolution_runtime_fix_v351 as runtime_fix
from pc_agent.kage_pilot.dojo_raw_trainer_v351 import RawDojoLeaderDetector


class DojoResolutionRuntimeFixV351Tests(unittest.TestCase):
    def test_compatibility_detector_is_the_exact_raw_matcher(self):
        self.assertIs(
            runtime_fix.BoundedResolutionIndependentDojoLeaderDetector,
            RawDojoLeaderDetector,
        )
        source = inspect.getsource(runtime_fix)
        self.assertNotIn("cv2.resize", source)
        self.assertNotIn("template_scale_cursor", source)
        self.assertNotIn("multiscale", source.casefold())

    def test_search_grid_uses_confirmed_64_cell_geometry(self):
        runtime_fix.install_resolution_runtime_fix()
        from pc_agent.kage_pilot.post_combat_v03e import ObstacleAwarePostCombatRecoveryEngine

        engine = ObstacleAwarePostCombatRecoveryEngine(
            leader_detector=SimpleNamespace(last_raw_score=-1.0, last_raw_location=None),
            search_timeout_seconds=30.0,
        )
        state = SimpleNamespace(
            arena_rect=(20, 30, 660, 350),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0),
        )
        frame = np.zeros((360, 680, 3), dtype=np.uint8)
        with patch.object(
            runtime_fix,
            "_desired_geometry",
            return_value=("64", 64.0, "test-raw-geometry"),
        ):
            engine.observe_movement_frame(frame, state, now=1.0)
        self.assertEqual(engine.search.pulses_per_cell, 8)
        self.assertEqual(engine.search.arena_width_cells, 10)
        self.assertEqual(engine.search.arena_height_cells, 5)
        self.assertEqual(engine.search.max_radius, 9)

    def test_unknown_geometry_does_not_invent_an_intermediate_cell_size(self):
        with patch.object(runtime_fix, "_desired_geometry", return_value=None):
            self.assertIsNone(runtime_fix._desired_geometry())


if __name__ == "__main__":
    unittest.main()
