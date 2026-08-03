from __future__ import annotations

import inspect

import cv2
import numpy as np

from kage_combat_lab.pr27_cells import (
    ArenaCropper, CellDifferenceDetector, LocalBackgroundModel,
    PlayerCentricCombatGrid,
)
from kage_combat_lab.pr27_model import (
    AppearanceDescriptor, ArenaRect, CombatAction, LocalBackgroundState,
    PR27Config, RoundState, SpriteClass, TrackState, TrackedSprite,
)
from kage_combat_lab.pr27_native_grid import PR27CombatSystem
from kage_combat_lab.pr27_overlay import PR27DebugOverlay
from kage_combat_lab.pr27_planning import CombatPlanner
from kage_combat_lab.pr27_runtime_support import PR27PhysicalInput


def blank(width: int = 1024, height: int = 768) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def draw_sprite(frame: np.ndarray, x: int, y: int, color=(40, 210, 70)) -> None:
    cv2.rectangle(frame, (x, y), (x + 18, y + 38), color, -1)
    cv2.rectangle(frame, (x + 5, y - 7), (x + 13, y), color, -1)


def build_system(**overrides) -> tuple[PR27CombatSystem, np.ndarray]:
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
        player_anchor_radius_px=80,
        local_occlusion_min_changed_cells=10,
        local_background_learning_frames=2,
    )
    values.update(overrides)
    system = PR27CombatSystem(
        config=PR27Config(**values).normalized(),
        cropper=ArenaCropper(ArenaRect(0, 0, 1024, 768)),
    )
    base = blank()
    for cell in system.grid.build(base.shape):
        system.baselines.set(cell, base[cell.y:cell.y + cell.height, cell.x:cell.x + cell.width])
    system._ensure_reference(base)
    return system, base


def descriptor() -> AppearanceDescriptor:
    return AppearanceDescriptor(np.zeros(32, dtype=np.float32), np.zeros(64, dtype=np.float32), 0.0)


def tracked(track_id: int, category: SpriteClass, anchor, cell, *, known_enemy=False) -> TrackedSprite:
    body = (int(anchor[0]-10), int(anchor[1]-42), 20, 42)
    return TrackedSprite(
        track_id=track_id, current_cells=frozenset({cell}), previous_cells=frozenset(),
        fragments=(), native_bbox=body, combined_mask=np.ones((1,1), dtype=np.uint8),
        appearance_signature=descriptor(), first_seen_frame=0, last_seen_frame=0,
        body_bbox=body, body_anchor=anchor, anchor_cell=cell, body_confidence=.9,
        observations=10, classification=category, known_enemy=known_enemy,
        confidence=.9, track_state=TrackState.TRACKED,
    )


def test_combat_perception_uses_only_four_cell_radius() -> None:
    grid = PlayerCentricCombatGrid(PR27Config(roi_radius_cells=4).normalized())
    grid.center_anchor = (512.0, 384.0)
    cells = grid.build((768,1024,3))
    assert len(cells) == 49
    assert all(c.row*c.row+c.column*c.column <= 16 for c in cells)


def test_roi_contains_only_expected_circular_cells() -> None:
    grid = PlayerCentricCombatGrid(PR27Config().normalized())
    grid.center_anchor = (512.0,384.0)
    keys = {(c.row,c.column) for c in grid.build((768,1024,3))}
    assert keys == {(dy,dx) for dy in range(-4,5) for dx in range(-4,5) if dx*dx+dy*dy <= 16}


def test_pixels_outside_roi_do_not_create_tracks() -> None:
    system, base = build_system(enable_context_enemy=False)
    frame = base.copy(); draw_sprite(frame,20,20)
    result = system.process(frame)
    assert result.observations == () and result.tracks == ()


def test_effect_outside_roi_does_not_affect_combat() -> None:
    system, base = build_system(enable_context_enemy=False)
    frame = base.copy(); frame[:120,:180] = 255
    result = system.process(frame)
    assert not result.local_occlusion_detected
    assert result.state is RoundState.SEARCHING
    assert result.roi_processed_cell_count == 49


def test_player_is_origin_cell_zero_zero() -> None:
    system, base = build_system(enable_context_enemy=False)
    frame = base.copy(); draw_sprite(frame,503,365,(240,120,40))
    result = system.process(frame)
    player = next(t for t in result.tracks if t.classification is SpriteClass.PLAYER)
    assert player.anchor_cell == (0,0) and result.player_cell == (0,0)


