from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from pc_agent.kage_pilot.dataset import DatasetStore, SessionWriter
from pc_agent.kage_pilot.learning_v2 import PrototypePolicy, TemporalCombatModel, temporal_features
from pc_agent.kage_pilot.pilot_v2 import TemporalCombatPilot


def jpeg(level: int) -> bytes:
    image = Image.new("L", (96, 56), level)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


class FakeFrameSource:
    def __init__(self, frames):
        self.frames = list(frames)
        self.index = 0

    def capture(self):
        frame = self.frames[min(self.index, len(self.frames) - 1)]
        self.index += 1
        return SimpleNamespace(jpeg=frame)


class FakeController:
    def __init__(self):
        self.events = []

    def activate(self): self.events.append(("activate",))
    def apply_keys(self, keys): self.events.append(("keys", tuple(keys)))
    def release_all(self): self.events.append(("release",))
    def tap(self, key, duration=0.08): self.events.append(("tap", key, duration))
    def click_normalized(self, x, y): self.events.append(("click", x, y))


class KagePilotV02Tests(unittest.TestCase):
    def test_temporal_model_separates_navigation_and_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            writer = SessionWriter(root, session_id="fight", started_at=0.0)
            writer.append(jpeg(20), timestamp=0.0, keys=("r",))
            writer.append(jpeg(60), timestamp=0.1, keys=("r", "right"))
            writer.append(jpeg(100), timestamp=0.2, keys=("r", "h"))
            writer.append(jpeg(160), timestamp=0.3, keys=("r", "left"))
            writer.append(jpeg(220), timestamp=0.4, keys=("r", "v"))
            writer.finalize("victory", ended_at=0.5)

            model = TemporalCombatModel.train(
                DatasetStore(root),
                base_keys=("r",),
                skill_keys=("h", "v"),
                history_frames=1,
            )
            self.assertEqual(model.base_keys, ("r",))
            self.assertIn("right", model.navigation.prototypes)
            self.assertIn("left", model.navigation.prototypes)
            self.assertIn("h", model.skill.prototypes)
            self.assertIn("v", model.skill.prototypes)
            self.assertIn("idle", model.skill.prototypes)

            prediction = model.predict(jpeg(20), jpeg(60))
            self.assertEqual(prediction.navigation.keys, ("right",))

            path = root / "v02.json"
            model.save(path)
            loaded = TemporalCombatModel.load(path)
            self.assertEqual(loaded.base_keys, ("r",))
            self.assertEqual(loaded.skill_keys, ("h", "v"))

    def test_temporal_features_include_change(self):
        stationary = temporal_features(jpeg(40), jpeg(40))
        moving = temporal_features(jpeg(40), jpeg(180))
        half = len(stationary) // 2
        self.assertTrue(all(abs(value) < 1e-9 for value in stationary[half:]))
        self.assertTrue(any(abs(value) > 0.1 for value in moving[half:]))

    def test_pilot_holds_r_and_skill_uses_cooldown(self):
        previous = jpeg(10)
        current = jpeg(200)
        features = temporal_features(previous, current)
        nav = PrototypePolicy({"right": features}, {"right": 1})
        skill = PrototypePolicy({"h": features}, {"h": 1})
        model = TemporalCombatModel(nav, skill, base_keys=("r",), skill_keys=("h",))
        source = FakeFrameSource([current, current])
        controller = FakeController()
        clock = iter([10.0, 10.1])
        pilot = TemporalCombatPilot(
            model,
            source,
            controller,
            nav_confidence=0.0,
            skill_confidence=0.0,
            skill_cooldown_seconds=1.0,
            startup_delay_seconds=0.0,
            monotonic_fn=lambda: next(clock),
        )
        pilot._previous_jpeg = previous

        first = pilot.step()
        second = pilot.step()
        self.assertEqual(first.applied_keys, ("h", "r", "right"))
        self.assertEqual(first.skill_fired, ("h",))
        self.assertEqual(second.applied_keys, ("r", "right"))
        self.assertEqual(second.skill_fired, ())


if __name__ == "__main__":
    unittest.main()
