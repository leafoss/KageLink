from __future__ import annotations

from pathlib import Path

import pytest

from kage_combat_lab.tile_perception import PR24CombatTilePerception, TilePerceptionConfig


def test_missing_pr24_data_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="PR26_TILE_DATA_MISSING"):
        PR24CombatTilePerception(
            TilePerceptionConfig(
                data_root=tmp_path,
                profile="default",
                region_id="missing",
            )
        )
