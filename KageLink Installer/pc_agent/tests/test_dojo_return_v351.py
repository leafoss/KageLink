from __future__ import annotations

from pathlib import Path
import unittest

import kage_pilot_live_v0351_round


class DojoClosedLoopReturnV351ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = Path(kage_pilot_live_v0351_round.__file__).resolve()
        cls.source = cls.path.read_text(encoding="utf-8")

    def test_visual_position_is_observed_during_world_and_movement_frames(self):
        self.assertIn("def observe_world", self.source)
        self.assertIn("self.position.observe(frame_bgr, observer_state)", self.source)
        self.assertIn("def observe_movement_frame", self.source)
        self.assertIn("commanded_direction=commanded", self.source)

    def test_accepted_template_mode_controls_cell_conversion(self):
        self.assertIn('value if value in {"32", "64"}', self.source)
        self.assertIn("self.position.odometry.cell_size = cell_size", self.source)
        self.assertIn("DOJO_CELL_MODE", self.source)

    def test_return_is_closed_loop_and_replans_after_observation(self):
        self.assertIn("before_distance = math.hypot", self.source)
        self.assertIn("after_distance = math.hypot", self.source)
        self.assertIn("DOJO_RETURN_REPLAN", self.source)
        self.assertIn("DOJO_RETURN_NO_PROGRESS", self.source)
        self.assertIn("DOJO_RETURN_STALLED", self.source)
        self.assertIn("return_no_progress_limit", self.source)

    def test_lost_position_relocalizes_before_any_vector_return(self):
        relocalize = self.source.index("self.position.relocalize(frame_bgr, observer_state)")
        vector_return = self.source.index("if not self.position.near_origin")
        self.assertLess(relocalize, vector_return)
        self.assertIn("DOJO_POSITION_UNKNOWN", self.source)

    def test_fallback_order_is_static_scan_then_local_search_then_existing_rings(self):
        origin = self.source.index("DOJO_RETURN_ORIGIN_REACHED")
        static_scan = self.source.index("DOJO_RETURN_STATIC_SCAN")
        local_search = self.source.index("DOJO_SAFE_LOCAL_SEARCH_BEGIN", origin)
        ring_fallback = self.source.index("DOJO_SEARCH_FALLBACK_BEGIN")
        self.assertLess(origin, static_scan)
        self.assertLess(static_scan, local_search)
        self.assertLess(local_search, ring_fallback)

    def test_return_has_timeout_step_and_no_progress_limits(self):
        self.assertIn("return_timeout_seconds", self.source)
        self.assertIn("return_max_steps", self.source)
        self.assertIn("return_no_progress_limit", self.source)
        self.assertIn("timeout_or_step_limit", self.source)

    def test_anchor_is_set_only_from_current_visual_confirmation(self):
        self.assertIn('getattr(match, "source", "") == "visual"', self.source)
        self.assertIn("self._set_visual_anchor(frame_bgr, observer_state)", self.source)
        self.assertNotIn("macro_start", self.source)

    def test_existing_validated_runtime_remains_the_provider(self):
        self.assertIn("import kage_pilot_live_v03k_round as validated_round", self.source)
        self.assertIn("return validated_round.main()", self.source)


if __name__ == "__main__":
    unittest.main()
