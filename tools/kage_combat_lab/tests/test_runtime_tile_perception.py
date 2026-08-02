from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from kage_combat_lab.domain import CombatFrame, GridCell
from kage_combat_lab.runtime_tile_perception import install_runtime_tile_perception


class _FakeTargetMemory:
    ready = False

    def enrich_candidates(self, *, frame_bgr, state, candidates, timestamp):
        return tuple(candidates)


class _FakePerception:
    terrain_example_count = 1
    last_summary = {"cells": 4, "unknown": 1, "active_unknown": 1}

    def enrich_candidates(self, *, frame_bgr, state, observer, candidates, target_memory):
        return tuple(candidates)


def test_runtime_patch_requires_full_tile_inputs(monkeypatch) -> None:
    import kage_combat_lab.runtime_tile_perception as runtime_module

    runtime_module._INSTALLED = False
    runtime_module._RUNTIME = None
    monkeypatch.setattr(runtime_module, "PR24CombatTilePerception", _FakePerception)

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


def test_runtime_patch_restores_target_memory_method(monkeypatch) -> None:
    import kage_combat_lab.runtime_tile_perception as runtime_module

    runtime_module._INSTALLED = False
    runtime_module._RUNTIME = None
    monkeypatch.setattr(runtime_module, "PR24CombatTilePerception", _FakePerception)

    memory = _FakeTargetMemory()
    original_method = memory.enrich_candidates

    def original(*args, **kwargs):
        kwargs["target_memory"].enrich_candidates(
            frame_bgr=kwargs["frame_bgr"],
            state=kwargs["state"],
            candidates=(),
            timestamp=0.0,
        )
        return CombatFrame(frame_index=0, player_cell=GridCell(0, 0), candidates=())

    bridge = SimpleNamespace(combat_frame_from_observer_state=original)
    install_runtime_tile_perception(bridge)
    bridge.combat_frame_from_observer_state(
        observer=SimpleNamespace(grid_origin=(0.0, 0.0)),
        state=SimpleNamespace(arena_rect=(0, 0, 64, 64), player_center=(32.0, 32.0)),
        frame_bgr=np.zeros((64, 64, 3), dtype=np.uint8),
        target_memory=memory,
    )

    assert memory.enrich_candidates == original_method
