from types import SimpleNamespace

import cv2
import numpy as np

from kage_combat_lab.domain import CandidateObservation, GridCell, ObservationKind
from kage_combat_lab.player_facing_dataset import PlayerFacingDatasetCollector


def state(mask=None):
    return SimpleNamespace(
        arena_rect=(0, 0, 128, 128),
        player_center=(64.0, 64.0),
        motion_mask=(
            np.zeros((128, 128), dtype=np.uint8)
            if mask is None
            else mask
        ),
    )


def test_trustworthy_turn_saves_png_and_json(tmp_path):
    collector = PlayerFacingDatasetCollector(tmp_path)
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    cv2.circle(frame, (64, 64), 10, (255, 255, 255), -1)
    saved, contamination, path = collector.save_if_trustworthy(
        frame_bgr=frame,
        state=state(),
        candidate=None,
        direction="RIGHT",
        round_name="round_003",
        frame_index=148,
        confidence=0.86,
        source="EXCLUSIVE_TURN_TRANSACTION",
    )
    assert saved and path is not None and path.exists()
    assert path.with_suffix(".json").exists()
    assert contamination == 0.0


def test_overlap_with_target_blocks_dataset_poisoning(tmp_path):
    collector = PlayerFacingDatasetCollector(tmp_path)
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    candidate = CandidateObservation(
        1,
        GridCell(0, 0),
        ObservationKind.CLEAN_BODY,
        bbox=(32, 32, 64, 64),
        cells_touched=frozenset({GridCell(0, 0)}),
    )
    saved, contamination, path = collector.save_if_trustworthy(
        frame_bgr=frame,
        state=state(),
        candidate=candidate,
        direction="LEFT",
        round_name="round_003",
        frame_index=149,
        confidence=0.86,
        source="EXCLUSIVE_TURN_TRANSACTION",
    )
    assert not saved and path is None
    assert contamination > 0.35


def test_low_confidence_never_saves(tmp_path):
    collector = PlayerFacingDatasetCollector(tmp_path)
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    saved, _, path = collector.save_if_trustworthy(
        frame_bgr=frame,
        state=state(),
        candidate=None,
        direction="UP",
        round_name="round_003",
        frame_index=150,
        confidence=0.40,
        source="UNKNOWN",
    )
    assert not saved and path is None