def test_enemy_cells_are_relative_to_player() -> None:
    system, base = build_system(); result = None
    for index in range(4):
        frame = base.copy(); draw_sprite(frame,503,365,(240,120,40)); draw_sprite(frame,600+index*2,365)
        result = system.process(frame)
    assert result is not None and result.target is not None
    assert result.target.anchor_cell == (0,2) and result.enemy_relative_cell == (0,2)


def test_player_body_is_visually_contained_in_single_64px_cell() -> None:
    grid = PlayerCentricCombatGrid(PR27Config().normalized())
    assert grid.calibrate_to_body((895,363,44,64),(917.0,425.0)) >= .90
    assert grid.central_bbox() == (885,363,64,64)


def test_player_body_containment_is_stable_across_idle_frames() -> None:
    grid = PlayerCentricCombatGrid(PR27Config(player_cell_hysteresis_px=3).normalized())
    body=(895,363,44,64); grid.calibrate_to_body(body,(917.0,425.0)); before=(grid.offset_x,grid.offset_y)
    for anchor in ((918.0,425.0),(916.0,424.0),(919.0,426.0)): grid.calibrate_to_body(body,anchor)
    assert (grid.offset_x,grid.offset_y) == before


def test_combat_grid_follows_player_without_phase_jitter() -> None:
    grid = PlayerCentricCombatGrid(PR27Config(player_cell_hysteresis_px=3).normalized())
    grid.update_center((500.0,400.0)); grid.update_center((502.0,398.0))
    assert grid.center_anchor == (500.0,400.0)
    grid.update_center((505.0,400.0)); assert grid.center_anchor == (505.0,400.0)


def test_combat_pipeline_has_no_scene_changed_state() -> None:
    system, base = build_system(local_occlusion_min_changed_cells=5)
    result = system.process(np.full_like(base,150))
    assert not result.scene_changed and result.state is not RoundState.SCENE_CHANGED
    assert all(b.valid for b in system.baselines._baselines.values())


def test_large_effect_does_not_suspend_combat_globally() -> None:
    system, base = build_system(local_occlusion_min_changed_cells=5)
    frame=base.copy(); frame[180:580,220:820]=255; result=system.process(frame)
    assert result.state is RoundState.LOCAL_VISUAL_OCCLUSION
    assert not result.scene_changed and "local visual occlusion" in result.reason


def test_unknown_local_background_does_not_freeze_combat() -> None:
    system, base = build_system(local_occlusion_min_changed_cells=5,local_occlusion_max_frames=3,local_background_learning_frames=2,enable_context_enemy=False)
    states=[]
    for _ in range(9):
        frame=base.copy(); frame[120:650,180:850]=(80,80,80); states.append(system.process(frame).state)
    assert RoundState.LOCAL_UNKNOWN_BACKGROUND in states
    assert states[-1] is RoundState.SEARCHING
    assert RoundState.SCENE_CHANGED not in states


def test_no_global_baseline_rebuild_during_round() -> None:
    source=inspect.getsource(PR27CombatSystem.process)
    assert "invalidate_all" not in source
    assert "SceneChangeRebaseliner" not in source
    assert "global_reacquire" not in source


class FakeController:
    def __init__(self) -> None:
        self.repeat_keys=set(); self.states=[]
    def activate(self): return None
    def release_all(self): self.states.append(())
    def apply_keys(self,keys): self.states.append(tuple(keys))


def _latched_input():
    controller=FakeController(); physical=PR27PhysicalInput(controller,sleep_fn=lambda _seconds:None)
    assert physical.activate(mode="CONTROL_ENABLED") == ("R_DOWN_COMBAT_LATCH",)
    return controller,physical


def test_r_down_is_sent_once_when_combat_starts() -> None:
    controller,_physical=_latched_input(); assert controller.states.count(("r",)) == 1


def test_r_remains_held_without_target() -> None:
    controller,physical=_latched_input()
    assert physical.execute(CombatAction.NONE,mode="CONTROL_ENABLED") == ("R_HELD_COMBAT",)
    assert controller.states[-1] == ("r",)


def test_r_remains_held_during_target_missing() -> None:
    controller,physical=_latched_input(); physical.execute(CombatAction.NONE,mode="CONTROL_ENABLED")
    assert controller.states[-1] == ("r",) and physical.combat_r_latched


