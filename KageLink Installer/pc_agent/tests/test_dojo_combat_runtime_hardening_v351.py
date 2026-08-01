from __future__ import annotations

import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pc_agent.kage_pilot.combat_target_config_v351 import CombatTargetConfig
from pc_agent.kage_pilot.dojo_combat_runtime_hardening_v351 import (
    HardenedCombatTargetMemory,
    choose_contact_candidate,
)
from pc_agent.kage_pilot.dojo_round_video_performance_v351 import (
    install_round_video_performance_guard,
)


class _Track:
    def __init__(
        self,
        track_id,
        *,
        center,
        bbox=None,
        score=80.0,
        shape_score=0.8,
    ):
        self.track_id = track_id
        self.center = center
        if bbox is None:
            bbox = (
                int(round(float(center[0]) - 16.0)),
                int(round(float(center[1]) - 24.0)),
                32,
                48,
            )
        self.bbox = bbox
        self.enemy_score = score
        self.shape_score = shape_score
        self.residual_velocity = (0.0, 0.0)


class _Tracker:
    def __init__(self, states):
        self.states = dict(states)

    def context_for(self, track_id):
        return SimpleNamespace(state=self.states[track_id], appearance=())


class _Observer:
    tile_size = 64.0

    def __init__(self, distances, rejected=None):
        self.distances = dict(distances)
        self.rejected = dict(rejected or {})

    def metrics_for(self, track_id):
        value = self.distances.get(track_id)
        return None if value is None else SimpleNamespace(grid_distance=value)

    def combat_track_rejection_reason(self, track, *, for_acquire=False):
        return self.rejected.get(track.track_id)


class _Recorder:
    def __init__(self):
        self.fps = 8.0
        self.calls = 0
        self.events = []

    def record(self, frame, state, observer, *, raw_candidates=(), engine=None):
        self.calls += 1
        return True

    def _emit(self, event, fields):
        self.events.append((event, fields))


