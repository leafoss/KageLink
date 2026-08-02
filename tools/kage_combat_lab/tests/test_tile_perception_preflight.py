from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from kage_combat_lab.tile_perception import TileFeatureExtractor


def test_pr24_feature_vector_shape_is_stable() -> None:
    crop = np.zeros((60, 60, 3), dtype=np.uint8)
    crop[:, :30] = (10, 40, 80)
    crop[:, 30:] = (90, 120, 160)
    feature = TileFeatureExtractor().extract(crop)
    assert feature.shape == (134,)
    assert abs(float(np.linalg.norm(feature)) - 1.0) < 1e-5


def test_pr24_persisted_feature_remains_json_serializable(tmp_path: Path) -> None:
    crop = np.zeros((64, 64, 3), dtype=np.uint8)
    cv2.circle(crop, (32, 32), 12, (255, 255, 255), -1)
    feature = TileFeatureExtractor().extract(crop[2:-2, 2:-2]).tolist()
    path = tmp_path / "knowledge.json"
    path.write_text(json.dumps({"feature": feature}), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))["feature"]
    assert len(loaded) == 134
