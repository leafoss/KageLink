from __future__ import annotations

from types import SimpleNamespace

from kage_combat_lab.hostility_gate import EntityState, HostilityState
from kage_combat_lab.runtime_target_integrity import (
    CameraStabilityGate,
    has_latched_hostile_memory,
    rawless_orientation_geometry,
)


def test_low_response_camera_jump_is_never_authoritative() -> None:
    gate = CameraStabilityGate(accepted=(3.0, -1.0), initialized=True)
    dx, dy, response, authoritative = gate.evaluate(
        -11.0,
        29.0,
        0.100,
        True,
    )
    assert (dx, dy) == (3.0, -1.0)
    assert response == 0.100
    assert not authoritative
    assert gate.reason == "LOW_RESPONSE_OR_RAW_REJECT"


def test_large_camera_translation_requires_temporal_confirmation() -> None:
    gate = CameraStabilityGate(accepted=(0.0, 0.0), initialized=True)
    first = gate.evaluate(-46.0, 3.0, 0.55, True)
    second = gate.evaluate(-45.0, 4.0, 0.53, True)
    assert not first[3]
    assert second[3]
    assert abs(second[0] + 46.0) <= 1.0
    assert abs(second[1] - 4.0) <= 1.0


def test_small_camera_correction_can_be_accepted_immediately() -> None:
    gate = CameraStabilityGate(accepted=(1.0, -1.0), initialized=True)
    dx, dy, _, authoritative = gate.evaluate(3.0, 0.0, 0.57, True)
    assert authoritative
    assert (dx, dy) == (3.0, 0.0)


def test_physical_25x44_body_can_only_be_an_orientation_hint_without_raw_id() -> None:
    assert rawless_orientation_geometry(
        bbox=(459, 105, 25, 44),
        changed_ratio=0.139,
        largest_blob_area=569,
        cell_count=1,
    )


def test_whole_cell_and_wide_top_artifacts_have_zero_rawless_authority() -> None:
    assert not rawless_orientation_geometry(
        bbox=(538, 42, 64, 64),
        changed_ratio=0.519,
        largest_blob_area=2120,
        cell_count=1,
    )
    assert not rawless_orientation_geometry(
        bbox=(538, 42, 64, 33),
        changed_ratio=0.496,
        largest_blob_area=1900,
        cell_count=1,
    )


def test_reid_memory_requires_raw_body_bound_hostile_latch() -> None:
    hostile_track = SimpleNamespace(
        entity_state=EntityState.ENTITY_CONFIRMED,
        hostility_state=HostilityState.HOSTILE_CONFIRMED,
    )
    valid = SimpleNamespace(
        _pr26_round_target_memory=SimpleNamespace(
            last_raw_track_id=17,
            track=hostile_track,
        )
    )
    rawless = SimpleNamespace(
        _pr26_round_target_memory=SimpleNamespace(
            last_raw_track_id=None,
            track=hostile_track,
        )
    )
    unconfirmed = SimpleNamespace(
        _pr26_round_target_memory=SimpleNamespace(
            last_raw_track_id=17,
            track=SimpleNamespace(
                entity_state=EntityState.ENTITY_CONFIRMED,
                hostility_state=HostilityState.OBSERVE_HOSTILITY,
            ),
        )
    )
    assert has_latched_hostile_memory(valid)
    assert not has_latched_hostile_memory(rawless)
    assert not has_latched_hostile_memory(unconfirmed)
