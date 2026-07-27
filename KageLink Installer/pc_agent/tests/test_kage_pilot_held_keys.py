from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from pc_agent.kage_pilot.dataset import DatasetStore, SessionWriter
from pc_agent.kage_pilot.learning import BehaviorCloner
from pc_agent.kage_pilot.pilot import Pilot


def jpeg(level: int) -> bytes:
    image = Image.new("L", (64, 36), level)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


class FakeFrameSource:
    def __init__(self, frame: bytes):
        self.frame = frame

    def capture(self):
        return SimpleNamespace(jpeg=self.frame)


class FakeController:
    def __init__(self):
        self.events = []

    def activate(self):
        self.events.append(("activate",))

    def apply_keys(self, keys):
        self.events.append(("keys", tuple(keys)))

    def release_all(self):
        self.events.append(("release",))

    def tap(self, key, duration=0.08):
        self.events.append(("tap", key, duration))

    def click_normalized(self, x, y):
        self.events.append(("click", x, y))


class KagePilotHeldKeyTests(unittest.TestCase):
    def test_action_runs_remove_held_key_duration_bias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            writer = SessionWriter(root, session_id="fight", started_at=0.0)
            writer.append(jpeg(20), timestamp=0.0, keys=("r",))
            writer.append(jpeg(30), timestamp=0.1, keys=("r",))
            writer.append(jpeg(240), timestamp=0.2, keys=("r", "right"))
            writer.append(jpeg(245), timestamp=0.3, keys=("r", "right"))
            writer.append(jpeg(40), timestamp=0.4, keys=("r",))
            writer.append(jpeg(120), timestamp=0.5, keys=("h", "r"))
            writer.finalize("victory", ended_at=0.6)

            model = BehaviorCloner.train(
                DatasetStore(root),
                include_idle=False,
                exclude_keys=("r",),
                use_action_runs=True,
            )

            self.assertEqual(model.counts, {"right": 1, "h": 1})
            self.assertNotIn("r", model.prototypes)

    def test_pilot_keeps_base_key_while_applying_prediction(self):
        model = BehaviorCloner({"left": [0.0] * 144}, {"left": 1})
        controller = FakeController()
        pilot = Pilot(
            model,
            FakeFrameSource(jpeg(0)),
            controller,
            base_keys=("r",),
            min_confidence=0.0,
        )

        step = pilot.step()

        self.assertEqual(step.applied_keys, ("left", "r"))
        self.assertIn(("keys", ("left", "r")), controller.events)


if __name__ == "__main__":
    unittest.main()
