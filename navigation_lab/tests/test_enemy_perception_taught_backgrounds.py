from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from navigation_lab.enemy_perception.background_reference import BackgroundReferenceStore
from navigation_lab.enemy_perception.runtime import _seed_backgrounds_from_taught_terrain
from navigation_lab.observer.tile_knowledge import TileClass


class TaughtBackgroundSeedTests(unittest.TestCase):
    def test_only_taught_empty_terrain_crops_seed_catalogue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            walkable_path = root / "walkable.png"
            npc_path = root / "npc.png"
            cv2.imwrite(str(walkable_path), np.full((60, 60, 3), 40, np.uint8))
            cv2.imwrite(str(npc_path), np.full((60, 60, 3), 180, np.uint8))
            knowledge = SimpleNamespace(
                examples=[
                    SimpleNamespace(
                        category=TileClass.WALKABLE,
                        crop_path=str(walkable_path),
                    ),
                    SimpleNamespace(
                        category=TileClass.NPC,
                        crop_path=str(npc_path),
                    ),
                ]
            )
            store = BackgroundReferenceStore(root / "backgrounds")
            added = _seed_backgrounds_from_taught_terrain(store, knowledge, root)
            self.assertEqual(added, 1)
            self.assertEqual(len(store.references_by_class.get("walkable", [])), 1)
            self.assertNotIn("npc", store.references_by_class)

    def test_same_taught_crop_is_not_duplicated_each_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crop_path = root / "walkable.png"
            cv2.imwrite(str(crop_path), np.full((60, 60, 3), 40, np.uint8))
            knowledge = SimpleNamespace(
                examples=[
                    SimpleNamespace(
                        category=TileClass.WALKABLE,
                        crop_path=str(crop_path),
                    )
                ]
            )
            store = BackgroundReferenceStore(root / "backgrounds")
            self.assertEqual(
                _seed_backgrounds_from_taught_terrain(store, knowledge, root),
                1,
            )
            self.assertEqual(
                _seed_backgrounds_from_taught_terrain(store, knowledge, root),
                0,
            )
            self.assertEqual(len(store.references_by_class["walkable"]), 1)


if __name__ == "__main__":
    unittest.main()
