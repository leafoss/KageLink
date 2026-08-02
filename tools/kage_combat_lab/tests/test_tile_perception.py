from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from kage_combat_lab.domain import CandidateObservation, GridCell, ObservationKind
from kage_combat_lab.tile_perception import (
    PR24CombatTilePerception,
    TileFeatureExtractor,
    TilePerceptionConfig,
)


def _build_runtime(
    tmp_path: Path,
    terrain: np.ndarray,
    *,
    similarity: float = 0.90,
    novelty: float = 0.12,
    activity: float = 0.005,
) -> PR24CombatTilePerception:
    root = tmp_path / "data"
    profile = root / "profiles" / "default"
    (profile / "calibrations").mkdir(parents=True)
    (profile / "tile_knowledge").mkdir(parents=True)
    (profile / "calibrations" / "arena_grid.json").write_text(
        json.dumps({"tile_size_px": 64, "offset_x_px": 0, "offset_y_px": 0}),
        encoding="utf-8",
    )
    feature = TileFeatureExtractor().extract(terrain[2:-2, 2:-2]).tolist()
    crop_path = profile / "tile_knowledge" / "terrain.png"
    cv2.imwrite(str(crop_path), terrain)
    (profile / "tile_knowledge" / "arena.json").write_text(
        json.dumps(
            {
                "examples": [
                    {
                        "id": "floor",
                        "category": "walkable",
                        "feature": feature,
                        "crop_path": str(crop_path),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return PR24CombatTilePerception(
        TilePerceptionConfig(
            data_root=root,
            profile="default",
            region_id="arena",
            similarity_threshold=similarity,
            novelty_threshold=novelty,
            temporal_activity_threshold=activity,
            terrain_reject_similarity=0.965,
            crop_inset_px=2,
        )
    )


def _state_and_observer():
    state = SimpleNamespace(
        arena_rect=(0, 0, 128, 128),
        player_center=(32.0, 96.0),
    )
    observer = SimpleNamespace(grid_origin=(0.0, 0.0))
    return state, observer


def test_unknown_tile_promotes_weak_raw_candidate(tmp_path: Path) -> None:
    terrain = np.zeros((64, 64, 3), dtype=np.uint8)
    terrain[:] = 30
    runtime = _build_runtime(tmp_path, terrain, activity=0.0)
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    frame[:] = 30
    cv2.rectangle(frame, (76, 16), (92, 58), (230, 230, 230), -1)
    state, observer = _state_and_observer()
    weak = CandidateObservation(
        track_id=7,
        anchor_cell=GridCell(1, 0),
        kind=ObservationKind.CONTAMINATED_ACTIVITY,
        visible=True,
        body_like=False,
        confidence=0.2,
        bbox=(76, 16, 16, 42),
        motion_score=0.5,
        background_probability=0.4,
    )

    result = runtime.enrich_candidates(
        frame_bgr=frame,
        state=state,
        observer=observer,
        candidates=[weak],
        target_memory=SimpleNamespace(ready=False),
    )

    promoted = next(item for item in result if item.track_id == 7)
    assert promoted.kind is ObservationKind.CLEAN_BODY
    assert promoted.body_like
    assert promoted.appearance_score > 0.1


def test_known_terrain_rejects_weak_candidate(tmp_path: Path) -> None:
    terrain = np.zeros((64, 64, 3), dtype=np.uint8)
    terrain[:] = 30
    runtime = _build_runtime(tmp_path, terrain, activity=0.0)
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    frame[:] = 30
    state, observer = _state_and_observer()
    weak = CandidateObservation(
        track_id=8,
        anchor_cell=GridCell(1, 0),
        kind=ObservationKind.CLEAN_BODY,
        visible=True,
        body_like=True,
        confidence=0.2,
        bbox=(70, 10, 16, 30),
        motion_score=0.1,
        background_probability=0.0,
    )

    result = runtime.enrich_candidates(
        frame_bgr=frame,
        state=state,
        observer=observer,
        candidates=[weak],
        target_memory=SimpleNamespace(ready=False),
    )

    rejected = next(item for item in result if item.track_id == 8)
    assert rejected.kind is ObservationKind.CONTAMINATED_ACTIVITY
    assert rejected.background_probability >= 0.96


def test_unknown_moving_tile_creates_synthetic_candidate(tmp_path: Path) -> None:
    terrain = np.zeros((64, 64, 3), dtype=np.uint8)
    terrain[:] = 30
    runtime = _build_runtime(tmp_path, terrain, activity=0.001)
    base = np.zeros((128, 128, 3), dtype=np.uint8)
    base[:] = 30
    state, observer = _state_and_observer()

    runtime.enrich_candidates(
        frame_bgr=base,
        state=state,
        observer=observer,
        candidates=[],
        target_memory=SimpleNamespace(ready=False),
    )
    changed = base.copy()
    cv2.rectangle(changed, (76, 12), (94, 56), (240, 240, 240), -1)
    result = runtime.enrich_candidates(
        frame_bgr=changed,
        state=state,
        observer=observer,
        candidates=[],
        target_memory=SimpleNamespace(ready=False),
    )

    synthetic = [item for item in result if item.track_id < 0]
    assert len(synthetic) == 1
    assert synthetic[0].anchor_cell == GridCell(1, 0)
    assert synthetic[0].kind is ObservationKind.CLEAN_BODY


def test_synthetic_candidates_stop_after_target_capsule_ready(tmp_path: Path) -> None:
    terrain = np.zeros((64, 64, 3), dtype=np.uint8)
    terrain[:] = 30
    runtime = _build_runtime(tmp_path, terrain, activity=0.001)
    base = np.zeros((128, 128, 3), dtype=np.uint8)
    base[:] = 30
    state, observer = _state_and_observer()

    runtime.enrich_candidates(
        frame_bgr=base,
        state=state,
        observer=observer,
        candidates=[],
        target_memory=SimpleNamespace(ready=False),
    )
    changed = base.copy()
    cv2.rectangle(changed, (76, 12), (94, 56), (240, 240, 240), -1)
    result = runtime.enrich_candidates(
        frame_bgr=changed,
        state=state,
        observer=observer,
        candidates=[],
        target_memory=SimpleNamespace(ready=True),
    )

    assert not [item for item in result if item.track_id < 0]
