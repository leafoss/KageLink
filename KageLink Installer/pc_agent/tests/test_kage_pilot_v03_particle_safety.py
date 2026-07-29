from __future__ import annotations

import unittest
from types import SimpleNamespace

from pc_agent.kage_pilot.particle_safe_grid_target_v03 import ParticleSafeGridTargetObserver


class KagePilotV03ParticleSafetyTests(unittest.TestCase):
    def test_tiny_distant_particle_is_not_grid_eligible(self):
        observer = object.__new__(ParticleSafeGridTargetObserver)
        observer._last_metrics = {7: SimpleNamespace(grid_distance=3)}
        tiny_particle = SimpleNamespace(
            track_id=7,
            bbox=(100.0, 100.0, 5.0, 7.0),
            shape_score=0.95,
        )

        self.assertFalse(
            observer._grid_eligible(
                tiny_particle,
                SimpleNamespace(),
                for_keep=False,
            )
        )


if __name__ == "__main__":
    unittest.main()
