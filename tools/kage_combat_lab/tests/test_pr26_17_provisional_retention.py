from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kage_combat_lab.hostility_gate import EntityState, HostilityState
from kage_combat_lab.runtime_provisional_target_retention import (
    nearest_phase_alias,
    provisional_body_hold_allowed,
    valid_round_target_latch,
)


ROOT = Path(__file__).resolve().parents[1]


def test_repeating_dojo_phase_aliases_unwrap_to_accepted_viewport() -> None:
    assert nearest_phase_alias(-64.0, 2.0) == 0.0
    assert nearest_phase_alias(-96.0, 2.0) == 0.0
    assert nearest_phase_alias(33.6, 0.0) == pytest.approx(1.6)


def test_ordinary_small_camera_measurement_is_not_rewritten() -> None:
    assert nearest_phase_alias(6.6, 0.0) == 6.6
    assert nearest_phase_alias(2.8, 2.0) == 2.8


def test_provisional_body_grace_survives_one_or_two_detector_gaps() -> None:
    assert provisional_body_hold_allowed(
        last_raw_at=10.0,
        now=12.8,
        valid_latch=False,
        track_exists=True,
    )


def test_provisional_body_grace_cannot_become_permanent_or_replace_latch() -> None:
    assert not provisional_body_hold_allowed(
        last_raw_at=10.0,
        now=13.1,
        valid_latch=False,
        track_exists=True,
    )
    assert not provisional_body_hold_allowed(
        last_raw_at=10.0,
        now=10.5,
        valid_latch=True,
        track_exists=True,
    )
    assert not provisional_body_hold_allowed(
        last_raw_at=10.0,
        now=10.5,
        valid_latch=False,
        track_exists=False,
    )


def test_valid_round_latch_requires_body_bound_hostile_memory() -> None:
    hostile = SimpleNamespace(
        entity_state=EntityState.ENTITY_CONFIRMED,
        hostility_state=HostilityState.HOSTILE_CONFIRMED,
    )
    gate = SimpleNamespace(
        _pr26_round_target_memory=SimpleNamespace(
            last_raw_track_id=7,
            track=hostile,
        )
    )
    assert valid_round_target_latch(gate)

    gate._pr26_round_target_memory.last_raw_track_id = None
    assert not valid_round_target_latch(gate)


def test_runtime_installs_snapshot_before_occupancy_and_restores_after_close() -> None:
    text = (ROOT / "kage_combat_lab" / "full_round_daynight.py").read_text(
        encoding="utf-8"
    )
    snapshot = text.index("install_event_snapshot_integrity()")
    occupancy = text.index("install_runtime_tile_perception(")
    restore = text.index("install_trigger_frame_json_preservation()")
    assert snapshot < occupancy < restore


def test_runtime_installs_provisional_selector_after_exact_cell_binding() -> None:
    text = (ROOT / "kage_combat_lab" / "full_round_daynight.py").read_text(
        encoding="utf-8"
    )
    exact_cell = text.index("install_exact_cell_acquisition_recovery()")
    provisional = text.index("install_provisional_body_target_retention()")
    assert exact_cell < provisional
