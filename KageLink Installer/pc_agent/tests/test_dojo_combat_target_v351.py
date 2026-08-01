from __future__ import annotations

from types import SimpleNamespace
import tempfile
import unittest

import numpy as np

from pc_agent.kage_pilot.combat_target_v351 import (
    CombatTargetConfig,
    CombatTargetState,
    PersistentCombatTargetMemory,
    effect_rejection_reason,
    load_combat_target_config,
)
from pc_agent.kage_pilot.dojo_combat_vision_v351 import annotate_combat_diagnostics


class _Track:
    def __init__(
        self,
        track_id: int,
        center=(140.0, 100.0),
        bbox=None,
        velocity=(0.0, 0.0),
    ) -> None:
        self.track_id = track_id
        self.center = center
        # Test geometry must move with the requested visual centre now that combat
        # position is correctly anchored to the bbox feet instead of track.center.
        if bbox is None:
            bbox = (
                int(round(float(center[0]) - 18.0)),
                int(round(float(center[1]) - 28.0)),
                36,
                56,
            )
        self.bbox = bbox
        self.residual_velocity = velocity
        self.enemy_score = 80.0
        self.shape_score = 0.8


class _Context:
    def __init__(self, state="VISIBLE", appearance=()) -> None:
        self.state = state
        self.appearance = appearance


class _Metrics:
    def __init__(self, distance=1) -> None:
        self.grid_distance = distance


class _Tracker:
    def __init__(self, contexts) -> None:
        self.contexts = contexts

    def context_for(self, track_id):
        return self.contexts[track_id]


class _Observer:
    def __init__(self, metrics) -> None:
        self.metrics = metrics

    def metrics_for(self, track_id):
        return self.metrics.get(track_id)


