from __future__ import annotations

import inspect

import cv2
import numpy as np

from kage_combat_lab.pr27_native_grid import (
    ArenaCropper,
    ArenaRect,
    CombatAction,
    PR27CombatSystem,
    PR27Config,
)
from kage_combat_lab.pr27_overlay import PR27DebugOverlay
from kage_combat_lab.pr27_runtime_support import PR27PhysicalInput


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


def build_system(**overrides) -> tuple[PR27CombatSystem, np.ndarray]:
    values = dict(
        changed_ratio_threshold=0.01,
        uncertain_ratio_threshold=0.005,
        minimum_component_area=4,
        minimum_fragment_pixels=4,
        minimum_observation_pixels=8,
        scene_changed_min_cells=20,
        association_min_score=0.30,
        target_association_min_score=0.20,
        enemy_confirm_frames=2,
        player_anchor_radius_px=35,
    )
    values.update(overrides)
    config = PR27Config(**values)
    system = PR27CombatSystem(
        config=config,
        cropper=ArenaCropper(ArenaRect(0, 0, 256, 192)),
    )
    baseline = blank_frame()
    seed_blank_baseline(system, baseline)
    return system, baseline


def test_small_particle_does_not_create_track() -> None:
    system, baseline = build_system(
        minimum_fragment_pixels=20,
        minimum_observation_pixels=40,
        enable_context_enemy=False,
    )
    frame = baseline.copy()
    cv2.rectangle(frame, (20, 20), (22, 22), (255, 255, 255), -1)
    result = system.process(frame)
    assert result.tracks == ()


def test_lost_non_target_track_is_removed_from_memory() -> None:
    system, baseline = build_system(
        enable_context_enemy=False,
        maximum_missing_frames=2,
    )
    frame = baseline.copy()
    draw_sprite(frame, 30, 30)
    result = system.process(frame)
    assert result.tracks

    for _ in range(3):
        result = system.process(baseline.copy())

    assert result.tracks == ()
    assert system.tracker.tracks == {}


def test_target_id_survives_gap_without_binding_to_player() -> None:
    system, baseline = build_system(
        target_missing_grace_frames=6,
        maximum_missing_frames=2,
        target_focus_radius_cells=3,
    )
    result = None
    for x in (30, 34):
        frame = baseline.copy()
        draw_sprite(frame, 120, 96, (240, 120, 40))
        draw_sprite(frame, x, 30, (40, 210, 70))
        result = system.process(frame)

    assert result is not None and result.target is not None
    target_id = result.target.track_id

    for _ in range(4):
        frame = baseline.copy()
        draw_sprite(frame, 120, 96, (240, 120, 40))
        result = system.process(frame)
        assert result.target is not None
        assert result.target.track_id == target_id
        assert result.target.visible is False

    frame = baseline.copy()
    draw_sprite(frame, 120, 96, (240, 120, 40))
    draw_sprite(frame, 42, 30, (40, 210, 70))
    result = system.process(frame)
    assert result.target is not None
    assert result.target.track_id == target_id
    assert result.target.visible is True


def test_target_focus_ignores_distant_distractor() -> None:
    system, baseline = build_system(
        target_focus_radius_cells=2,
        maximum_active_tracks=8,
    )
    result = None
    for x in (30, 34):
        frame = baseline.copy()
        draw_sprite(frame, 120, 96, (240, 120, 40))
        draw_sprite(frame, x, 30, (40, 210, 70))
        result = system.process(frame)

    assert result is not None and result.target is not None
    target_id = result.target.track_id
    previous_ids = set(system.tracker.tracks)

    frame = baseline.copy()
    draw_sprite(frame, 120, 96, (240, 120, 40))
    draw_sprite(frame, 38, 30, (40, 210, 70))
    draw_sprite(frame, 220, 145, (255, 255, 255))
    result = system.process(frame)

    assert result.target is not None
    assert result.target.track_id == target_id
    assert set(system.tracker.tracks).issubset(previous_ids)


def test_baseline_caches_lab_image_once() -> None:
    system, _ = build_system(enable_context_enemy=False)
    baseline = next(iter(system.baselines._baselines.values()))
    assert baseline.lab_image.shape == baseline.image.shape


class FakeController:
    def __init__(self) -> None:
        self.repeat_keys: set[str] = set()
        self.activated = False
        self.states: list[tuple[str, ...]] = []

    def activate(self) -> None:
        self.activated = True

    def release_all(self) -> None:
        self.states.append(())

    def apply_keys(self, keys: tuple[str, ...]) -> None:
        self.states.append(tuple(keys))


def test_control_mode_arms_and_keeps_repeat_r_during_search() -> None:
    controller = FakeController()
    physical = PR27PhysicalInput(controller, sleep_fn=lambda _seconds: None)

    armed = physical.activate(mode="CONTROL_ENABLED")
    idle = physical.execute(CombatAction.NONE, mode="CONTROL_ENABLED")

    assert controller.activated is True
    assert controller.repeat_keys == {"r"}
    assert armed == ("R_ARMED",)
    assert idle == ("R_HELD_IDLE",)
    assert controller.states[-1] == ("r",)


def test_control_attack_returns_to_held_r() -> None:
    controller = FakeController()
    physical = PR27PhysicalInput(controller, sleep_fn=lambda _seconds: None)
    physical.activate(mode="CONTROL_ENABLED")

    actions = physical.execute(CombatAction.ATTACK, mode="CONTROL_ENABLED")

    assert actions == ("R_AUTHORIZED", "H_80MS")
    assert ("h", "r") in controller.states
    assert controller.states[-1] == ("r",)


def test_debug_overlay_has_no_blocking_wait_key() -> None:
    source = inspect.getsource(PR27DebugOverlay.show)
    assert "cv2.waitKey(0)" not in source
    assert "cv2.waitKey(1)" in source
