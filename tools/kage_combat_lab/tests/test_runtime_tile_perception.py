from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from kage_combat_lab.domain import CombatFrame, GridCell
from kage_combat_lab.hostility_gate import GateSnapshot
from kage_combat_lab.runtime_tile_perception import install_runtime_tile_perception


class _FakeTargetMemory:
    ready = False

    def enrich_candidates(self, *, frame_bgr, state, candidates, timestamp):
        return tuple(candidates)


class _FakeGate:
    def __init__(self) -> None:
        self.last_snapshot = GateSnapshot()
        self.last_overlay_frame = None

    def filter_candidates(
        self,
        *,
        frame_bgr,
        state,
        observer,
        candidates,
        evidence,
        now,
    ):
        return tuple(candidates)

    def consume_console_events(self):
        return ()

    def consume_video_events(self):
        return ()


def _install_fakes(monkeypatch, tmp_path):
    import kage_combat_lab.runtime_tile_perception as runtime_module

    calibration = tmp_path / "grid.json"
    calibration.write_text(
        json.dumps({"offset_x_px": 7, "offset_y_px": 11}),
        encoding="utf-8",
    )

    class _FakePerception:
        terrain_example_count = 1

        def __init__(self) -> None:
            self.config = SimpleNamespace(calibration_path=calibration)
            self.last_summary = {"cells": 4, "unknown": 1, "active_unknown": 1}
            self.last_evidence = {}

        def scan(self, *, frame_bgr, state, observer):
            self.last_evidence = {}
            return {}

    runtime_module._INSTALLED = False
    runtime_module._RUNTIME = None
    runtime_module._HOSTILITY_GATE = None
    monkeypatch.setattr(runtime_module, "PR24CombatTilePerception", _FakePerception)
    monkeypatch.setattr(runtime_module, "PR26HostilityGate", _FakeGate)
    return runtime_module


def test_runtime_patch_requires_full_tile_inputs(monkeypatch, tmp_path) -> None:
    _install_fakes(monkeypatch, tmp_path)
    bridge = SimpleNamespace(
        combat_frame_from_observer_state=lambda *args, **kwargs: CombatFrame(
            frame_index=0,
            player_cell=GridCell(0, 0),
            candidates=(),
        )
    )
    install_runtime_tile_perception(bridge)

    try:
        bridge.combat_frame_from_observer_state()
    except RuntimeError as exc:
        assert "PR26_TILE_PIPELINE_REQUIRES" in str(exc)
    else:
        raise AssertionError("runtime patch must fail closed without tile inputs")


def test_runtime_patch_restores_target_memory_method_and_grid_origin(
    monkeypatch,
    tmp_path,
) -> None:
    _install_fakes(monkeypatch, tmp_path)
    memory = _FakeTargetMemory()
    original_method = memory.enrich_candidates
    observed_origin = []

    def original(*args, **kwargs):
        observer = kwargs["observer"]
        observed_origin.append((observer.grid_origin_x, observer.grid_origin_y))
        kwargs["target_memory"].enrich_candidates(
            frame_bgr=kwargs["frame_bgr"],
            state=kwargs["state"],
            candidates=(),
            timestamp=0.0,
        )
        return CombatFrame(frame_index=0, player_cell=GridCell(0, 0), candidates=())

    bridge = SimpleNamespace(combat_frame_from_observer_state=original)
    install_runtime_tile_perception(bridge)
    observer = SimpleNamespace(grid_origin_x=1.0, grid_origin_y=2.0)
    bridge.combat_frame_from_observer_state(
        observer=observer,
        state=SimpleNamespace(arena_rect=(3, 5, 64, 64), player_center=(32.0, 32.0)),
        frame_bgr=np.zeros((64, 64, 3), dtype=np.uint8),
        target_memory=memory,
    )

    assert observed_origin == [((7 - 3) % 64, (11 - 5) % 64)]
    assert observer.grid_origin_x == 1.0
    assert observer.grid_origin_y == 2.0
    assert memory.enrich_candidates == original_method
