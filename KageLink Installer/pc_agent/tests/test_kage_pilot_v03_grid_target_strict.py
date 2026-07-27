from __future__ import annotations

from collections import deque
import unittest

import numpy as np

from pc_agent.kage_pilot.entity_observer import EntityTrack, FlowEstimate, ObserverState
from pc_agent.kage_pilot.entity_tracker_v03 import TrackContext
from pc_agent.kage_pilot.grid_target_observer_v03 import GridTrackMetrics
from pc_agent.kage_pilot.grid_target_observer_v03b import StrictGridTargetObserver
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.persistent_water_tracker_v03 import PersistentBackgroundWaterAwareEntityTracker


def _track(track_id=1, *, center=(160.0, 96.0), score=90.0):
    track = EntityTrack(
        track_id=track_id,
        bbox=(round(center[0] - 9), round(center[1] - 19), 18, 38),
        center=center,
        created_at=0.0,
        last_seen=1.0,
        observations=8,
        motion_energy=0.3,
        edge_density=0.2,
        shape_score=0.8,
    )
    track.enemy_score = score
    track.history = deque([center], maxlen=28)
    return track


class KagePilotV03StrictGridTests(unittest.TestCase):
    def _observer(self):
        config = V03ObserverConfig(
            target_acquire_threshold=55,
            target_keep_threshold=38,
        ).normalized()
        observer = StrictGridTargetObserver(config, tile_size=32, contact_lock_seconds=2.8)
        tracker = PersistentBackgroundWaterAwareEntityTracker(config)
        observer.tracker = tracker
        return observer, tracker

    def _state(self, track, *, timestamp=1.0, player=(96.0, 96.0)):
        return ObserverState(
            timestamp=timestamp,
            arena_rect=(0, 0, 640, 384),
            player_center=player,
            global_flow=FlowEstimate(),
            tracks=(track,),
            target_id=None,
            motion_mask=np.zeros((384, 640), dtype=np.uint8),
        )

    def test_two_cells_away_needs_coherent_grid_trajectory(self):
        observer, tracker = self._observer()
        track = _track(center=(160.0, 96.0))
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="VISIBLE", relative_side="RIGHT", last_visible_side="RIGHT")
        observer._last_metrics = {
            1: GridTrackMetrics(
                cell=(5, 3),
                player_cell=(3, 3),
                grid_distance=2,
                unique_cells=2,
                toward_steps=1,
                away_steps=0,
                net_closer=1,
                approach_ratio=1.0,
                background_strength=0.0,
            )
        }
        self.assertFalse(observer._grid_eligible(track, self._state(track), for_keep=False))

    def test_lost_track_does_not_extend_contact_latch(self):
        observer, tracker = self._observer()
        track = _track(center=(105.0, 96.0))
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="LOST", relative_side="RIGHT", last_visible_side="RIGHT")
        observer._grid_target_id = 1
        observer._contact_latch_until = 2.0
        observer._contact_side = "RIGHT"
        observer._last_metrics = {
            1: GridTrackMetrics(
                cell=(3, 3),
                player_cell=(3, 3),
                grid_distance=0,
                unique_cells=2,
                toward_steps=1,
                away_steps=0,
                net_closer=1,
                approach_ratio=1.0,
                background_strength=0.0,
            )
        }

        first = observer._select_grid_target(self._state(track, timestamp=1.5))
        self.assertEqual(first, 1)
        self.assertEqual(observer.target_mode, "CONTACT_MEMORY")
        self.assertEqual(observer._contact_latch_until, 2.0)

        second = observer._select_grid_target(self._state(track, timestamp=2.1))
        self.assertIsNone(second)
        self.assertEqual(observer.target_mode, "NONE")

    def test_visible_adjacent_target_can_start_contact_latch(self):
        observer, tracker = self._observer()
        track = _track(center=(105.0, 96.0))
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="VISIBLE", relative_side="RIGHT", last_visible_side="RIGHT")
        observer._last_metrics = {
            1: GridTrackMetrics(
                cell=(3, 3),
                player_cell=(3, 3),
                grid_distance=0,
                unique_cells=2,
                toward_steps=1,
                away_steps=0,
                net_closer=1,
                approach_ratio=1.0,
                background_strength=0.0,
            )
        }
        observer._latch_contact(track, self._state(track, timestamp=1.0))
        self.assertGreater(observer._contact_latch_until, 3.0)
        self.assertEqual(observer._contact_side, "RIGHT")


if __name__ == "__main__":
    unittest.main()
