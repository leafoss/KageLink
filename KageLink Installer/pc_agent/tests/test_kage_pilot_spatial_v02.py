from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pc_agent.kage_pilot.dataset import DatasetStore, SessionWriter
from pc_agent.kage_pilot.learning_spatial_v2 import (
    FEATURE_MODE,
    FeatureScaler,
    SpatialCombatModel,
    SpatialPolicy,
    spatial_features,
)


def scene(player_x: int, enemy_x: int, *, flash: bool = False) -> bytes:
    image = Image.new("L", (320, 180), 35)
    draw = ImageDraw.Draw(image)
    # Static arena geometry/background.
    draw.rectangle((15, 20, 305, 150), outline=70, width=2)
    draw.line((30, 120, 290, 120), fill=55, width=2)
    # Player and opponent are deliberately distinct small high-contrast sprites.
    draw.rectangle((player_x, 82, player_x + 12, 104), fill=215)
    draw.rectangle((enemy_x, 80, enemy_x + 12, 104), fill=150)
    if flash:
        draw.rectangle((enemy_x - 5, 70, enemy_x + 18, 110), outline=245, width=2)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


class SpatialKagePilotTests(unittest.TestCase):
    def test_spatial_features_change_when_relative_positions_change(self):
        close = spatial_features(scene(110, 145), scene(110, 145))
        pushed = spatial_features(scene(110, 145), scene(80, 145))
        self.assertEqual(len(close), len(pushed))
        self.assertGreater(sum(abs(a - b) for a, b in zip(close, pushed)), 1.0)

    def test_scaler_and_policy_keep_distinct_spatial_classes(self):
        idle = spatial_features(scene(110, 145), scene(110, 145))
        right = spatial_features(scene(80, 145), scene(95, 145))
        left = spatial_features(scene(140, 105), scene(125, 105))
        scaler = FeatureScaler.fit([idle, right, left])
        idle_s = scaler.transform(idle)
        right_s = scaler.transform(right)
        left_s = scaler.transform(left)
        policy = SpatialPolicy.from_examples([
            ("idle", idle_s),
            ("right", right_s),
            ("left", left_s),
        ])
        self.assertEqual(policy.predict_features(right_s).label, "right")
        self.assertEqual(policy.predict_features(left_s).label, "left")

    def test_spatial_model_trains_existing_combat_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            writer = SessionWriter(root, session_id="fight", started_at=0.0)
            writer.append(scene(110, 145), timestamp=0.0, keys=("r",))
            writer.append(scene(90, 145), timestamp=0.1, keys=("r", "right"))
            writer.append(scene(110, 145, flash=True), timestamp=0.2, keys=("r", "h"))
            writer.append(scene(135, 105), timestamp=0.3, keys=("r", "left"))
            writer.append(scene(135, 105), timestamp=0.4, keys=("v",))
            writer.finalize("victory", ended_at=0.5)

            model = SpatialCombatModel.train(DatasetStore(root), history_frames=1)
            self.assertEqual(model.base_keys, ("r",))
            self.assertEqual(model.skill_keys, ("h",))
            self.assertEqual(model.post_combat_keys, ("v",))
            self.assertIn("right", model.navigation.counts)
            self.assertIn("left", model.navigation.counts)
            self.assertIn("h", model.skill.counts)
            self.assertNotIn("v", model.skill.counts)

            path = root / "spatial.json"
            model.save(path)
            loaded = SpatialCombatModel.load(path)
            self.assertEqual(loaded.base_keys, ("r",))
            payload = path.read_text(encoding="utf-8")
            self.assertIn(FEATURE_MODE, payload)


if __name__ == "__main__":
    unittest.main()
