from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from kage_combat_lab.tile_perception import (
    PR24CombatTilePerception,
    TileFeatureExtractor,
    TilePerceptionConfig,
)


def test_player_cell_never_becomes_synthetic_target(tmp_path: Path) -> None:
    root = tmp_path / "data"
    profile = root / "profiles" / "default"
    (profile / "calibrations").mkdir(parents=True)
    (profile / "tile_knowledge").mkdir(parents=True)
    (profile / "calibrations" / "arena_grid.json").write_text(
        json.dumps({"tile_size_px": 64}), encoding="utf-8"
    )
    terrain = np.zeros((64, 64, 3), dtype=np.uint8)
    terrain[:] = 20
    feature = TileFeatureExtractor().extract(terrain[2:-2, 2:-2]).tolist()
    (profile / "tile_knowledge" / "arena.json").write_text(
        json.dumps(
            {"examples": [{"id": "floor", "category": "walkable", "feature": feature}]}
        ),
        encoding="utf-8",
    )
    runtime = PR24CombatTilePerception(
        TilePerceptionConfig(root, "default", "arena", temporal_activity_threshold=0.001)
    )
    state = SimpleNamespace(arena_rect=(0, 0, 64, 64), player_center=(32.0, 32.0))
    observer = SimpleNamespace(grid_origin=(0.0, 0.0))
    base = terrain.copy()
    runtime.enrich_candidates(
        frame_bgr=base,
        state=state,
        observer=observer,
        candidates=[],
        target_memory=SimpleNamespace(ready=False),
    )
    changed = base.copy()
    cv2.rectangle(changed, (20, 10), (42, 55), (255, 255, 255), -1)
    result = runtime.enrich_candidates(
        frame_bgr=changed,
        state=state,
        observer=observer,
        candidates=[],
        target_memory=SimpleNamespace(ready=False),
    )
    assert not result
