from __future__ import annotations

import cv2
import numpy as np

from kage_combat_lab.pr27_cells import ArenaCropper, NativeGrid64
from kage_combat_lab.pr27_model import ArenaRect, CombatAction, FragmentRole, PR27Config, SpriteClass
from kage_combat_lab.pr27_native_grid import PR27CombatSystem


def blank(width=256, height=192):
    return np.zeros((height, width, 3), dtype=np.uint8)


def draw_sprite(frame, x, y, color=(40, 210, 70)):
    cv2.rectangle(frame, (x, y), (x + 18, y + 38), color, -1)
    cv2.rectangle(frame, (x + 5, y - 7), (x + 13, y), color, -1)


def build_system(**overrides):
    values = dict(
        changed_ratio_threshold=0.005,
        uncertain_ratio_threshold=0.002,
        minimum_component_area=4,
        minimum_fragment_pixels=4,
        minimum_observation_pixels=8,
        body_min_area=30,
        body_lock_min_confidence=0.20,
        association_min_score=0.20,
        target_association_min_score=0.18,
        target_minimum_appearance=0.20,
        enemy_confirm_frames=2,
        player_confirm_frames=1,
        player_anchor_radius_px=42,
        attack_distance_cells=1,
    )
    values.update(overrides)
    config = PR27Config(**values).normalized()
    system = PR27CombatSystem(config=config, cropper=ArenaCropper(ArenaRect(0, 0, 256, 192)))
    anchor = (256 * config.player_anchor_x_ratio, 192 * config.player_anchor_y_ratio)
    phase = NativeGrid64.phase_from_anchor(anchor, desired_local=(config.grid_player_local_x, config.grid_player_local_y))
    system.grid.set_phase(*phase)
    system.planner.set_grid_phase(phase)
    base = blank()
    _, arena = system.cropper.crop(base)
    for cell in system.grid.build(arena.shape):
        system.baselines.set(cell, arena[cell.y:cell.y+cell.height, cell.x:cell.x+cell.width])
    system._ensure_reference(arena)
    return system, base


def test_grid_phase_places_player_body_in_single_cell():
    config = PR27Config().normalized()
    anchor = (128.0, 104.0)
    phase = NativeGrid64.phase_from_anchor(anchor, desired_local=(config.grid_player_local_x, config.grid_player_local_y))
    grid = NativeGrid64(phase_x=phase[0], phase_y=phase[1])
    cells = grid.build((192, 256, 3))
    key = grid.cell_key_for_point(anchor, (192, 256, 3))
    cell = grid.cell_for_key(cells, key)
    assert cell is not None
    assert cell.x <= 119 and 137 < cell.x + cell.width
    assert cell.y <= 65 and 103 < cell.y + cell.height


def test_ground_strip_is_rejected_before_track_creation():
    system, base = build_system(enable_context_enemy=False)
    frame = base.copy()
    cv2.rectangle(frame, (30, 70), (95, 78), (255, 255, 255), -1)
    result = system.process(frame)
    assert result.tracks == ()
    assert any(key.startswith("GROUND_LIKE") for key in result.fragment_rejections)


def test_body_observation_has_unique_anchor_cell_and_body_bbox():
    system, base = build_system(enable_context_enemy=False)
    frame = base.copy()
    draw_sprite(frame, 30, 30)
    result = system.process(frame)
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.body_bbox is not None
    assert observation.body_anchor is not None
    assert observation.anchor_cell is not None
    assert len({observation.anchor_cell}) == 1
    assert all(fragment.role is FragmentRole.BODY_CANDIDATE for fragment in observation.fragments)


def test_trainer_zone_rejects_body_anchor_and_bbox():
    system, base = build_system(enable_context_enemy=True)
    system.trainer_exclusion_bbox = (0, 0, 100, 100)
    system.tracker.set_trainer_exclusion(system.trainer_exclusion_bbox)
    for _ in range(4):
        frame = base.copy()
        draw_sprite(frame, 30, 30)
        result = system.process(frame)
    assert not any(track.classification is SpriteClass.ENEMY for track in result.tracks)
    assert result.action is CombatAction.NONE
    assert any("TRAINER" in item for item in result.candidate_rejections)


def test_attack_requires_enemy_body_lock_anchor_cell_and_visual_facing():
    system, base = build_system()
    result = None
    actions = []
    for offset in (0, 2, 4, 6, 6, 6):
        frame = base.copy()
        draw_sprite(frame, 119, 65, (240, 120, 40))
        draw_sprite(frame, 150 + offset, 65, (40, 210, 70))
        result = system.process(frame)
        actions.append(result.action)
    assert result is not None
    enemies = [track for track in result.tracks if track.classification is SpriteClass.ENEMY]
    assert enemies
    enemy = enemies[0]
    assert enemy.body_bbox is not None and enemy.anchor_cell is not None
    assert result.target is not None
    assert result.target.body_bbox == enemy.body_bbox
    assert result.target.anchor_cell == enemy.anchor_cell
    assert CombatAction.TURN_RIGHT in actions
    # Synthetic rectangles have no directional visual evidence. PR27.7 must not
    # convert a TURN command into observed facing or release H on that basis.
    assert result.action is not CombatAction.ATTACK
    assert not result.facing_confirmed
    assert result.h_block_reason in {"VISUAL_FACING_NOT_CONFIRMED", "FACING_CONFIRMATION_COOLDOWN"}
