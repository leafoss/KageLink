from __future__ import annotations

from types import SimpleNamespace
import unittest

from pc_agent.kage_pilot.combat_target_filter_v351 import (
    combat_body_rejection_reason,
)
from pc_agent.kage_pilot.dojo_resolution_bridge_v351 import effective_tile_size_for
from pc_agent.kage_pilot.grid_target_observer_v03c import FrameAlignedGridTargetObserver
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig


class _Track:
    def __init__(
        self,
        *,
        bbox,
        center=None,
        history=None,
        shape_score=0.8,
    ) -> None:
        self.track_id = 7
        self.bbox = bbox
        x, y, width, height = bbox
        self.center = center or (x + width / 2.0, y + height / 2.0)
        self.history = list(history or [self.center])
        self.shape_score = shape_score


class DojoFailedPhysicalRoundRegressionV351Tests(unittest.TestCase):
    def test_mode_64_cell_is_64_regardless_of_72x73_trainer_png(self):
        # Template dimensions are deliberately absent from this API. A 72x73 raw
        # Trainer crop controls matching only; mode 64 controls navigation geometry.
        self.assertEqual(effective_tile_size_for("64", 1.0), 64.0)
        self.assertEqual(effective_tile_size_for("32", 1.0), 32.0)

    def test_grid_distance_uses_feet_instead_of_sprite_centres(self):
        config = V03ObserverConfig(
            player_box_width=36.0,
            player_box_height=76.0,
        ).normalized()
        observer = FrameAlignedGridTargetObserver(config, tile_size=64.0)
        observer.grid_origin_x = 0.0
        observer.grid_origin_y = 0.0
        observer.tracker = SimpleNamespace(background=None)

        state = SimpleNamespace(
            arena_rect=(0, 0, 960, 540),
            player_center=(128.0, 128.0),
        )
        # Both sprite centres fall in row 2. Their feet occupy rows 2 and 3,
        # therefore the physical grid distance must be one, not zero.
        track = _Track(
            bbox=(128, 128, 20, 76),
            center=(138.0, 166.0),
            history=[(138.0, 166.0)],
        )

        metrics = observer._metrics(track, state)

        self.assertEqual(metrics.player_cell, (2, 2))
        self.assertEqual(metrics.cell, (2, 3))
        self.assertEqual(metrics.grid_distance, 1)

    def test_horizontal_attack_strip_is_not_a_body(self):
        effect = _Track(bbox=(40, 80, 140, 40))
        reason = combat_body_rejection_reason(
            effect,
            context_state="VISIBLE",
            grid_distance=1,
            player_center=(100.0, 100.0),
            player_box_size=(36.0, 76.0),
            tile_size=64.0,
            frame_shape=(420, 900),
            for_acquire=True,
        )
        self.assertIn(reason, {"BODY_TOO_WIDE", "BODY_HORIZONTAL_EFFECT"})

    def test_vertical_attack_column_is_not_a_body(self):
        effect = _Track(bbox=(90, 40, 24, 80))
        reason = combat_body_rejection_reason(
            effect,
            context_state="VISIBLE",
            grid_distance=1,
            player_center=(100.0, 100.0),
            player_box_size=(36.0, 76.0),
            tile_size=64.0,
            frame_shape=(420, 900),
            for_acquire=True,
        )
        self.assertEqual(reason, "BODY_VERTICAL_EFFECT")

    def test_occluded_blob_cannot_acquire_or_rebind_identity(self):
        body = _Track(bbox=(120, 70, 28, 58))
        reason = combat_body_rejection_reason(
            body,
            context_state="OCCLUDED",
            grid_distance=1,
            player_center=(100.0, 100.0),
            player_box_size=(36.0, 76.0),
            tile_size=64.0,
            for_acquire=False,
        )
        self.assertEqual(reason, "BODY_NOT_VISIBLE")

    def test_new_d0_candidate_cannot_become_the_enemy(self):
        body = _Track(bbox=(90, 65, 24, 56))
        reason = combat_body_rejection_reason(
            body,
            context_state="VISIBLE",
            grid_distance=0,
            player_center=(100.0, 100.0),
            player_box_size=(36.0, 76.0),
            tile_size=64.0,
            for_acquire=True,
        )
        self.assertEqual(reason, "BODY_SELF_CELL")

    def test_weak_shape_near_player_does_not_gain_contact_authority(self):
        blob = _Track(bbox=(120, 80, 28, 50), shape_score=0.12)
        reason = combat_body_rejection_reason(
            blob,
            context_state="VISIBLE",
            grid_distance=1,
            player_center=(100.0, 100.0),
            player_box_size=(36.0, 76.0),
            tile_size=64.0,
            for_acquire=True,
        )
        self.assertEqual(reason, "BODY_SHAPE_WEAK")


if __name__ == "__main__":
    unittest.main()