class DojoCombatRuntimeHardeningV351Tests(unittest.TestCase):
    def test_only_visible_body_can_be_contact_candidate(self):
        distant = _Track(10, center=(260.0, 100.0), score=95.0)
        contact = _Track(11, center=(150.0, 100.0), score=60.0)
        occluded = _Track(12, center=(120.0, 100.0), score=99.0)
        lost = _Track(13, center=(115.0, 100.0), score=99.0)
        tracker = _Tracker(
            {10: "VISIBLE", 11: "VISIBLE", 12: "OCCLUDED", 13: "LOST"}
        )
        observer = _Observer({10: 5, 11: 1, 12: 1, 13: 1})

        chosen = choose_contact_candidate(
            (distant, lost, occluded, contact),
            tracker=tracker,
            observer=observer,
            player_center=(100.0, 100.0),
        )

        self.assertIs(chosen, contact)

    def test_large_nearby_blob_never_wins_by_proximity(self):
        body = _Track(1, center=(150.0, 100.0), bbox=(135, 70, 30, 58), score=60.0)
        effect = _Track(2, center=(110.0, 100.0), bbox=(40, 80, 140, 40), score=99.0)
        tracker = _Tracker({1: "VISIBLE", 2: "VISIBLE"})
        observer = _Observer({1: 1, 2: 1}, rejected={2: "BODY_TOO_WIDE"})

        chosen = choose_contact_candidate(
            (effect, body),
            tracker=tracker,
            observer=observer,
            player_center=(100.0, 100.0),
        )

        self.assertIs(chosen, body)

    def test_visual_id_rebind_never_becomes_teleport_velocity(self):
        memory = HardenedCombatTargetMemory(
            CombatTargetConfig(structured_logging_enabled=False)
        )
        first = _Track(1, center=(140.0, 100.0))
        second = _Track(99, center=(148.0, 100.0))
        context = SimpleNamespace(state="VISIBLE", appearance=())
        metrics = SimpleNamespace(grid_distance=1)

        memory.acquire(
            first,
            context,
            metrics,
            player_center=(100.0, 100.0),
            now=1.0,
            frame_index=1,
        )
        memory.observe(
            second,
            context,
            metrics,
            player_center=(100.0, 100.0),
            now=1.1,
            frame_index=2,
            rebound=True,
            rebind_score=0.95,
        )

        self.assertEqual(memory._velocity, (0.0, 0.0))
        self.assertEqual(memory.visual_track_id, 99)
        self.assertEqual(memory.combat_target_id, 1)

    def test_prediction_cannot_escape_local_contact_region(self):
        memory = HardenedCombatTargetMemory(
            CombatTargetConfig(structured_logging_enabled=False)
        )
        track = _Track(1, center=(140.0, 100.0))
        context = SimpleNamespace(state="VISIBLE", appearance=())
        metrics = SimpleNamespace(grid_distance=1)
        player = (100.0, 100.0)

        memory.acquire(
            track,
            context,
            metrics,
            player_center=player,
            now=1.0,
            frame_index=1,
        )
        memory._velocity = (-900.0, 450.0)
        memory.mark_missing(now=1.5, frame_index=5, flow=(-80.0, 50.0))
        predicted = memory.snapshot(now=1.5, frame_index=5).predicted_position

        self.assertIsNotNone(predicted)
        self.assertLessEqual(
            math.dist(player, predicted),
            memory.config.contact_radius * 1.35 + 1e-6,
        )
        self.assertLessEqual(
            math.dist(memory._track_position(track), predicted),
            memory.config.local_rebind_radius * 0.65 + 1e-6,
        )

    def test_melee_rebind_requires_visible_d1_and_rejects_far_track(self):
        memory = HardenedCombatTargetMemory(
            CombatTargetConfig(structured_logging_enabled=False)
        )
        visible = SimpleNamespace(state="VISIBLE", appearance=())
        occluded = SimpleNamespace(state="OCCLUDED", appearance=())
        player = (100.0, 100.0)
        memory.acquire(
            _Track(1, center=(135.0, 100.0)),
            visible,
            SimpleNamespace(grid_distance=1),
            player_center=player,
            now=1.0,
            frame_index=1,
        )

        close_score = memory.rebind_score(
            _Track(2, center=(130.0, 100.0)),
            visible,
            SimpleNamespace(grid_distance=1),
            player_center=player,
        )
        occluded_score = memory.rebind_score(
            _Track(3, center=(130.0, 100.0)),
            occluded,
            SimpleNamespace(grid_distance=1),
            player_center=player,
        )
        far_score = memory.rebind_score(
            _Track(4, center=(250.0, 100.0)),
            visible,
            SimpleNamespace(grid_distance=5),
            player_center=player,
        )

        self.assertGreaterEqual(close_score, 0.82)
        self.assertEqual(occluded_score, 0.0)
        self.assertLessEqual(far_score, 0.10)

    def test_rebind_needs_two_consecutive_visible_frames(self):
        memory = HardenedCombatTargetMemory(
            CombatTargetConfig(structured_logging_enabled=False)
        )
        visible = SimpleNamespace(state="VISIBLE", appearance=())
        player = (100.0, 100.0)
        memory.acquire(
            _Track(1, center=(140.0, 100.0)),
            visible,
            SimpleNamespace(grid_distance=1),
            player_center=player,
            now=1.0,
            frame_index=1,
        )
        memory.mark_missing(now=1.4, frame_index=4)
        rebound = _Track(7, center=(144.0, 100.0))
        tracker = _Tracker({7: "VISIBLE"})
        observer = _Observer({7: 1})

        first, first_score = memory.choose_local_rebind(
            [rebound],
            tracker=tracker,
            observer=observer,
            player_center=player,
        )
        second, second_score = memory.choose_local_rebind(
            [rebound],
            tracker=tracker,
            observer=observer,
            player_center=player,
        )

        self.assertIsNone(first)
        self.assertGreaterEqual(first_score, memory.config.minimum_rebind_score)
        self.assertIs(second, rebound)
        self.assertEqual(second_score, first_score)

    def test_round_video_is_sampled_by_wall_clock_instead_of_every_observer_frame(self):
        recorder = _Recorder()
        install_round_video_performance_guard(recorder, target_fps=2.0)

        with patch(
            "pc_agent.kage_pilot.dojo_round_video_performance_v351.time.monotonic",
            side_effect=(10.0, 10.1, 10.49, 10.51),
        ):
            results = [
                recorder.record(None, None, None),
                recorder.record(None, None, None),
                recorder.record(None, None, None),
                recorder.record(None, None, None),
            ]

        self.assertEqual(results, [True, False, False, True])
        self.assertEqual(recorder.calls, 2)
        self.assertEqual(recorder.skipped_observer_frames, 2)
        self.assertEqual(recorder.fps, 2.0)


if __name__ == "__main__":
    unittest.main()
