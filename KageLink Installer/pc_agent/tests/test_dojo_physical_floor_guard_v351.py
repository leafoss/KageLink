from __future__ import annotations

from types import SimpleNamespace
import unittest

from pc_agent.kage_pilot.combat_strategy_v351 import (
    AttackVisualContext,
    CombatStrategyFrame,
    GridObservation,
    ObservationClass,
)
from pc_agent.kage_pilot.dojo_physical_floor_guard_v351 import (
    _body_size_compatible,
    _camera_shift_freeze_required,
    _contact_candidate_is_safe,
)


def observation(
    *,
    track_id: int = 7,
    cell: tuple[int, int] = (4, 3),
    context_state: str = "OCCLUDED",
    classification: str = ObservationClass.UNKNOWN_BLOB.value,
    body_size: tuple[float, float] = (30.0, 42.0),
) -> GridObservation:
    return GridObservation(
        frame_index=3,
        timestamp=0.4,
        track_id=track_id,
        anchor_cell=cell,
        bbox_cells=frozenset({cell}),
        visible=context_state == "VISIBLE",
        body_like=False,
        contaminated=True,
        enemy_score=78.0,
        body_size=body_size,
        body_cell_coverage=0.70,
        classification=classification,
        context_state=context_state,
        anchor_point=(145.0, 118.0),
    )


def frame(
    item: GridObservation,
    *,
    timestamp: float = 0.4,
    motion_burst: bool = False,
    attack: AttackVisualContext | None = None,
) -> CombatStrategyFrame:
    return CombatStrategyFrame(
        frame_index=3,
        timestamp=timestamp,
        player_cell=(4, 4),
        observations=(item,),
        attack_context=attack,
        motion_burst=motion_burst,
    )


def target(**changes):
    values = {
        "clean_visual_track_id": 7,
        "confirmed_cell": (4, 3),
        "last_clean_seen_at": 0.0,
        "body_size": (30.0, 42.0),
    }
    values.update(changes)
    return SimpleNamespace(**values)


class PhysicalFloorGuardV351Tests(unittest.TestCase):
    def test_camera_shift_freezes_new_track_creation(self):
        flow = SimpleNamespace(dx=12.0, dy=0.0)
        self.assertTrue(
            _camera_shift_freeze_required(flow, cell_size=32.0)
        )

    def test_small_flow_does_not_freeze_normal_tracking(self):
        flow = SimpleNamespace(dx=3.0, dy=2.0)
        self.assertFalse(
            _camera_shift_freeze_required(
                flow,
                cell_size=32.0,
                candidate_count=6,
                active_cells=8,
                track_count=5,
            )
        )

    def test_candidate_explosion_freezes_new_tracks(self):
        flow = SimpleNamespace(dx=0.0, dy=0.0)
        self.assertTrue(
            _camera_shift_freeze_required(
                flow,
                cell_size=64.0,
                candidate_count=40,
            )
        )

    def test_brief_same_track_occlusion_in_confirmed_cell_is_safe(self):
        item = observation()
        self.assertTrue(
            _contact_candidate_is_safe(
                frame=frame(item),
                target=target(),
                candidate=item,
            )
        )

    def test_visible_floor_blob_cannot_use_contact_memory(self):
        item = observation(context_state="VISIBLE")
        self.assertFalse(
            _contact_candidate_is_safe(
                frame=frame(item),
                target=target(),
                candidate=item,
            )
        )

    def test_occluded_blob_outside_confirmed_cell_is_rejected(self):
        item = observation(cell=(4, 4))
        self.assertFalse(
            _contact_candidate_is_safe(
                frame=frame(item),
                target=target(),
                candidate=item,
            )
        )

    def test_own_attack_corridor_cannot_renew_contact(self):
        item = observation()
        attack = AttackVisualContext(
            attack_id=2,
            started_at=0.1,
            origin_cell=(4, 4),
            direction="UP",
            expected_cells=frozenset({(4, 3), (4, 2)}),
            expires_at=0.95,
        )
        self.assertFalse(
            _contact_candidate_is_safe(
                frame=frame(item, attack=attack),
                target=target(),
                candidate=item,
            )
        )

    def test_camera_burst_cannot_renew_contact(self):
        item = observation()
        self.assertFalse(
            _contact_candidate_is_safe(
                frame=frame(item, motion_burst=True),
                target=target(),
                candidate=item,
            )
        )

    def test_contact_memory_expires_after_seven_tenths(self):
        item = observation()
        self.assertFalse(
            _contact_candidate_is_safe(
                frame=frame(item, timestamp=0.71),
                target=target(last_clean_seen_at=0.0),
                candidate=item,
            )
        )

    def test_floor_sized_fragment_is_not_body_compatible(self):
        self.assertFalse(_body_size_compatible((30.0, 42.0), (48.0, 10.0)))


if __name__ == "__main__":
    unittest.main()