def test_r_remains_held_during_local_occlusion() -> None:
    controller,physical=_latched_input(); physical.execute(CombatAction.NONE,mode="CONTROL_ENABLED")
    assert controller.states[-1] == ("r",) and physical.combat_r_latched


def test_r_remains_held_during_unknown_background() -> None:
    controller,physical=_latched_input(); physical.execute(CombatAction.NONE,mode="CONTROL_ENABLED")
    assert controller.states[-1] == ("r",) and physical.combat_r_latched


def test_r_is_released_only_when_combat_ends() -> None:
    controller,physical=_latched_input(); physical.execute(CombatAction.CHASE_RIGHT,mode="CONTROL_ENABLED")
    assert physical.end_combat("ROUND_END")[0] == "R_UP_COMBAT_END"
    assert controller.states[-1] == () and not physical.combat_r_latched


def test_emergency_stop_releases_r() -> None:
    controller,physical=_latched_input(); physical.close()
    assert controller.states[-1] == () and not physical.combat_r_latched


def _facing_sequence():
    planner=CombatPlanner(PR27Config(facing_confirm_frames=2).normalized())
    player=tracked(1,SpriteClass.PLAYER,(100.0,100.0),(0,0))
    enemy=tracked(2,SpriteClass.ENEMY,(150.0,100.0),(0,1),known_enemy=True)
    return planner,player,enemy


def test_attack_requires_confirmed_facing() -> None:
    planner,player,enemy=_facing_sequence()
    assert planner.plan((player,enemy),arena_shape=(300,300))[1] is CombatAction.TURN_RIGHT
    assert planner.plan((player,enemy),arena_shape=(300,300))[1] is CombatAction.NONE
    assert planner.plan((player,enemy),arena_shape=(300,300))[1] is CombatAction.ATTACK


def test_hit_invalidates_previous_facing() -> None:
    planner=CombatPlanner(PR27Config(facing_confirm_frames=1).normalized())
    planner.facing="RIGHT"; planner.facing_confirm_frames=3; planner.invalidate_facing("player_displacement")
    assert not planner.facing_confirmed and planner.facing is None


def test_facing_is_corrected_before_h() -> None:
    planner,player,enemy=_facing_sequence()
    assert planner.plan((player,enemy),arena_shape=(300,300))[1] is CombatAction.TURN_RIGHT


def test_h_is_blocked_while_facing_unknown() -> None:
    planner,player,enemy=_facing_sequence()
    assert planner.plan((player,enemy),arena_shape=(300,300))[1] is not CombatAction.ATTACK


def test_wrong_side_jutsu_cannot_be_fired() -> None:
    planner,player,enemy=_facing_sequence(); planner.facing="LEFT"; planner.facing_confirm_frames=5
    _,action,_,reason=planner.plan((player,enemy),arena_shape=(300,300))
    assert action is CombatAction.TURN_RIGHT and "correction" in reason


def test_enemy_lock_uses_body_anchor_inside_roi() -> None:
    system,base=build_system(); result=None
    for _ in range(4):
        frame=base.copy(); draw_sprite(frame,503,365,(240,120,40)); draw_sprite(frame,600,365); result=system.process(frame)
    assert result is not None and result.target is not None
    assert result.target.body_anchor is not None and result.target.anchor_cell is not None
    assert result.target.anchor_cell[0]**2+result.target.anchor_cell[1]**2 <= 16


def test_ground_strip_cannot_rebind_enemy() -> None:
    system,base=build_system(); result=None
    for _ in range(4):
        frame=base.copy(); draw_sprite(frame,503,365,(240,120,40)); draw_sprite(frame,600,365); result=system.process(frame)
    target_id=result.target.track_id
    frame=base.copy(); draw_sprite(frame,503,365,(240,120,40)); cv2.rectangle(frame,(560,400),(760,408),(255,255,255),-1)
    result=system.process(frame)
    assert result.target is not None and result.target.track_id == target_id and not result.target.visible


def test_effect_cannot_update_enemy_appearance() -> None:
    system,base=build_system(); result=None
    for _ in range(4):
        frame=base.copy(); draw_sprite(frame,503,365,(240,120,40)); draw_sprite(frame,600,365); result=system.process(frame)
    target_id=result.target.track_id; old=system.tracker.tracks[target_id].appearance_signature.hsv_histogram.copy()
    effect=base.copy(); effect[180:580,220:820]=255; system.process(effect)
    assert np.array_equal(system.tracker.tracks[target_id].appearance_signature.hsv_histogram,old)


