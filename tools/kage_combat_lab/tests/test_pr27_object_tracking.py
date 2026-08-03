from __future__ import annotations

import cv2
import numpy as np

from kage_combat_lab.pr27_entity_validation import CandidateClass, EntityCandidate
from kage_combat_lab.pr27_fixed_grid import DEFAULT_FIXED_GRID, NativeRect
from kage_combat_lab.pr27_object_tracking import ObjectTrackState, PersistentObjectTracker
from kage_combat_lab.pr27_trainer_identity import TrainerIdentityTracker


def frame() -> np.ndarray:
    image = np.full((1037, 1920, 3), (100, 120, 90), dtype=np.uint8)
    cv2.rectangle(image, (1080, 400), (1100, 446), (30, 40, 220), -1)
    cv2.rectangle(image, (1084, 442), (1090, 450), (10, 10, 10), -1)
    cv2.rectangle(image, (1092, 442), (1098, 450), (10, 10, 10), -1)
    return image


def candidate(candidate_id: int, bbox: NativeRect = NativeRect(1080, 400, 1101, 451)) -> EntityCandidate:
    feet = ((bbox.left + bbox.right) / 2.0, bbox.bottom - 1.0)
    cell = DEFAULT_FIXED_GRID.cell_for_native_point(*feet)
    descriptor = np.zeros(32, np.float32)
    descriptor[2] = 1.0
    return EntityCandidate(
        candidate_id=candidate_id,
        bbox=bbox,
        feet_anchor=feet,
        relative_cell=None if cell is None else cell.relative_key,
        area=bbox.width * bbox.height,
        component_pixels=500,
        occupancy=0.47,
        aspect_ratio=bbox.width / bbox.height,
        solidity=0.72,
        vertical_score=0.80,
        feet_support_score=0.40,
        rigidity_score=0.82,
        entity_confidence=0.80,
        humanoid_confidence=0.80,
        candidate_class=CandidateClass.HUMANOID_CANDIDATE,
        descriptor=descriptor,
    )


def test_raw_difference_only_opens_track_then_rgb_keeps_it() -> None:
    tracker = PersistentObjectTracker(DEFAULT_FIXED_GRID, confirm_frames=2)
    image = frame()
    first = tracker.update(image, (candidate(1),), frame_index=0)
    assert len(first) == 1
    logical_id = first[0].track_id
    second = tracker.update(image, (candidate(2),), frame_index=1)
    assert second[0].track_id == logical_id
    assert second[0].confirmed
    third = tracker.update(image, (), frame_index=2)
    assert third[0].track_id == logical_id
    assert third[0].state is ObjectTrackState.RGB_PREDICTED
    assert third[0].visible


def test_candidate_id_churn_does_not_reset_body_track() -> None:
    tracker = PersistentObjectTracker(DEFAULT_FIXED_GRID, confirm_frames=2)
    image = frame()
    ids = []
    for frame_index, candidate_id in enumerate((10, 20, 30, 40)):
        tracks = tracker.update(image, (candidate(candidate_id),), frame_index=frame_index)
        ids.append(tracks[0].track_id)
    assert len(set(ids)) == 1
    assert tracks[0].lineage[-4:] == (10, 20, 30, 40)


def test_trainer_identity_vetoes_only_matching_candidate() -> None:
    pre_click = np.full((1037, 1920, 3), (100, 120, 90), dtype=np.uint8)
    trainer_bbox = NativeRect(1040, 300, 1080, 350)
    cv2.rectangle(pre_click, (1040, 300), (1079, 349), (150, 30, 180), -1)
    identity = TrainerIdentityTracker.capture(pre_click, trainer_bbox)
    tracker = TrainerIdentityTracker(identity, confirm_frames=1)
    observed = tracker.observe(pre_click)
    assert observed.current_frame_match
    matching = candidate(1, trainer_bbox)
    other = candidate(2, NativeRect(1120, 300, 1141, 351))
    cv2.rectangle(pre_click, (1120, 300), (1140, 350), (20, 220, 30), -1)
    preserved, vetoed, scores = tracker.veto_candidates(pre_click, (matching, other), threshold=0.75)
    assert 1 in vetoed
    assert any(item.candidate_id == 2 for item in preserved)
    assert tracker.last.entity_detection_mask_pixels == 0


def test_enemy_under_old_trainer_bbox_is_not_blind_masked() -> None:
    scene = np.full((1037, 1920, 3), (100, 120, 90), dtype=np.uint8)
    old_bbox = NativeRect(1040, 300, 1080, 350)
    cv2.rectangle(scene, (1040, 300), (1079, 349), (150, 30, 180), -1)
    identity = TrainerIdentityTracker.capture(scene, old_bbox)
    tracker = TrainerIdentityTracker(identity, confirm_frames=1, absent_frames=1)
    changed = np.full_like(scene, (100, 120, 90))
    cv2.rectangle(changed, (1045, 305), (1065, 350), (20, 220, 30), -1)
    evidence = tracker.observe(changed)
    assert evidence.state.value in {"TRAINER_ABSENT", "TRAINER_VISUAL_UNCERTAIN"}
    enemy = candidate(3, NativeRect(1045, 305, 1066, 351))
    preserved, vetoed, _scores = tracker.veto_candidates(changed, (enemy,), threshold=0.82)
    assert not vetoed
    assert preserved and preserved[0].candidate_id == 3
    assert tracker.last.entity_detection_mask_pixels == 0
