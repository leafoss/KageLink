from __future__ import annotations

from collections import deque
import unittest

import numpy as np

from pc_agent.kage_pilot.entity_observer import EntityTrack, FlowEstimate, ObserverState
from pc_agent.kage_pilot.entity_tracker_v03 import TrackContext
from pc_agent.kage_pilot.grid_target_observer_v03 import (
    GridTargetObserver,
    GridTrackMetrics,
    _cell_for,
    _compress_cells,
    _grid_distance,
)
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.persistent_water_tracker_v03 import PersistentBackgroundWaterAwareEntityTracker


def _track(track_id: int = 1, *, center=(96.0, 96.0), score=75.0) -> EntityTrack:
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
    return track


class KagePilotV03GridTargetTests(unittest.TestCase):
    def _observer(self) -> tuple[GridTargetObserver, PersistentBackgroundWaterAwareEntityTracker]:
        config = V03ObserverConfig(
            target_acquire_threshold=55,
            target_keep_threshold=38,
        ).normalized()
        observer = GridTargetObserver(config, tile_size=32, contact_lock_seconds=2.8)
        tracker = PersistentBackgroundWaterAwareEntityTracker(config)
        observer.tracker = tracker
        return observer, tracker

    def test_grid_math_uses_32px_cells(self):
        self.assertEqual(_cell_for((95.0, 65.0), 32), (2, 2))
        self.assertEqual(_grid_distance((5, 2), (2, 4)), 3)
        self.assertEqual(
            _compress_cells([(65.0, 65.0), (70.0, 68.0), (97.0, 65.0)], 32),
            [(2, 2), (3, 2)],
        )

    def test_cell_path_toward_player_is_coherent_approach(self):
        observer, tracker = self._observer()
        track = _track(center=(96.0, 96.0))
        track.history = deque(
            [(192.0, 96.0), (160.0, 96.0), (128.0, 96.0), (96.0, 96.0)],
            maxlen=28,
        )
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="VISIBLE", relative_side="RIGHT", last_visible_side="RIGHT")
        state = ObserverState(
            timestamp=1.0,
            arena_rect=(0, 0, 640, 384),
            player_center=(32.0, 96.0),
            global_flow=FlowEstimate(),
            tracks=(track,),
            target_id=None,
            motion_mask=np.zeros((384, 640), dtype=np.uint8),
        )
        metrics = observer._metrics(track, state)
        self.assertGreaterEqual(metrics.toward_steps, 2)
        self.assertGreaterEqual(metrics.net_closer, 2)
        self.assertTrue(metrics.coherent_approach)

    def test_local_jitter_does_not_become_grid_approach(self):
        observer, tracker = self._observer()
        track = _track(center=(322.0, 100.0))
        track.history = deque(
            [(320.0, 100.0), (324.0, 102.0), (319.0, 98.0), (323.0, 101.0)],
            maxlen=28,
        )
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="VISIBLE", relative_side="UP", last_visible_side="UP")
        state = ObserverState(
            timestamp=1.0,
            arena_rect=(0, 0, 640, 384),
            player_center=(96.0, 300.0),
            global_flow=FlowEstimate(),
            tracks=(track,),
            target_id=None,
            motion_mask=np.zeros((384, 640), dtype=np.uint8),
        )
        metrics = observer._metrics(track, state)
        self.assertFalse(metrics.coherent_approach)
        self.assertLess(metrics.unique_cells, 3)

    def test_contact_memory_keeps_recent_lost_target(self):
        observer, tracker = self._observer()
        track = _track(center=(110.0, 100.0))
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="LOST", relative_side="RIGHT", last_visible_side="RIGHT")
        observer._grid_target_id = 1
        observer._contact_latch_until = 3.0
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
        state = ObserverState(
            timestamp=2.0,
            arena_rect=(0, 0, 640, 384),
            player_center=(100.0, 100.0),
            global_flow=FlowEstimate(),
            tracks=(track,),
            target_id=None,
            motion_mask=np.zeros((384, 640), dtype=np.uint8),
        )
        selected = observer._select_grid_target(state)
        self.assertEqual(selected, 1)
        self.assertEqual(observer.target_mode, "CONTACT_MEMORY")

    def test_distant_visible_track_requires_cell_approach(self):
        observer, tracker = self._observer()
        track = _track(center=(320.0, 96.0), score=95.0)
        tracker._tracks[1] = track
        tracker._contexts[1] = TrackContext(state="VISIBLE", relative_side="UP", last_visible_side="UP")
        observer._last_metrics = {
            1: GridTrackMetrics(
                cell=(10, 3),
                player_cell=(3, 9),
                grid_distance=7,
                unique_cells=1,
                toward_steps=0,
                away_steps=0,
                net_closer=0,
                approach_ratio=0.0,
                background_strength=0.0,
            )
        }
        state = ObserverState(
            timestamp=1.0,
            arena_rect=(0, 0, 640, 384),
            player_center=(96.0, 288.0),
            global_flow=FlowEstimate(),
            tracks=(track,),
            target_id=None,
            motion_mask=np.zeros((384, 640), dtype=np.uint8),
        )
        self.assertFalse(observer._grid_eligible(track, state, for_keep=False))


if __name__ == "__main__":
    unittest.main()
