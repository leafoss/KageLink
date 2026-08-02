from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from kage_combat_lab.pr27_native_grid import (
    ArenaCropper,
    ArenaRect,
    CellBaselineStore,
    CellDifferenceDetector,
    CellSearchGroup,
    CellState,
    CombatAction,
    NativeGrid64,
    PR27CombatSystem,
    PR27Config,
    RoundState,
    SpriteClass,
    TrackState,
)


def blank_frame(width: int = 256, height: int = 192) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def seed_blank_baseline(system: PR27CombatSystem, frame: np.ndarray) -> None:
    _, arena = system.cropper.crop(frame)
    for cell in system.grid.build(arena.shape):
        crop = arena[cell.y : cell.y + cell.height, cell.x : cell.x + cell.width]
        system.baselines.set(cell, crop)


def draw_sprite(frame: np.ndarray, x: int, y: int, color=(50, 180, 240)) -> None:
    cv2.rectangle(frame, (x, y), (x + 18, y + 38), color, -1)
    cv2.rectangle(frame, (x + 5, y - 7), (x + 13, y), color, -1)


def test_native_grid_keeps_64px_cells_and_real_border_sizes() -> None:
    cells = NativeGrid64().build((130, 150, 3))
    assert cells[0].width == 64 and cells[0].height == 64
    assert max(cell.column for cell in cells) == 2
    assert max(cell.row for cell in cells) == 2
    edge = next(cell for cell in cells if cell.row == 2 and cell.column == 2)
    assert edge.width == 22
    assert edge.height == 2


def test_each_cell_owns_its_own_difference_mask() -> None:
    config = PR27Config(changed_ratio_threshold=0.02, minimum_component_area=4)
    frame = blank_frame(128, 128)
    cells = NativeGrid64().build(frame.shape)
    baselines = CellBaselineStore()
    for cell in cells:
        baselines.set(cell, frame[cell.y : cell.y + cell.height, cell.x : cell.x + cell.width])

    changed = frame.copy()
    cv2.rectangle(changed, (70, 10), (90, 35), (255, 255, 255), -1)
    differences = CellDifferenceDetector(config).compare(changed, cells, baselines)

    assert differences[(0, 1)].state is CellState.CHANGED
    assert differences[(0, 0)].state is CellState.STABLE
    assert differences[(1, 0)].state is CellState.STABLE
    assert differences[(1, 1)].state is CellState.STABLE
    assert differences[(0, 1)].difference_mask.shape == (64, 64)


def test_group_is_only_a_list_of_cell_addresses() -> None:
    annotations = CellSearchGroup.__annotations__
    assert set(annotations) == {"group_id", "cells"}
    forbidden = {"identity", "target", "foot_point", "hostility", "direction", "bbox"}
    assert forbidden.isdisjoint(annotations)


def test_sprite_keeps_visual_id_when_crossing_native_cell_boundary() -> None:
    config = PR27Config(
        changed_ratio_threshold=0.01,
        uncertain_ratio_threshold=0.005,
        minimum_component_area=4,
        scene_changed_min_cells=20,
        association_min_score=0.30,
        enemy_confirm_frames=3,
        player_anchor_radius_px=35,
    )
    cropper = ArenaCropper(ArenaRect(0, 0, 256, 192))
    system = PR27CombatSystem(config=config, cropper=cropper)
    baseline = blank_frame()
    seed_blank_baseline(system, baseline)

    ids = []
    for x in (55, 61, 67, 73):
        frame = baseline.copy()
        draw_sprite(frame, 120, 96, (240, 120, 40))
        draw_sprite(frame, x, 30, (40, 210, 70))
        result = system.process(frame)
        enemy_like = [track for track in result.tracks if track.center[1] < 80]
        assert enemy_like
        ids.append(enemy_like[0].track_id)

    assert len(set(ids)) == 1