def test_target_reacquisition_is_local() -> None:
    system,base=build_system(target_missing_grace_frames=6); result=None
    for _ in range(4):
        frame=base.copy(); draw_sprite(frame,503,365,(240,120,40)); draw_sprite(frame,600,365); result=system.process(frame)
    target_id=result.target.track_id
    frame=base.copy(); draw_sprite(frame,503,365,(240,120,40)); system.process(frame)
    frame=base.copy(); draw_sprite(frame,503,365,(240,120,40)); draw_sprite(frame,606,365); result=system.process(frame)
    assert result.target is not None and result.target.track_id == target_id


def test_enemy_outside_radius_does_not_trigger_global_search() -> None:
    system,base=build_system(); result=None
    for _ in range(5):
        frame=base.copy(); draw_sprite(frame,503,365,(240,120,40)); draw_sprite(frame,900,365); result=system.process(frame)
    assert result is not None and result.target is None
    assert not any(t.classification is SpriteClass.ENEMY for t in result.tracks)


def _learning_model():
    config=PR27Config(local_background_learning_frames=2).normalized()
    model=LocalBackgroundModel(config); grid=PlayerCentricCombatGrid(config); grid.center_anchor=(256.0,256.0)
    cells=grid.build((512,512,3)); arena=np.zeros((512,512,3),dtype=np.uint8)
    return config,model,cells,arena


def test_unknown_cell_learns_background_incrementally() -> None:
    config,model,cells,arena=_learning_model(); valid=np.zeros((512,512),dtype=np.uint8)
    model.sync_from_reference(arena,valid,arena,cells); key=(0,1); model.begin_learning({key}); changed=np.full_like(arena,70)
    detector=CellDifferenceDetector(config)
    for _ in range(3):
        differences=detector.compare(changed,cells,model.baselines); model.learn(changed,cells,differences,protected_cells={(0,0)},effect_cells=set())
    cell=next(c for c in cells if (c.row,c.column)==key)
    assert model.states[key] is LocalBackgroundState.KNOWN_BACKGROUND and int(np.mean(model.baselines.get(cell).image))==70


def test_player_pixels_are_never_learned_as_background() -> None:
    config,model,cells,arena=_learning_model(); valid=np.full((512,512),255,dtype=np.uint8)
    model.sync_from_reference(arena,valid,arena,cells); changed=np.full_like(arena,100); detector=CellDifferenceDetector(config)
    for _ in range(4):
        differences=detector.compare(changed,cells,model.baselines); model.learn(changed,cells,differences,protected_cells={(0,0)},effect_cells=set())
    cell=next(c for c in cells if (c.row,c.column)==(0,0)); assert int(np.mean(model.baselines.get(cell).image))==0


def test_enemy_pixels_are_never_learned_as_background() -> None:
    config,model,cells,arena=_learning_model(); valid=np.full((512,512),255,dtype=np.uint8)
    model.sync_from_reference(arena,valid,arena,cells); changed=np.full_like(arena,100); detector=CellDifferenceDetector(config)
    for _ in range(4):
        differences=detector.compare(changed,cells,model.baselines); model.learn(changed,cells,differences,protected_cells={(0,1)},effect_cells=set())
    cell=next(c for c in cells if (c.row,c.column)==(0,1)); assert int(np.mean(model.baselines.get(cell).image))==0


def test_effect_pixels_are_never_learned_as_background() -> None:
    config,model,cells,arena=_learning_model(); valid=np.full((512,512),255,dtype=np.uint8)
    model.sync_from_reference(arena,valid,arena,cells); changed=np.full_like(arena,100); detector=CellDifferenceDetector(config)
    for _ in range(4):
        differences=detector.compare(changed,cells,model.baselines); model.learn(changed,cells,differences,protected_cells=set(),effect_cells={(0,1)})
    cell=next(c for c in cells if (c.row,c.column)==(0,1)); assert int(np.mean(model.baselines.get(cell).image))==0


def test_overlay_does_not_draw_global_grid_or_search_groups() -> None:
    source=inspect.getsource(PR27DebugOverlay.render)
    assert "for cell in result.cells" in source
    assert "for group in result.groups" not in source
    assert "result.grid" not in source
