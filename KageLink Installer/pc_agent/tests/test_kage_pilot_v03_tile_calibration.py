from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np

from pc_agent.kage_pilot.entity_observer import EntityTrack, FlowEstimate, ObserverState
from pc_agent.kage_pilot.grid_target_observer_v03 import GridTrackMetrics
from pc_agent.kage_pilot.grid_target_observer_v03d import TileCalibratedGridTargetObserver
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig


class _FakeTracker:
    def __init__(self, context) -> None:
        self._context = context

    def context_for(self, track_id: int):
        del track_id
        return self._context


def _track() -> EntityTrack:
    track = EntityTrack(
        track_id=7,
        bbox=(300, 170, 24, 42),
        center=(312.0, 191.0),
        created_at=0.0,
        last_seen=0.1,
        observations=5,
        shape_score=0.8,
    )
    track.enemy_score = 70.0
    return track


def _state(track: EntityTrack | None = None, *, timestamp: float = 0.0) -> ObserverState:
    return ObserverState(
        timestamp=timestamp,
        arena_rect=(38, 22, 922, 464),
        player_center=(458.0, 208.0),
        global_flow=FlowEstimate(),
        tracks=() if track is None else (track,),
        target_id=None,
        motion_mask=np.zeros((442, 884), dtype=np.uint8),
    )


class KagePilotV03TileCalibrationTests(unittest.TestCase):
    def _observer(self) -> TileCalibratedGridTargetObserver:
        config = V03ObserverConfig().normalized()
        return TileCalibratedGridTargetObserver(config, tile_size=64.0)

    def test_auto_grid_alignment_centres_player_inside_64px_cell(self):
        observer = self._observer()
        state = _state()

        observer._align_grid_to_player(state)

        origin_x, origin_y = observer.grid_origin
        full_player_x = state.arena_rect[0] + state.player_center[0]
        full_player_y = state.arena_rect[1] + state.player_center[1]
        self.assertAlmostEqual((full_player_x - origin_x) % 64.0, 32.0, places=5)
        self.assertAlmostEqual((full_player_y - origin_y) % 64.0, 32.0, places=5)

    def test_single_adjacent_observation_does_not_confirm_contact(self):
        observer = self._observer()
        track = _track()
        observer.tracker = _FakeTracker(
            SimpleNamespace(state="VISIBLE", relative_side="RIGHT", last_visible_side="RIGHT")
        )
        observer._last_metrics[track.track_id] = GridTrackMetrics(
            cell=(8, 5),
            player_cell=(7, 5),
            grid_distance=1,
            unique_cells=1,
            toward_steps=0,
            away_steps=0,
            net_closer=0,
            approach_ratio=0.0,
            background_strength=0.0,
        )

        observer._update_contact_evidence(_state(track, timestamp=0.0))

        self.assertFalse(observer._contact_confirmed(track))

    def test_two_adjacent_frames_confirm_contact(self):
        observer = self._observer()
        track = _track()
        observer.tracker = _FakeTracker(
            SimpleNamespace(state="VISIBLE", relative_side="RIGHT", last_visible_side="RIGHT")
        )
        observer._last_metrics[track.track_id] = GridTrackMetrics(
            cell=(8, 5),
            player_cell=(7, 5),
            grid_distance=1,
            unique_cells=1,
            toward_steps=0,
            away_steps=0,
            net_closer=0,
            approach_ratio=0.0,
            background_strength=0.0,
        )

        observer._update_contact_evidence(_state(track, timestamp=0.0))
        observer._update_contact_evidence(_state(track, timestamp=0.1))

        self.assertTrue(observer._contact_confirmed(track))

    def test_manual_origin_disables_auto_realignment(self):
        config = V03ObserverConfig().normalized()
        observer = TileCalibratedGridTargetObserver(
            config,
            tile_size=64.0,
            auto_align_grid=False,
            grid_origin_x=11.0,
            grid_origin_y=17.0,
        )

        observer._align_grid_to_player(_state())

        self.assertEqual(observer.grid_origin, (11.0, 17.0))


if __name__ == "__main__":
    unittest.main()
