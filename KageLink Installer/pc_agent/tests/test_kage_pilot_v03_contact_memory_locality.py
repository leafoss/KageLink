from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np

from pc_agent.kage_pilot.entity_observer import EntityTrack, FlowEstimate, ObserverState
from pc_agent.kage_pilot.grid_target_observer_v03 import GridTrackMetrics
from pc_agent.kage_pilot.grid_target_observer_v03d import TileCalibratedGridTargetObserver
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig


class FakeLostTracker:
    def context_for(self, track_id):
        del track_id
        return SimpleNamespace(
            state="LOST",
            relative_side="UP",
            last_visible_side="UP",
        )


def make_track() -> EntityTrack:
    track = EntityTrack(
        track_id=5,
        bbox=(300, 80, 18, 28),
        center=(309.0, 94.0),
        created_at=0.0,
        last_seen=1.0,
        observations=12,
        shape_score=0.7,
    )
    track.enemy_score = 90.0
    return track


class ContactMemoryLocalityTests(unittest.TestCase):
    def test_lost_contact_memory_three_cells_away_is_not_target(self):
        config = V03ObserverConfig().normalized()
        observer = TileCalibratedGridTargetObserver(config, tile_size=32.0)
        observer.tracker = FakeLostTracker()
        track = make_track()
        observer._grid_target_id = track.track_id
        observer._contact_latch_until = 10.0
        observer._last_metrics[track.track_id] = GridTrackMetrics(
            cell=(12, 3),
            player_cell=(12, 6),
            grid_distance=3,
            unique_cells=4,
            toward_steps=4,
            away_steps=1,
            net_closer=2,
            approach_ratio=0.8,
            background_strength=0.0,
        )
        state = ObserverState(
            timestamp=2.0,
            arena_rect=(0, 0, 640, 480),
            player_center=(400.0, 240.0),
            global_flow=FlowEstimate(),
            tracks=(track,),
            target_id=track.track_id,
            motion_mask=np.zeros((480, 640), dtype=np.uint8),
        )

        selected = observer._select_grid_target(state)

        self.assertIsNone(selected)
        self.assertEqual(observer.target_mode, "NONE")


if __name__ == "__main__":
    unittest.main()
