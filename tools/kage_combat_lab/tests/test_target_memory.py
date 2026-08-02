from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from kage_combat_lab.domain import (
    CandidateObservation,
    CombatFrame,
    GridCell,
    ObservationKind,
)
from kage_combat_lab.target_memory import TargetCapsuleMemory


def sprite(brightness=1.0):
    image = np.zeros((42, 24, 3), dtype=np.uint8)
    cv2.rectangle(image, (7, 2), (17, 12), (30, 30, int(220 * brightness)), -1)
    cv2.rectangle(
        image,
        (4, 13),
        (20, 34),
        (int(80 * brightness), int(160 * brightness), 40),
        -1,
    )
    cv2.line(image, (4, 20), (0, 30), (240, 240, 240), 2)
    cv2.line(image, (20, 20), (23, 30), (240, 240, 240), 2)
    return image


def frame_with_sprite(image, x=70, y=50):
    frame = np.full((180, 240, 3), 32, dtype=np.uint8)
    h, w = image.shape[:2]
    frame[y : y + h, x : x + w] = image
    return frame


def candidate(track, x=70, y=50, *, kind=ObservationKind.CLEAN_BODY, confidence=0.9):
    h, w = 42, 24
    foot = (x + w * 0.5, y + h)
    return CandidateObservation(
        track_id=track,
        anchor_cell=GridCell(1, 1),
        kind=kind,
        visible=True,
        body_like=kind is ObservationKind.CLEAN_BODY,
        confidence=confidence,
        cells_touched=frozenset({GridCell(1, 1)}),
        bbox=(x, y, w, h),
        foot_point=foot,
        relative_offset_px=(50.0, 20.0),
        motion_score=0.65,
    )


def state():
    return SimpleNamespace(
        arena_rect=(0, 0, 240, 180),
        global_flow=SimpleNamespace(dx=0.0, dy=0.0),
    )


def test_capsule_saves_manifest_and_sprite(tmp_path: Path):
    memory = TargetCapsuleMemory(root=tmp_path)
    frame = frame_with_sprite(sprite())
    selected = candidate(1)
    memory.observe_selected(
        frame_bgr=frame,
        state=state(),
        candidate=selected,
        timestamp=1.0,
        face="RIGHT",
        grid_distance=1,
    )
    assert memory.ready
    assert (tmp_path / "target_session.json").exists()
    assert (tmp_path / "exemplar_001.png").exists()
    assert (tmp_path / "descriptor_001.npz").exists()


def test_new_track_is_reidentified_from_appearance_and_position(tmp_path: Path):
    memory = TargetCapsuleMemory(root=tmp_path)
    base = frame_with_sprite(sprite())
    memory.observe_selected(
        frame_bgr=base,
        state=state(),
        candidate=candidate(1),
        timestamp=1.0,
        face="RIGHT",
        grid_distance=1,
    )

    changed = frame_with_sprite(sprite(0.82), x=74, y=52)
    raw = candidate(
        99,
        x=74,
        y=52,
        kind=ObservationKind.CONTAMINATED_ACTIVITY,
        confidence=0.42,
    )
    raw = replace(raw, body_like=False)
    enriched = memory.enrich_candidates(
        frame_bgr=changed,
        state=state(),
        candidates=[raw],
        timestamp=1.2,
    )[0]
    assert enriched.kind is ObservationKind.REIDENTIFIED_BODY
    assert enriched.reidentified
    assert enriched.identity_score >= memory.reid_accept_score
    assert enriched.appearance_score >= memory.min_appearance_score


def test_repeated_weak_static_candidate_becomes_background(tmp_path: Path):
    memory = TargetCapsuleMemory(root=tmp_path)
    floor = np.full((180, 240, 3), 40, dtype=np.uint8)
    cv2.rectangle(floor, (70, 50), (93, 91), (55, 55, 55), -1)
    weak = candidate(
        7,
        kind=ObservationKind.CONTAMINATED_ACTIVITY,
        confidence=0.2,
    )
    weak = replace(weak, body_like=False, motion_score=0.45)

    result = weak
    for index in range(8):
        result = memory.enrich_candidates(
            frame_bgr=floor,
            state=state(),
            candidates=[weak],
            timestamp=float(index) * 0.2,
        )[0]
    assert result.background_probability >= 0.70
    assert not result.is_target_body


def test_best_current_candidate_prefers_reidentified_target_over_floor(tmp_path: Path):
    memory = TargetCapsuleMemory(root=tmp_path)
    target = CandidateObservation(
        track_id=9,
        anchor_cell=GridCell(1, 1),
        kind=ObservationKind.REIDENTIFIED_BODY,
        body_like=True,
        identity_score=0.85,
        appearance_score=0.8,
        position_score=0.8,
        shape_similarity=0.8,
        motion_score=0.6,
        background_probability=0.1,
        reidentified=True,
    )
    floor = CandidateObservation(
        track_id=10,
        anchor_cell=GridCell(1, 1),
        kind=ObservationKind.CONTAMINATED_ACTIVITY,
        body_like=False,
        confidence=0.3,
        background_probability=0.9,
    )
    combat_frame = CombatFrame.from_iterable(
        1, GridCell(0, 0), [floor, target], timestamp_seconds=1.2
    )
    best = memory.best_current_candidate(
        combat_frame,
        confirmed_cell=GridCell(1, 1),
    )
    assert best is target
