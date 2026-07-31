from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np

from pc_agent.kage_pilot.dojo_vision_lab_v351 import (
    RoundVideoRecorder,
    render_round_frame,
    round_number_from_argv,
)


class _FakeWriter:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs
        self.frames = []
        self.released = False

    def isOpened(self) -> bool:
        return True

    def write(self, frame) -> None:
        self.frames.append(frame.copy())

    def release(self) -> None:
        self.released = True


class _Tracker:
    @staticmethod
    def context_for(track_id: int):
        return SimpleNamespace(state="VISIBLE" if track_id == 7 else "LOST")


class _Observer:
    tile_size = 16.0
    grid_origin_x = 3.0
    grid_origin_y = 5.0
    active_grid_cells = 12
    target_mode = "VISIBLE"
    _locked_target_id = 7
    _grid_target_id = 7
    _contact_latch_until = 999.0
    tracker = _Tracker()
    _previous_gray = np.full((140, 300), 90, dtype=np.uint8)

    @staticmethod
    def metrics_for(track_id: int):
        return SimpleNamespace(grid_distance=1 if track_id == 7 else 4)


class DojoRoundVideoV351Tests(unittest.TestCase):
    @staticmethod
    def _sample():
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[10:150, 10:310] = (24, 58, 32)
        frame[55:80, 120:136] = (110, 155, 190)
        motion = np.zeros((140, 300), dtype=np.uint8)
        motion[40:70, 110:130] = 255
        raw_candidates = (
            SimpleNamespace(bbox=(105, 35, 25, 38)),
            SimpleNamespace(bbox=(210, 80, 18, 26)),
        )
        tracks = (
            SimpleNamespace(track_id=7, bbox=(110, 40, 20, 30), enemy_score=76.0),
            SimpleNamespace(track_id=8, bbox=(205, 75, 19, 28), enemy_score=41.0),
        )
        state = SimpleNamespace(
            timestamp=100.0,
            arena_rect=(10, 10, 310, 150),
            player_center=(150.0, 70.0),
            global_flow=SimpleNamespace(dx=1.25, dy=-0.5, points=18),
            tracks=tracks,
            target_id=7,
            motion_mask=motion,
        )
        detector = SimpleNamespace(
            _last_visual=SimpleNamespace(bbox=(250, 90, 20, 20), score=0.931),
            _last_visual_at=100.0,
            last_raw_score=0.931,
            threshold=0.880,
            last_accepted_template_mode="32",
            last_raw_scale=1.0,
            last_rejection_reason="",
        )
        engine = SimpleNamespace(leader_detector=detector, state="SEEK_LEADER")
        return frame, state, _Observer(), raw_candidates, engine

    def test_round_number_is_derived_from_round_log_path(self):
        argv = [
            "KagePilotRound.exe",
            "--log",
            r"C:\Users\Rafael\AppData\Local\KageLink\round_007.jsonl",
        ]
        self.assertEqual(round_number_from_argv(argv), 7)

    def test_renderer_contains_raw_candidates_tracks_and_locks(self):
        frame, state, observer, candidates, engine = self._sample()
        output = render_round_frame(
            frame,
            state,
            observer,
            raw_candidates=candidates,
            engine=engine,
            round_number=7,
            sequence=3,
            elapsed=1.25,
        )
        self.assertEqual(output.shape, (720, 1280, 3))
        self.assertGreater(int(np.count_nonzero(output)), 0)

    def test_recorder_writes_one_video_stream_for_the_round(self):
        frame, state, observer, candidates, engine = self._sample()
        created = []

        def factory(*args, **kwargs):
            writer = _FakeWriter(*args, **kwargs)
            created.append(writer)
            return writer

        with tempfile.TemporaryDirectory() as directory:
            recorder = RoundVideoRecorder(
                root=directory,
                round_number=7,
                fps=8.0,
                writer_factory=factory,
            )
            self.assertTrue(
                recorder.record(
                    frame,
                    state,
                    observer,
                    raw_candidates=candidates,
                    engine=engine,
                )
            )
            self.assertTrue(
                recorder.record(
                    frame,
                    state,
                    observer,
                    raw_candidates=candidates,
                    engine=engine,
                )
            )
            destination = recorder.close("unit_test")

        self.assertIsNotNone(destination)
        self.assertEqual(len(created), 1)
        self.assertEqual(len(created[0].frames), 2)
        self.assertTrue(created[0].released)
        self.assertIn("round_007_", Path(destination).name)

    def test_desktop_layer_is_absent_and_black_box_is_not_installed(self):
        root = Path(__file__).resolve().parents[1]
        entry = (root / "unified_entry.py").read_text(encoding="utf-8")
        visual_return = (root / "kage_pilot_visual_return.py").read_text(encoding="utf-8")
        recorder = (
            root / "pc_agent" / "kage_pilot" / "dojo_vision_lab_v351.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("unified_dojo_vision_lab_v351", entry)
        self.assertNotIn("install_dojo_vision_lab_desktop", entry)
        self.assertNotIn("install_vision_black_box(runtime)", visual_return)
        self.assertIn("install_runtime_lab(runtime)", visual_return)
        self.assertNotIn("tkinter", recorder.casefold())
        self.assertNotIn("ImageTk", recorder)
        self.assertIn("DOJO_ROUND_VIDEO_READY", recorder)
        self.assertIn("RAW CANDIDATES", recorder)
        self.assertIn("CONTACT LOCK", recorder)


if __name__ == "__main__":
    unittest.main()
