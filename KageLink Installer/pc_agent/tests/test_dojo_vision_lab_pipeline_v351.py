from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np

from pc_agent.kage_pilot.dojo_vision_lab_v351 import (
    VisionLabRecorder,
    VisionLabSettings,
    build_panels,
)


class DojoVisionLabPipelineV351Tests(unittest.TestCase):
    @staticmethod
    def _sample():
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[10:150, 10:310] = (24, 58, 32)
        frame[55:80, 120:136] = (110, 155, 190)
        motion = np.zeros((140, 300), dtype=np.uint8)
        motion[40:70, 110:130] = 255
        track = SimpleNamespace(
            track_id=7,
            bbox=(110, 40, 20, 30),
            enemy_score=76.0,
        )
        state = SimpleNamespace(
            arena_rect=(10, 10, 310, 150),
            player_center=(150.0, 70.0),
            global_flow=SimpleNamespace(dx=1.25, dy=-0.5, points=18),
            tracks=(track,),
            target_id=7,
            motion_mask=motion,
        )
        observer = SimpleNamespace(
            tile_size=16.0,
            grid_origin_x=3.0,
            grid_origin_y=5.0,
            _kagelink_debug_contrast=np.full((140, 300), 90, dtype=np.uint8),
        )
        detector = SimpleNamespace(
            active_scan_mode="32",
            active_scan_scales=(0.45, 0.50, 0.55, 0.60),
            last_raw_score=0.931,
            threshold=0.880,
            last_raw_scale=0.500,
            last_rejection_reason="",
        )
        match = SimpleNamespace(bbox=(120, 50, 16, 16), score=0.931, source="visual")
        decision = SimpleNamespace(
            state="SEEK_LEADER",
            action="right",
            move_pulse="right",
            tap_v=False,
            health=0.82,
            chakra=0.35,
            target_id=7,
            grid_distance=3,
            reason="move toward confirmed visual target",
        )
        return frame, state, observer, detector, match, decision

    def test_build_panels_exposes_every_visual_stage(self):
        frame, state, observer, detector, match, decision = self._sample()
        panels, metadata = build_panels(
            frame,
            state,
            observer=observer,
            detector=detector,
            match=match,
            decision=decision,
            source="round",
        )

        required = {
            "raw",
            "arena",
            "gray",
            "contrast",
            "motion_mask",
            "tracks",
            "trainer_scan",
            "grid",
            "hud",
            "composite",
        }
        self.assertEqual(set(panels), required)
        self.assertEqual(panels["composite"].shape, (660, 960, 3))
        self.assertEqual(metadata["detector"]["scan_mode"], "32")
        self.assertEqual(metadata["detector"]["scan_scales"], [0.45, 0.5, 0.55, 0.6])
        self.assertAlmostEqual(metadata["detector"]["raw_score"], 0.931)
        self.assertEqual(metadata["observer"]["cell_size"], 16.0)
        self.assertEqual(metadata["observer"]["target_id"], 7)
        self.assertEqual(metadata["decision"]["action"], "right")

    def test_recorder_writes_live_stages_manifest_and_clean_summary(self):
        frame, state, observer, detector, match, decision = self._sample()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = VisionLabRecorder(
                "round",
                "round_001",
                root=root,
                settings=VisionLabSettings(
                    enabled=True,
                    fps=6.0,
                    record_video=False,
                    save_stages=True,
                    stage_interval=0.25,
                    jpeg_quality=80,
                ),
            )
            self.assertTrue(
                recorder.record(
                    frame,
                    state,
                    observer=observer,
                    detector=detector,
                    match=match,
                    decision=decision,
                    now=1.0,
                )
            )

            live = root / "live"
            for name in (
                "raw",
                "arena",
                "gray",
                "contrast",
                "motion_mask",
                "tracks",
                "trainer_scan",
                "grid",
                "hud",
                "composite",
            ):
                self.assertTrue((live / f"{name}.jpg").is_file(), name)
            status = json.loads((live / "status.json").read_text(encoding="utf-8"))
            self.assertTrue(status["active"])
            self.assertEqual(status["recorded"], 1)
            self.assertEqual(status["metadata"]["observer"]["target_id"], 7)

            rows = recorder.frames_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            row = json.loads(rows[0])
            self.assertEqual(row["metadata"]["detector"]["scan_mode"], "32")
            self.assertEqual(set(row["stages"]), {
                "raw",
                "arena",
                "gray",
                "contrast",
                "motion_mask",
                "tracks",
                "trainer_scan",
                "grid",
                "hud",
                "composite",
            })

            recorder.close("unit_test")
            summary = json.loads(
                (recorder.session / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["reason"], "unit_test")
            self.assertEqual(summary["recorded"], 1)
            self.assertIsNone(summary["video"])
            final_status = json.loads((live / "status.json").read_text(encoding="utf-8"))
            self.assertFalse(final_status["active"])

    def test_source_contract_records_video_per_session_and_exact_runtime_taps(self):
        root = Path(__file__).resolve().parents[1]
        lab_source = (
            root / "pc_agent" / "kage_pilot" / "dojo_vision_lab_v351.py"
        ).read_text(encoding="utf-8")
        round_source = (root / "kage_pilot_visual_return.py").read_text(encoding="utf-8")
        anchor_source = (
            root / "pc_agent" / "kage_pilot" / "dojo_anchor_monitor_compat_v351.py"
        ).read_text(encoding="utf-8")
        desktop_source = (root / "unified_dojo_vision_lab_v351.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('self.video = self.session / "vision_pipeline.avi"', lab_source)
        self.assertIn("cv2.VideoWriter(", lab_source)
        self.assertIn('self.session / "stages"', lab_source)
        self.assertIn('self.frames_file = self.session / "frames.jsonl"', lab_source)
        self.assertIn("install_combat_tap()", lab_source)
        self.assertIn("install_runtime_lab(runtime)", round_source)
        self.assertIn("install_anchor_monitor_lab(monitor_type)", anchor_source)

        for key in (
            "raw",
            "arena",
            "gray",
            "contrast",
            "motion_mask",
            "tracks",
            "trainer_scan",
            "grid",
            "hud",
        ):
            self.assertIn(f'"{key}"', desktop_source)
        self.assertIn("dojo_vision_lab", desktop_source)
        self.assertNotIn("Show overlay over the game", desktop_source)


if __name__ == "__main__":
    unittest.main()