def test_context_enemy_requires_persistent_visual_identity() -> None:
    config = PR27Config(
        changed_ratio_threshold=0.01,
        uncertain_ratio_threshold=0.005,
        minimum_component_area=4,
        scene_changed_min_cells=20,
        association_min_score=0.30,
        enemy_confirm_frames=3,
        player_anchor_radius_px=35,
    )
    system = PR27CombatSystem(config=config, cropper=ArenaCropper(ArenaRect(0, 0, 256, 192)))
    baseline = blank_frame()
    seed_blank_baseline(system, baseline)

    result = None
    for frame_index in range(3):
        frame = baseline.copy()
        draw_sprite(frame, 120, 96, (240, 120, 40))
        draw_sprite(frame, 30 + frame_index * 3, 30, (40, 210, 70))
        result = system.process(frame)

    assert result is not None
    enemies = [track for track in result.tracks if track.classification is SpriteClass.ENEMY]
    assert len(enemies) == 1
    assert enemies[0].observations >= 3
    assert result.target is not None
    assert result.target.track_id == enemies[0].track_id
    assert result.action in {
        CombatAction.CHASE_LEFT,
        CombatAction.CHASE_RIGHT,
        CombatAction.CHASE_UP,
        CombatAction.CHASE_DOWN,
        CombatAction.ATTACK,
    }


def test_unknown_identity_never_authorizes_attack() -> None:
    config = PR27Config(
        changed_ratio_threshold=0.01,
        minimum_component_area=4,
        scene_changed_min_cells=20,
        enable_context_enemy=False,
    )
    system = PR27CombatSystem(config=config, cropper=ArenaCropper(ArenaRect(0, 0, 256, 192)))
    baseline = blank_frame()
    seed_blank_baseline(system, baseline)
    frame = baseline.copy()
    draw_sprite(frame, 30, 30)
    result = system.process(frame)
    assert result.target is None
    assert result.action is CombatAction.NONE
    assert result.state is RoundState.SEARCHING


def test_temporarily_missing_id_is_retained_without_blind_action() -> None:
    config = PR27Config(
        changed_ratio_threshold=0.01,
        minimum_component_area=4,
        scene_changed_min_cells=20,
        association_min_score=0.30,
        enemy_confirm_frames=2,
        maximum_missing_frames=3,
        player_anchor_radius_px=35,
    )
    system = PR27CombatSystem(config=config, cropper=ArenaCropper(ArenaRect(0, 0, 256, 192)))
    baseline = blank_frame()
    seed_blank_baseline(system, baseline)

    result = None
    for _ in range(2):
        frame = baseline.copy()
        draw_sprite(frame, 120, 96, (240, 120, 40))
        draw_sprite(frame, 30, 30, (40, 210, 70))
        result = system.process(frame)
    assert result and result.target
    target_id = result.target.track_id

    missing = baseline.copy()
    draw_sprite(missing, 120, 96, (240, 120, 40))
    result = system.process(missing)
    target_track = next(track for track in result.tracks if track.track_id == target_id)
    assert target_track.track_state is TrackState.TEMPORARILY_MISSING
    assert result.target is not None and result.target.track_id == target_id
    assert result.action is CombatAction.NONE
    assert result.state is RoundState.TARGET_TEMPORARILY_MISSING


def test_scene_change_suspends_combat_and_invalidates_baselines() -> None:
    config = PR27Config(
        changed_ratio_threshold=0.01,
        minimum_component_area=4,
        scene_changed_cell_ratio=0.25,
        scene_changed_min_cells=2,
    )
    system = PR27CombatSystem(config=config, cropper=ArenaCropper(ArenaRect(0, 0, 256, 192)))
    baseline = blank_frame()
    seed_blank_baseline(system, baseline)
    shifted = np.full_like(baseline, 150)
    result = system.process(shifted)
    assert result.scene_changed is True
    assert result.state is RoundState.SCENE_CHANGED
    assert result.action is CombatAction.NONE
    assert all(not item.valid for item in system.baselines._baselines.values())


def test_baseline_roundtrip_preserves_native_cell_images(tmp_path: Path) -> None:
    frame = blank_frame(150, 130)
    cells = NativeGrid64().build(frame.shape)
    store = CellBaselineStore()
    for cell in cells:
        crop = frame[cell.y : cell.y + cell.height, cell.x : cell.x + cell.width].copy()
        crop[:] = (cell.row * 20, cell.column * 20, 10)
        store.set(cell, crop)
    path = tmp_path / "baseline.npz"
    store.save_npz(path, metadata={"jpeg": False, "resized": False, "cell_size_px": 64})

    loaded = CellBaselineStore()
    count = loaded.load_npz(path, cells)
    assert count == len(cells)
    assert loaded.metadata["jpeg"] is False
    assert loaded.metadata["resized"] is False
    edge = cells[-1]
    assert loaded.get(edge).image.shape[:2] == (edge.height, edge.width)
