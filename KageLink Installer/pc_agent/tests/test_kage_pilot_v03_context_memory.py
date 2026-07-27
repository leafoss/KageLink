from __future__ import annotations

import unittest

import numpy as np

from pc_agent.kage_pilot.entity_observer import Candidate, FlowEstimate
from pc_agent.kage_pilot.entity_tracker_v03 import (
    DynamicBackgroundMemory,
    MeleeAwareEntityTracker,
    _appearance_signature,
    appearance_similarity,
)
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig, player_box_rect


def candidate(x: float, y: float, *, w: int = 18, h: int = 38) -> Candidate:
    return Candidate(
        bbox=(round(x - w / 2), round(y - h / 2), w, h),
        center=(x, y),
        contour_area=float(w * h * 0.62),
        motion_energy=0.35,
        edge_density=0.22,
        shape_score=0.92,
    )


class KagePilotV03ContextMemoryTests(unittest.TestCase):
    def test_appearance_signature_is_stable_for_same_patch(self):
        frame = np.zeros((120, 160), dtype=np.uint8)
        frame[30:70, 50:70] = 180
        frame[38:62, 56:64] = 40
        bbox = (50, 30, 20, 40)
        first = _appearance_signature(frame, bbox)
        second = _appearance_signature(frame.copy(), bbox)
        self.assertTrue(first)
        self.assertGreater(appearance_similarity(first, second), 0.99)

    def test_dynamic_background_learns_dense_repetitive_region(self):
        config = V03ObserverConfig(
            background_min_neighbors=2,
            background_min_dense_hits=3,
            background_min_age=0.2,
            background_similarity=0.80,
            background_player_guard=20,
        ).normalized()
        memory = DynamicBackgroundMemory(config)
        group = [candidate(220, 60), candidate(242, 62), candidate(264, 61)]
        signature = (1.0, 0.0, 0.0, 0.0)
        signatures = [signature, signature, signature]

        memory.observe_and_filter(group, signatures, player_center=(20.0, 100.0), now=0.0)
        memory.observe_and_filter(group, signatures, player_center=(20.0, 100.0), now=0.1)
        filtered, _ = memory.observe_and_filter(
            group,
            signatures,
            player_center=(20.0, 100.0),
            now=0.3,
        )

        self.assertGreater(memory.mature_cells, 0)
        self.assertLess(len(filtered), len(group))
        self.assertGreater(memory.suppressed_last_frame, 0)

    def test_isolated_candidate_is_not_learned_as_dynamic_background(self):
        config = V03ObserverConfig(
            background_min_neighbors=2,
            background_min_dense_hits=2,
            background_min_age=0.1,
            background_similarity=0.80,
            background_player_guard=20,
        ).normalized()
        memory = DynamicBackgroundMemory(config)
        single = [candidate(220, 60)]
        signatures = [(1.0, 0.0, 0.0, 0.0)]
        for index in range(12):
            filtered, _ = memory.observe_and_filter(
                single,
                signatures,
                player_center=(20.0, 100.0),
                now=index * 0.1,
            )
            self.assertEqual(len(filtered), 1)
        self.assertEqual(memory.mature_cells, 0)

    def test_player_contact_becomes_occluded_and_stays_outside_player_box(self):
        config = V03ObserverConfig(
            player_box_width=18,
            player_box_height=38,
            track_match_distance=105,
        ).normalized()
        tracker = MeleeAwareEntityTracker(config)
        player = (100.0, 100.0)

        tracker.update([candidate(145.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.0)
        track_id = tracker.tracks[0].track_id
        tracker.update([candidate(105.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.3)

        self.assertEqual(tracker.tracks[0].track_id, track_id)
        context = tracker.context_for(track_id)
        self.assertEqual(context.state, "OCCLUDED")
        self.assertEqual(context.relative_side, "RIGHT")

        px, py, pw, ph = player_box_rect(player, config)
        tx, ty, tw, th = tracker.tracks[0].bbox
        overlap_w = max(0, min(px + pw, tx + tw) - max(px, tx))
        overlap_h = max(0, min(py + ph, ty + th) - max(py, ty))
        self.assertEqual(overlap_w * overlap_h, 0)

    def test_dormant_identity_reacquires_same_id(self):
        config = V03ObserverConfig(
            track_ttl_seconds=0.5,
            reacquire_ttl=3.0,
            reacquire_distance=160,
            reacquire_similarity=0.70,
            dynamic_background_enabled=False,
        ).normalized()
        tracker = MeleeAwareEntityTracker(config)
        player = (20.0, 100.0)

        tracker.update([candidate(180.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.0)
        tracker.update([candidate(170.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.2)
        tracker.update([candidate(160.0, 100.0)], flow=FlowEstimate(), player_center=player, now=0.4)
        track_id = tracker.tracks[0].track_id

        tracker.update([], flow=FlowEstimate(), player_center=player, now=1.0)
        self.assertEqual(len(tracker.tracks), 0)
        self.assertEqual(tracker.dormant_count, 1)

        tracker.update([candidate(150.0, 100.0)], flow=FlowEstimate(), player_center=player, now=1.1)
        self.assertEqual(len(tracker.tracks), 1)
        self.assertEqual(tracker.tracks[0].track_id, track_id)
        self.assertEqual(tracker.context_for(track_id).state, "VISIBLE")


if __name__ == "__main__":
    unittest.main()
