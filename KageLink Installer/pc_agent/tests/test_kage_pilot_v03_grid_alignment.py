from __future__ import annotations

import unittest

import numpy as np

from pc_agent.kage_pilot.entity_observer import FlowEstimate, ObserverState
from pc_agent.kage_pilot.grid_target_observer_v03c import FrameAlignedGridTargetObserver
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig


class KagePilotV03GridAlignmentTests(unittest.TestCase):
    def test_arena_local_point_maps_to_full_frame_tile(self):
        observer = FrameAlignedGridTargetObserver(V03ObserverConfig().normalized(), tile_size=32)
        state = ObserverState(
            timestamp=0.0,
            arena_rect=(38, 22, 922, 464),
            player_center=(100.0, 100.0),
            global_flow=FlowEstimate(),
            tracks=(),
            target_id=None,
            motion_mask=np.zeros((442, 884), dtype=np.uint8),
        )
        # Arena-local (100,100) is full-frame (138,122), therefore tile (4,3).
        self.assertEqual(observer._frame_cell((100.0, 100.0), state), (4, 3))


if __name__ == "__main__":
    unittest.main()
