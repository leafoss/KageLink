from __future__ import annotations

from types import SimpleNamespace
import unittest

from pc_agent.kage_pilot.combat_lab.scenarios import frame, observation
from pc_agent.kage_pilot.combat_strategy_v351 import (
    CombatStrategyConfig,
    ObservationClass,
)
from pc_agent.kage_pilot.grid_focus_v2_strategy_v351 import (
    GridFocusV2SpatialStrategy,
)
from pc_agent.kage_pilot.grid_target_observer_v03c import (
    FrameAlignedGridTargetObserver,
)
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig


class _Track:
    def __init__(self, bbox):
        self.bbox = bbox
        x, y, width, height = bbox
        self.center = (x + width * 0.5, y + height * 0.5)
        self.history = [self.center]


class GridFocusSpatialAuthorityV351Tests(unittest.TestCase):
    def test_foot_anchor_uses_ninety_percent_of_bbox_height(self):
        track = _Track((100, 50, 20, 40))
        self.assertEqual(
            FrameAlignedGridTargetObserver._track_anchor(track),
            (110.0, 86.0),
        )

    def test_animation_height_change_with_same_bottom_keeps_foot_cell(self):
        observer = FrameAlignedGridTargetObserver(
            V03ObserverConfig().normalized(),
            tile_size=64.0,
        )
        observer.grid_origin_x = 0.0
        observer.grid_origin_y = 0.0
        state = SimpleNamespace(arena_rect=(0, 0, 960, 540))
        standing = _Track((100, 72, 20, 48))
        animated = _Track((100, 64, 20, 56))

        standing_cell = observer._frame_cell(observer._track_anchor(standing), state)
        animated_cell = observer._frame_cell(observer._track_anchor(animated), state)

        self.assertEqual(standing_cell, animated_cell)

    def test_small_shadow_extension_does_not_move_anchor_to_lower_cell(self):
        observer = FrameAlignedGridTargetObserver(
            V03ObserverConfig().normalized(),
            tile_size=64.0,
        )
        observer.grid_origin_x = 0.0
        observer.grid_origin_y = 0.0
        state = SimpleNamespace(arena_rect=(0, 0, 960, 540))
        body = _Track((100, 64, 20, 56))
        body_with_shadow = _Track((100, 64, 20, 62))

        body_cell = observer._frame_cell(observer._track_anchor(body), state)
        shadow_cell = observer._frame_cell(
            observer._track_anchor(body_with_shadow),
            state,
        )

        self.assertEqual(body_cell, shadow_cell)

    def test_one_frame_partial_bbox_contamination_cannot_move_identity(self):
        strategy = GridFocusV2SpatialStrategy(
            CombatStrategyConfig(strategy="grid_focus_v2")
        )
        strategy.update(frame(0, (0, 0), observation(0, 10, (1, 0))))
        acquired = strategy.update(frame(1, (0, 0), observation(1, 10, (1, 0))))
        self.assertEqual(acquired.confirmed_target_cell, (1, 0))

        contaminated_shape = observation(
            2,
            10,
            (2, 0),
            classification=ObservationClass.BODY_SPANS_BORDER.value,
            bbox_cells={(1, 0), (2, 0)},
        )
        pending = strategy.update(frame(2, (0, 0), contaminated_shape))

        self.assertEqual(pending.confirmed_target_cell, (1, 0))
        self.assertEqual(pending.pending_rebind_cell, (2, 0))
        self.assertEqual(pending.pending_rebind_hits, 1)
        self.assertFalse(pending.movement_authority)
        self.assertFalse(pending.attack_authority)

        restored = strategy.update(frame(3, (0, 0), observation(3, 10, (1, 0))))
        self.assertEqual(restored.confirmed_target_cell, (1, 0))
        self.assertIsNone(restored.pending_rebind_cell)

    def test_two_clean_adjacent_hits_confirm_cell_transition(self):
        strategy = GridFocusV2SpatialStrategy(
            CombatStrategyConfig(strategy="grid_focus_v2")
        )
        strategy.update(frame(0, (0, 0), observation(0, 10, (1, 0))))
        acquired = strategy.update(frame(1, (0, 0), observation(1, 10, (1, 0))))
        target_id = acquired.combat_target_id

        first = strategy.update(frame(2, (0, 0), observation(2, 10, (2, 0))))
        second = strategy.update(frame(3, (0, 0), observation(3, 10, (2, 0))))

        self.assertEqual(first.confirmed_target_cell, (1, 0))
        self.assertEqual(second.confirmed_target_cell, (2, 0))
        self.assertEqual(second.combat_target_id, target_id)
        self.assertEqual(second.last_contact_direction, "RIGHT")


if __name__ == "__main__":
    unittest.main()
