from __future__ import annotations

from pathlib import Path

import pytest

from kage_combat_lab.tile_perception import TilePerceptionConfig


def test_tile_config_rejects_noncanonical_ranges() -> None:
    with pytest.raises(ValueError):
        TilePerceptionConfig(Path("."), similarity_threshold=0.40).normalized()
    with pytest.raises(ValueError):
        TilePerceptionConfig(Path("."), novelty_threshold=0.0).normalized()
    with pytest.raises(ValueError):
        TilePerceptionConfig(Path("."), temporal_activity_threshold=1.5).normalized()