class DojoCombatTargetV351Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = CombatTargetConfig(
            contact_hold_seconds=2.0,
            local_rebind_seconds=1.0,
            hard_lost_timeout=3.0,
            direction_confirm_frames=3,
            target_switch_confirm_frames=3,
            structured_logging_enabled=False,
        )
        self.player = (100.0, 100.0)

    def _memory(self):
        return PersistentCombatTargetMemory(self.config)

    def test_short_visual_loss_keeps_same_logical_target(self):
        memory = self._memory()
        memory.acquire(
            _Track(11),
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=10.0,
            frame_index=80,
        )
        logical_id = memory.combat_target_id
        memory.mark_missing(now=10.5, frame_index=84)
        snapshot = memory.snapshot(now=10.5, frame_index=84)
        self.assertEqual(snapshot.combat_target_id, logical_id)
        self.assertEqual(
            snapshot.target_state,
            CombatTargetState.OCCLUDED_PREDICTED.value,
        )
        self.assertTrue(snapshot.active)

    def test_zero_candidates_does_not_immediately_lose_target(self):
        memory = self._memory()
        memory.acquire(
            _Track(1),
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=0.0,
            frame_index=1,
        )
        for frame in range(2, 10):
            memory.mark_missing(now=frame / 8.0, frame_index=frame)
        self.assertNotEqual(memory.state, CombatTargetState.LOST)
        self.assertEqual(memory.combat_target_id, 1)

    def test_new_visual_track_rebinds_to_same_combat_target(self):
        memory = self._memory()
        first = _Track(11, center=(142.0, 100.0))
        memory.acquire(
            first,
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=1.0,
            frame_index=8,
        )
        logical_id = memory.combat_target_id
        memory.mark_missing(now=1.6, frame_index=13)
        rebound = _Track(37, center=(146.0, 101.0))
        score = memory.rebind_score(
            rebound,
            _Context(),
            _Metrics(1),
            player_center=self.player,
        )
        memory.observe(
            rebound,
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=1.75,
            frame_index=14,
            rebound=True,
            rebind_score=score,
        )
        snapshot = memory.snapshot(now=1.75, frame_index=14)
        self.assertEqual(snapshot.combat_target_id, logical_id)
        self.assertEqual(snapshot.current_visual_track_id, 37)
        self.assertEqual(snapshot.target_state, CombatTargetState.CONTACT.value)

    def test_distant_candidate_is_not_local_rebind_during_contact(self):
        memory = self._memory()
        memory.acquire(
            _Track(3),
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=1.0,
            frame_index=8,
        )
        memory.mark_missing(now=1.8, frame_index=14)
        far = _Track(99, center=(360.0, 100.0))
        tracker = _Tracker({99: _Context()})
        observer = _Observer({99: _Metrics(6)})
        selected, score = memory.choose_local_rebind(
            [far],
            tracker=tracker,
            observer=observer,
            player_center=self.player,
        )
        self.assertIsNone(selected)
        self.assertEqual(score, 0.0)

    def test_direction_does_not_invert_after_one_frame(self):
        memory = self._memory()
        memory.acquire(
            _Track(1, center=(145.0, 100.0)),
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=1.0,
            frame_index=1,
        )
        memory.observe(
            _Track(1, center=(55.0, 100.0)),
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=1.1,
            frame_index=2,
        )
        self.assertEqual(
            memory.snapshot(now=1.1, frame_index=2).last_contact_direction,
            "RIGHT",
        )

    def test_direction_changes_after_consistent_confirmation(self):
        memory = self._memory()
        memory.acquire(
            _Track(1, center=(145.0, 100.0)),
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=1.0,
            frame_index=1,
        )
        for index in range(3):
            memory.observe(
                _Track(1, center=(55.0, 100.0)),
                _Context(),
                _Metrics(1),
                player_center=self.player,
                now=1.1 + index * 0.1,
                frame_index=2 + index,
            )
        self.assertEqual(
            memory.snapshot(now=1.4, frame_index=5).last_contact_direction,
            "LEFT",
        )

    def test_movement_mode_switches_between_melee_and_pursuit(self):
        memory = self._memory()
        memory.acquire(
            _Track(2, center=(220.0, 100.0)),
            _Context(),
            _Metrics(4),
            player_center=self.player,
            now=1.0,
            frame_index=1,
        )
        self.assertEqual(
            memory.snapshot(now=1.0, frame_index=1).movement_mode,
            "PURSUIT",
        )
        memory.observe(
            _Track(2, center=(140.0, 100.0)),
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=1.2,
            frame_index=2,
        )
        self.assertEqual(
            memory.snapshot(now=1.2, frame_index=2).movement_mode,
            "MELEE_LOCK",
        )

    def test_hard_lost_requires_full_timeout(self):
        memory = self._memory()
        memory.acquire(
            _Track(2),
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=2.0,
            frame_index=16,
        )
        memory.mark_missing(now=4.99, frame_index=39)
        self.assertNotEqual(memory.state, CombatTargetState.LOST)
        memory.mark_missing(now=5.0, frame_index=40)
        self.assertEqual(memory.state, CombatTargetState.LOST)

    def test_target_switch_requires_multiple_frames(self):
        memory = self._memory()
        self.assertFalse(memory.propose_switch(20))
        self.assertFalse(memory.propose_switch(20))
        self.assertTrue(memory.propose_switch(20))

    def test_horizontal_effect_is_rejected(self):
        candidate = SimpleNamespace(bbox=(180, 120, 180, 16))
        reason = effect_rejection_reason(
            candidate,
            frame_shape=(600, 900),
            flow=SimpleNamespace(dx=0.0, dy=0.0),
            player_center=self.player,
            config=self.config,
        )
        self.assertEqual(reason, "TOO_HORIZONTAL")

    def test_camera_flow_wide_blob_is_rejected(self):
        candidate = SimpleNamespace(bbox=(100, 120, 320, 80))
        reason = effect_rejection_reason(
            candidate,
            frame_shape=(600, 900),
            flow=SimpleNamespace(dx=-12.0, dy=0.0),
            player_center=self.player,
            config=self.config,
        )
        self.assertEqual(reason, "CAMERA_FLOW")

    def test_config_weights_are_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/config.json"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    '{"combat_target":{"distance_weight":0.9,"size_weight":0.1,'
                    '"appearance_weight":0,"movement_weight":0}}'
                )
            config = load_combat_target_config(path)
        self.assertAlmostEqual(config.distance_weight, 0.9)
        self.assertAlmostEqual(config.size_weight, 0.1)

    def test_debug_annotation_does_not_mutate_source_frame_or_state(self):
        memory = self._memory()
        memory.acquire(
            _Track(7),
            _Context(),
            _Metrics(1),
            player_center=self.player,
            now=1.0,
            frame_index=1,
        )
        snapshot = memory.snapshot(now=1.0, frame_index=1)
        observer = SimpleNamespace(
            combat_snapshot=lambda: snapshot,
            tracker=SimpleNamespace(
                raw_candidate_count=0,
                filtered_candidate_count=0,
                rejected_candidates=(),
            ),
        )
        state = SimpleNamespace(
            arena_rect=(0, 0, 960, 540),
            player_center=self.player,
            tracks=(),
            global_flow=SimpleNamespace(dx=0.0, dy=0.0, points=0),
        )
        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame_before = frame.copy()
        state_before = dict(state.__dict__)
        annotated = annotate_combat_diagnostics(canvas, frame, state, observer)
        self.assertTrue(np.array_equal(frame, frame_before))
        self.assertEqual(state.__dict__, state_before)
        self.assertFalse(np.array_equal(annotated, canvas))


if __name__ == "__main__":
    unittest.main()
