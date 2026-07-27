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
    def test_temporal_model_separates_navigation_and_skills_and_cuts_v_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            writer = SessionWriter(root, session_id="fight", started_at=0.0)
            writer.append(jpeg(20), timestamp=0.0, keys=("r",))
            writer.append(jpeg(60), timestamp=0.1, keys=("r", "right"))
            writer.append(jpeg(100), timestamp=0.2, keys=("r", "h"))
            writer.append(jpeg(160), timestamp=0.3, keys=("r", "left"))
            writer.append(jpeg(220), timestamp=0.4, keys=("v",))
            writer.append(jpeg(240), timestamp=0.5, keys=())
            writer.finalize("victory", ended_at=0.6)

            model = TemporalCombatModel.train(
                DatasetStore(root),
                base_keys=("r",),
                skill_keys=("h",),
                post_combat_keys=("v",),
                history_frames=1,
            )
            self.assertEqual(model.base_keys, ("r",))
            self.assertEqual(model.skill_keys, ("h",))
            self.assertEqual(model.post_combat_keys, ("v",))
            self.assertIn("right", model.navigation.prototypes)
            self.assertIn("left", model.navigation.prototypes)
            self.assertIn("h", model.skill.prototypes)
            self.assertNotIn("v", model.skill.prototypes)
            self.assertIn("idle", model.skill.prototypes)
            # V and everything after it are post-fight, so only the first four
            # action runs are eligible for combat learning.
            self.assertEqual(sum(model.navigation.counts.values()), 4)

            prediction = model.predict(jpeg(20), jpeg(60))
            self.assertEqual(prediction.navigation.keys, ("right",))

            path = root / "v02.json"
            model.save(path)
            loaded = TemporalCombatModel.load(path)
            self.assertEqual(loaded.base_keys, ("r",))
            self.assertEqual(loaded.skill_keys, ("h",))
            self.assertEqual(loaded.post_combat_keys, ("v",))

    def test_leading_v_from_previous_victory_does_not_discard_next_fight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            writer = SessionWriter(root, session_id="next-fight", started_at=0.0)
            # Recorder already opened the next session; V belongs to meditation
            # from the previous victory and must be ignored, not treated as EOF.
            writer.append(jpeg(20), timestamp=0.0, keys=("v",))
            writer.append(jpeg(30), timestamp=0.1, keys=())
            writer.append(jpeg(60), timestamp=0.2, keys=("r",))
            writer.append(jpeg(100), timestamp=0.3, keys=("r", "right"))
            writer.append(jpeg(140), timestamp=0.4, keys=("r", "h"))
            writer.append(jpeg(180), timestamp=0.5, keys=("r", "left"))
            writer.finalize("victory", ended_at=0.6)

            model = TemporalCombatModel.train(
                DatasetStore(root),
                base_keys=("r",),
                skill_keys=("h",),
                post_combat_keys=("v",),
                history_frames=1,
            )
            self.assertEqual(sum(model.navigation.counts.values()), 4)
            self.assertIn("right", model.navigation.counts)
            self.assertIn("left", model.navigation.counts)
            self.assertIn("h", model.skill.counts)
            self.assertNotIn("v", model.skill.counts)

    def test_temporal_features_include_change(self):
        stationary = temporal_features(jpeg(40), jpeg(40))
        moving = temporal_features(jpeg(40), jpeg(180))
        half = len(stationary) // 2
        self.assertTrue(all(abs(value) < 1e-9 for value in stationary[half:]))
        self.assertTrue(any(abs(value) > 0.1 for value in moving[half:]))

    def test_policy_uses_real_exemplars_not_only_centroid(self):
        low = temporal_features(jpeg(0), jpeg(0))
        high = temporal_features(jpeg(255), jpeg(255))
        middle = temporal_features(jpeg(125), jpeg(125))
        policy = PrototypePolicy.from_examples([
            ("idle", low),
            ("idle", high),
            ("right", middle),
        ])
        self.assertTrue(policy.exemplars)
        self.assertEqual(policy.predict_features(middle).label, "right")

    def test_pilot_holds_r_and_requires_idle_rearm_for_skill(self):
        previous = jpeg(10)
        current = jpeg(200)
        features = temporal_features(previous, current)
        idle_features = temporal_features(current, current)
        nav = PrototypePolicy({"right": features}, {"right": 1}, {"right": [features]})
        skill = PrototypePolicy(
            {"h": features, "idle": idle_features},
            {"h": 1, "idle": 1},
            {"h": [features], "idle": [idle_features]},
        )
        model = TemporalCombatModel(nav, skill, base_keys=("r",), skill_keys=("h",), post_combat_keys=("v",))
        source = FakeFrameSource([current, current, current, current])
        controller = FakeController()
        clock = iter([10.0, 11.5, 11.6, 13.0])
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
        # Even though cooldown has elapsed, H cannot fire again until skill
        # prediction returns to idle at least once.
        self.assertEqual(second.skill_fired, ())

        # Force one idle observation to rearm, then restore H-like temporal
        # context and verify H can fire again.
        pilot.model.skill = PrototypePolicy({"idle": idle_features}, {"idle": 1}, {"idle": [idle_features]})
        third = pilot.step()
        self.assertEqual(third.skill_fired, ())
        pilot.model.skill = PrototypePolicy({"h": idle_features}, {"h": 1}, {"h": [idle_features]})
        fourth = pilot.step()
        self.assertEqual(fourth.skill_fired, ("h",))


if __name__ == "__main__":
    unittest.main()
