from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from pc_agent.kage_pilot.dataset import DatasetStore, SessionWriter
from pc_agent.kage_pilot.dojo import DojoConfig, DojoManager, TemplateRule, VisualTemplateDetector
from pc_agent.kage_pilot.learning import BehaviorCloner
from pc_agent.kage_pilot.pilot import Pilot
from pc_agent.kage_pilot.recorder import InputSnapshot, Recorder


def jpeg(level: int) -> bytes:
    image = Image.new("L", (64, 36), level)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


class FakeFrameSource:
    def __init__(self, frames):
        self.frames = list(frames)
        self.index = 0

    def capture(self):
        value = self.frames[min(self.index, len(self.frames) - 1)]
        self.index += 1
        return SimpleNamespace(jpeg=value, target=SimpleNamespace(left=0, top=0, width=100, height=100))


class FakeInput:
    def __init__(self, states):
        self.states = list(states)
        self.index = 0

    def snapshot(self, target=None):
        value = self.states[min(self.index, len(self.states) - 1)]
        self.index += 1
        return value


class FakeController:
    def __init__(self):
        self.events = []

    def activate(self): self.events.append(("activate",))
    def apply_keys(self, keys): self.events.append(("keys", tuple(keys)))
    def release_all(self): self.events.append(("release",))
    def tap(self, key, duration=0.08): self.events.append(("tap", key, duration))
    def click_normalized(self, x, y): self.events.append(("click", x, y))


class FakeDetector:
    def __init__(self, results):
        self.results = list(results)
        self.index = 0

    def matches(self, jpeg_bytes):
        value = self.results[min(self.index, len(self.results) - 1)]
        self.index += 1
        return value


class KagePilotTests(unittest.TestCase):
    def test_dataset_and_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            writer = SessionWriter(root, session_id="fight-1", started_at=10.0)
            writer.append(jpeg(10), timestamp=10.0, keys=("right",), mouse_buttons=("left",), mouse_x=0.2, mouse_y=0.4)
            writer.append(jpeg(20), timestamp=10.1, keys=("right", "e"))
            manifest = writer.finalize("victory", ended_at=10.2)
            self.assertEqual(manifest["result"], "victory")
            self.assertEqual(manifest["samples"], 2)
            samples = list(DatasetStore.samples(root / "sessions" / "fight-1"))
            self.assertEqual(samples[1].keys, ("e", "right"))
            self.assertAlmostEqual(samples[1].delta_ms, 100.0, places=2)
            actions = [json.loads(line) for line in (root / "sessions" / "fight-1" / "actions.jsonl").read_text().splitlines()]
            self.assertEqual(len(actions), 2)
            self.assertAlmostEqual(actions[0]["duration_ms"], 100.0, places=2)

    def test_recorder_with_fakes(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SessionWriter(Path(tmp), session_id="rec", started_at=0.0)
            source = FakeFrameSource([jpeg(10), jpeg(20)])
            input_source = FakeInput([InputSnapshot(("left",)), InputSnapshot(("e",), ("left",), 0.5, 0.5)])
            clock = iter([0.0, 0.0, 0.01, 0.1, 0.1, 0.11, 0.2])
            recorder = Recorder(source, input_source, fps=10, time_fn=lambda: next(clock), sleep_fn=lambda _: None)
            count = recorder.record(writer, max_samples=2)
            writer.finalize("victory", ended_at=0.2)
            self.assertEqual(count, 2)
            self.assertEqual(len(list(DatasetStore.samples(writer.path))), 2)

    def test_behavior_cloner_learns_two_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = SessionWriter(root, session_id="left", started_at=0)
            for i in range(3): left.append(jpeg(0), timestamp=i / 10, keys=("left",))
            left.finalize("victory", ended_at=1)
            right = SessionWriter(root, session_id="right", started_at=0)
            for i in range(3): right.append(jpeg(255), timestamp=i / 10, keys=("right",))
            right.finalize("victory", ended_at=1)
            model = BehaviorCloner.train(DatasetStore(root))
            self.assertEqual(model.predict(jpeg(2)).keys, ("left",))
            self.assertEqual(model.predict(jpeg(253)).keys, ("right",))
            model_path = root / "model.json"
            model.save(model_path)
            self.assertEqual(BehaviorCloner.load(model_path).predict(jpeg(253)).keys, ("right",))

    def test_template_detector(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "victory.png"
            Image.new("L", (16, 16), 200).save(path)
            rule = TemplateRule(path=path, region=(0.0, 0.0, 1.0, 1.0), max_distance=0.02)
            detector = VisualTemplateDetector(rule)
            self.assertTrue(detector.matches(jpeg(200)))
            self.assertFalse(detector.matches(jpeg(40)))

    def test_dojo_manager_victory_rest_cycle(self):
        dummy = TemplateRule(path=Path("unused.png"), region=(0, 0, 1, 1))
        config = DojoConfig(
            start_sequence=({"type": "key", "key": "enter"},),
            rest_sequence=({"type": "key", "key": "v"},),
            post_start_delay_seconds=0,
            post_result_delay_seconds=0,
            rest_seconds=0,
            combat_timeout_seconds=5,
            victory=dummy,
        )
        controller = FakeController()
        frame_source = FakeFrameSource([jpeg(10)] * 8)
        model = BehaviorCloner({"left": [0.0] * 144}, {"left": 1})
        pilot = Pilot(model, frame_source, controller, decision_hz=10, sleep_fn=lambda _: None)
        ticks = iter([0.0, 0.0, 0.1, 0.2, 0.3])
        manager = DojoManager(
            config,
            frame_source,
            controller,
            pilot,
            victory_detector=FakeDetector([False, True]),
            sleep_fn=lambda _: None,
            time_fn=lambda: next(ticks),
        )
        self.assertEqual(manager.run_cycle(), "victory")
        self.assertIn(("tap", "enter", 0.08), controller.events)
        self.assertIn(("tap", "v", 0.08), controller.events)
        self.assertIn(("keys", ("left",)), controller.events)


if __name__ == "__main__":
    unittest.main()
