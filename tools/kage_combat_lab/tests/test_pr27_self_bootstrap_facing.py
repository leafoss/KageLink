from __future__ import annotations

from collections import deque

import cv2
import numpy as np

from kage_combat_lab.pr27_facing import FacingObserver
from kage_combat_lab.pr27_identity import SelfTracker
from kage_combat_lab.pr27_model import (
    AppearanceDescriptor,
    PR27Config,
    SpriteClass,
    SpriteRole,
    TrackState,
    TrackedSprite,
)
from kage_combat_lab.pr27_pre_trainer_baseline import _self_capsule_from_idle_cell


def _descriptor() -> AppearanceDescriptor:
    histogram = np.zeros(32, dtype=np.float32)
    histogram[3] = 1.0
    structure = np.zeros(64, dtype=np.float32)
    structure[7] = 1.0
    return AppearanceDescriptor(histogram, structure, 0.2)


def _self_track() -> TrackedSprite:
    bbox = (70, 45, 24, 48)
    value = TrackedSprite(
        track_id=0,
        current_cells=frozenset({(0, 0)}),
        previous_cells=frozenset(),
        fragments=(),
        native_bbox=bbox,
        combined_mask=np.ones((48, 24), dtype=np.uint8),
        appearance_signature=_descriptor(),
        first_seen_frame=0,
        last_seen_frame=0,
        body_bbox=bbox,
        body_anchor=(82.0, 92.0),
        anchor_cell=(0, 0),
        body_confidence=0.9,
        classification=SpriteClass.PLAYER,
        confidence=0.9,
        track_state=TrackState.TRACKED,
        role=SpriteRole.SELF,
        role_locked=True,
        role_source="test",
        role_confidence=1.0,
    )
    value.movement_history.append(value.body_anchor)
    return value


def test_precombat_idle_cell_builds_self_identity_capsule() -> None:
    crops = deque(maxlen=31)
    for frame_index in range(8):
        image = np.full((64, 64, 3), (70, 75, 80), dtype=np.uint8)
        cv2.rectangle(image, (24, 18), (41, 55), (35, 150, 220), -1)
        cv2.rectangle(image, (28 + frame_index % 2, 11), (37 + frame_index % 2, 18), (20, 80, 180), -1)
        crops.append(image)
    metadata = _self_capsule_from_idle_cell(
        crops,
        cell_x=128,
        cell_y=64,
        desired_anchor=(32, 56),
    )
    assert metadata is not None
    assert metadata["self_body_size"][0] >= 10
    assert metadata["self_body_size"][1] >= 30
    assert len(metadata["self_appearance_descriptor"]["hsv_histogram"]) == 32
    assert len(metadata["self_appearance_descriptor"]["structure_vector"]) == 64
    assert metadata["self_calibration_confidence"] > 0.4


def test_self_tracker_loads_calibrated_descriptor_and_anchor() -> None:
    tracker = SelfTracker(PR27Config().normalized())
    metadata = {
        "self_body_size": [20, 42],
        "self_anchor_arena": [123.5, 98.0],
        "self_appearance_descriptor": {
            "hsv_histogram": [1.0] + [0.0] * 31,
            "structure_vector": [1.0] + [0.0] * 63,
            "edge_density": 0.2,
        },
        "self_calibration_confidence": 0.88,
        "self_calibration_method": "test",
    }
    tracker.bootstrap_metadata(metadata)
    assert tracker.identity.ready
    assert tracker.expected_anchor == (123.5, 98.0)
    assert tracker.identity.calibration_confidence == 0.88


def test_controlled_turn_requires_changed_and_stable_visual_frames() -> None:
    observer = FacingObserver(PR27Config(facing_confirm_frames=2).normalized())
    track = _self_track()
    before = np.zeros((140, 160, 3), dtype=np.uint8)
    cv2.rectangle(before, (70, 45), (93, 92), (120, 120, 120), -1)
    cv2.rectangle(before, (70, 56), (76, 66), (255, 255, 255), -1)
    observer.observe(before, track)
    observer.note_physical_actions(("R_HELD_COMBAT", "TURN_RIGHT_60MS"))
    assert observer.commanded == "RIGHT"
    assert observer.observed is None

    after = np.zeros_like(before)
    cv2.rectangle(after, (70, 45), (93, 92), (120, 120, 120), -1)
    cv2.rectangle(after, (87, 56), (93, 66), (255, 255, 255), -1)
    observer.observe(after, track)
    assert not observer.confirmed
    observer.observe(after, track)
    assert observer.observed == "RIGHT"
    observer.observe(after, track)
    assert observer.confirmed
    assert observer.last_visual_source in {
        "CONTROLLED_TURN_VISUAL_TRANSITION",
        "FACING_TEMPLATE_MATCH",
    }


def test_turn_command_without_visual_change_never_confirms() -> None:
    observer = FacingObserver(PR27Config(facing_confirm_frames=2).normalized())
    track = _self_track()
    arena = np.zeros((140, 160, 3), dtype=np.uint8)
    cv2.rectangle(arena, (70, 45), (93, 92), (120, 120, 120), -1)
    observer.observe(arena, track)
    observer.note_physical_actions(("TURN_LEFT_60MS",))
    for _ in range(4):
        observer.observe(arena, track)
    assert observer.commanded == "LEFT"
    assert not observer.confirmed
