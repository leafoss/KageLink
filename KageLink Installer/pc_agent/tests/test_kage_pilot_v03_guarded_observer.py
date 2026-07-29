from __future__ import annotations

import importlib.util
import pathlib
import unittest

import numpy as np

from pc_agent.kage_pilot.entity_observer import EntityTrack, ObserverState, FlowEstimate
from pc_agent.kage_pilot.entity_tracker_v03 import TrackContext
from pc_agent.kage_pilot.guarded_observer_v03 import TargetEligibleObserver
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.target_guard_v03 import TargetGuardWaterAwareEntityTracker


class _FakeParentStateObserver(TargetEligibleObserver):
    """Exercise the guarded selection logic without needing real HWND capture."""

    def __init__(self, config, state, tracker):
        # Intentionally avoid the real image pipeline for this unit test.
        self.config = config
        self.tracker = tracker
        self._locked_target_id = state.target_id
        self._state = state

    def process(self, frame_bgr, *, timestamp=None):  # pragma: no cover - replaced below
        raise AssertionError("test monkeypatch should replace this method")


class KagePilotV03GuardedObserverTests(unittest.TestCase):
    def test_lost_high_score_track_is_not_target_eligible(self):
        config = V03ObserverConfig().normalized()
        tracker = TargetGuardWaterAwareEntityTracker(config)
        track = EntityTrack(
            track_id=7,
            bbox=(200, 100, 18, 38),
            center=(209.0, 119.0),
            created_at=0.0,
            last_seen=1.0,
            observations=10,
        )
        track.enemy_score = 95.0
        tracker._tracks[7] = track
        tracker._contexts[7] = TrackContext(state="LOST", relative_side="RIGHT", last_visible_side="RIGHT")

        self.assertFalse(
            tracker.target_eligible(7, player_center=(100.0, 100.0), now=1.2, for_keep=True)
        )

    def test_cli_player_defaults_match_latest_validated_combat_calibration(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        script = root / "kage_pilot_observer.py"
        spec = importlib.util.spec_from_file_location("kage_pilot_observer_defaults", script)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertAlmostEqual(module.DEFAULT_PLAYER_X, 0.5181, places=4)
        self.assertAlmostEqual(module.DEFAULT_PLAYER_Y, 0.4706, places=4)
        parser = module.build_parser()
        args = parser.parse_args([])
        self.assertAlmostEqual(args.player_x, 0.5181, places=4)
        self.assertAlmostEqual(args.player_y, 0.4706, places=4)


if __name__ == "__main__":
    unittest.main()
