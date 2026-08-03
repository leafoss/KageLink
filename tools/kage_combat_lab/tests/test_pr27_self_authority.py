from __future__ import annotations

import inspect
import time
from pathlib import Path

import numpy as np

from kage_combat_lab.pr27_async_debug import AsyncDebugWriter
from kage_combat_lab.pr27_facing import FacingObserver
from kage_combat_lab.pr27_identity import SelfTracker, lock_track_role
from kage_combat_lab.pr27_model import (
    AppearanceDescriptor,
    CombatAction,
    PR27Config,
    RecoveryState,
    RoundState,
    SpriteClass,
    SpriteObservation,
    SpriteRole,
    TrackState,
    TrackedSprite,
)
from kage_combat_lab.pr27_overlap import MergedBodyDetector, role_conflict
from kage_combat_lab.pr27_overlay import PR27DebugOverlay
from kage_combat_lab.pr27_planning import CombatPlanner
from kage_combat_lab.pr27_runtime_support import PR27PhysicalInput
from kage_combat_lab.pr27_tracker import SpriteTracker


def descriptor(seed: float = 0.0) -> AppearanceDescriptor:
    hist = np.zeros(32, dtype=np.float32)
    hist[int(seed) % 32] = 1.0
    structure = np.zeros(64, dtype=np.float32)
    structure[int(seed * 3) % 64] = 1.0
    return AppearanceDescriptor(hist, structure, 0.1 + seed * 0.01)


def observation(
    observation_id: int,
    anchor: tuple[float, float],
    cell: tuple[int, int],
    *,
    width: int = 20,
    height: int = 42,
    seed: float = 0.0,
) -> SpriteObservation:
    bbox = (int(anchor[0] - width / 2), int(anchor[1] - height + 2), width, height)
    return SpriteObservation(
        observation_id=observation_id,
        source_group_id=1,
        fragments=(),
        cells=frozenset({cell}),
        native_bbox=bbox,
        combined_mask=np.ones((height, width), dtype=np.uint8),
        crop=np.zeros((height, width, 3), dtype=np.uint8),
        descriptor=descriptor(seed),
        body_bbox=bbox,
        body_anchor=anchor,
        anchor_cell=cell,
        body_confidence=0.9,
    )


def track(
    track_id: int,
    role: SpriteRole,
    anchor: tuple[float, float],
    cell: tuple[int, int],
    *,
    seed: float = 0.0,
) -> TrackedSprite:
    bbox = (int(anchor[0] - 10), int(anchor[1] - 40), 20, 42)
    category = {
        SpriteRole.SELF: SpriteClass.PLAYER,
        SpriteRole.ENEMY: SpriteClass.ENEMY,
        SpriteRole.NPC: SpriteClass.NPC,
    }.get(role, SpriteClass.UNKNOWN)
    value = TrackedSprite(
        track_id=track_id,
        current_cells=frozenset({cell}),
        previous_cells=frozenset(),
        fragments=(),
        native_bbox=bbox,
        combined_mask=np.ones((42, 20), dtype=np.uint8),
        appearance_signature=descriptor(seed),
        first_seen_frame=0,
        last_seen_frame=0,
        body_bbox=bbox,
        body_anchor=anchor,
        anchor_cell=cell,
        body_confidence=0.9,
        observations=10,
        classification=category,
        known_enemy=role is SpriteRole.ENEMY,
        confidence=0.9,
        track_state=TrackState.TRACKED,
        observation_id=track_id + 100,
        role=role,
        role_locked=role in {SpriteRole.SELF, SpriteRole.ENEMY, SpriteRole.NPC},
        role_assigned_frame=0,
        role_source="test",
        role_confidence=0.9,
        predicted_anchor=anchor,
    )
    value.movement_history.append(anchor)
    return value


def test_exactly_one_self_exists_per_round() -> None:
    tracker = SelfTracker(PR27Config().normalized())
    self_track, reserved = tracker.update(
        (observation(1, (100.0, 100.0), (0, 0)),),
        frame_index=0,
        arena_shape=(200, 200),
    )
    assert self_track is not None
    assert self_track.track_id == 0
    assert self_track.effective_role is SpriteRole.SELF
    assert reserved == frozenset({1})


def test_self_role_is_immutable() -> None:
    value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0))
    assert not lock_track_role(
        value,
        SpriteRole.ENEMY,
        frame_index=5,
        source="invalid_association",
        confidence=1.0,
    )
    assert value.effective_role is SpriteRole.SELF
    assert value.role_conflict_reason == "ROLE_FLIP_BLOCKED:SELF->ENEMY"


def test_enemy_can_never_become_self() -> None:
    value = track(7, SpriteRole.ENEMY, (120.0, 100.0), (0, 1))
    assert not lock_track_role(
        value,
        SpriteRole.SELF,
        frame_index=9,
        source="centrality",
        confidence=1.0,
    )
    assert value.effective_role is SpriteRole.ENEMY


def test_npc_can_never_become_self_during_round() -> None:
    value = track(18, SpriteRole.NPC, (140.0, 100.0), (0, 1))
    assert not lock_track_role(
        value,
        SpriteRole.SELF,
        frame_index=12,
        source="frame_475_regression",
        confidence=1.0,
    )
    assert value.effective_role is SpriteRole.NPC


def test_self_observation_is_reserved_before_enemy_association() -> None:
    config = PR27Config(enemy_confirm_frames=2).normalized()
    self_tracker = SelfTracker(config)
    generic = SpriteTracker(config)
    item = observation(1, (100.0, 100.0), (0, 0))
    self_track, reserved = self_tracker.update((item,), frame_index=0, arena_shape=(200, 200))
    tracks = generic.update(
        (item,),
        frame_index=0,
        arena_shape=(200, 200),
        self_track=self_track,
        reserved_observation_ids=reserved,
    )
    assert tracks == ()
    assert generic.shared_observation_blocked


def test_self_and_enemy_cannot_share_observation() -> None:
    self_value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0))
    enemy_value = track(2, SpriteRole.ENEMY, (105.0, 100.0), (0, 0))
    enemy_value.observation_id = self_value.observation_id
    evidence = role_conflict(self_value, enemy_value)
    assert evidence.conflict
    assert evidence.shared_observation
    assert evidence.reason == "SHARED_OBSERVATION_BLOCKED"


def test_near_coincident_anchors_create_merged_body() -> None:
    config = PR27Config(merged_body_iou_threshold=0.05).normalized()
    detector = MergedBodyDetector(config)
    self_value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0))
    enemy_value = track(2, SpriteRole.ENEMY, (108.0, 100.0), (0, 0))
    merged = observation(8, (104.0, 100.0), (0, 0), width=42, height=48)
    evidence = detector.detect((merged,), self_track=self_value, enemy_track=enemy_value)
    assert evidence.detected
    assert merged.merged_body
    assert merged.reserved_role is SpriteRole.MERGED_BODY


def test_merged_body_preserves_self_role() -> None:
    self_value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0))
    enemy_value = track(2, SpriteRole.ENEMY, (108.0, 100.0), (0, 0))
    MergedBodyDetector(PR27Config().normalized()).detect(
        (observation(3, (104.0, 100.0), (0, 0), width=42, height=48),),
        self_track=self_value,
        enemy_track=enemy_value,
    )
    assert self_value.effective_role is SpriteRole.SELF
    assert enemy_value.effective_role is SpriteRole.ENEMY


def test_same_cell_uses_subcell_anchor_direction() -> None:
    planner = CombatPlanner(PR27Config(facing_confirm_frames=2).normalized(), require_visual_facing=True)
    self_value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0))
    enemy_value = track(2, SpriteRole.ENEMY, (112.0, 100.0), (0, 0))
    planner.update_facing_observation("RIGHT", confirmed=True)
    target, action, state, _ = planner.plan((self_value, enemy_value), arena_shape=(200, 200))
    assert target is not None
    assert target.direction == "RIGHT"
    assert target.relative_anchor_px == (12.0, 0.0)
    assert action is CombatAction.ATTACK
    assert state is RoundState.ATTACKING


def test_same_cell_does_not_imply_unknown_direction() -> None:
    planner = CombatPlanner(PR27Config().normalized(), require_visual_facing=True)
    assert planner._direction((100.0, 100.0), (94.0, 100.0)) == "LEFT"


def test_overlap_unknown_watchdog_breaks_deadlock() -> None:
    config = PR27Config(
        close_idle_soft_frames=2,
        close_idle_turn_frames=3,
        close_idle_drop_frames=5,
        separation_cooldown_frames=1,
    ).normalized()
    planner = CombatPlanner(config, require_visual_facing=True)
    self_value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0))
    enemy_value = track(2, SpriteRole.ENEMY, (101.0, 100.0), (0, 0))
    actions = []
    states = []
    for _ in range(5):
        _, action, state, _ = planner.plan((self_value, enemy_value), arena_shape=(200, 200))
        actions.append(action)
        states.append(state)
    assert RoundState.SEPARATION_RECOVERY in states or RoundState.CLOSE_REACQUIRE in states
    assert any(action.value.startswith("SEPARATE_") for action in actions) or planner.request_target_reacquire


def test_enemy_cell_zero_zero_cannot_remain_stable_indefinitely() -> None:
    config = PR27Config(close_idle_soft_frames=2, close_idle_turn_frames=3, close_idle_drop_frames=4).normalized()
    planner = CombatPlanner(config, require_visual_facing=True)
    self_value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0))
    enemy_value = track(2, SpriteRole.ENEMY, (101.0, 100.0), (0, 0))
    last_state = None
    for _ in range(6):
        _, _, last_state, _ = planner.plan((self_value, enemy_value), arena_shape=(200, 200))
    assert last_state in {RoundState.CLOSE_REACQUIRE, RoundState.SEPARATION_RECOVERY}


def test_visible_close_enemy_is_not_ignored() -> None:
    planner = CombatPlanner(PR27Config(close_idle_soft_frames=2).normalized(), require_visual_facing=True)
    self_value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0))
    _, action, state, reason = planner.plan(
        (self_value,),
        arena_shape=(200, 200),
        close_candidate_count=1,
    )
    assert action is CombatAction.NONE
    assert state is RoundState.CLOSE_TARGET_SEARCH
    assert "visible" in reason


def test_close_enemy_idle_has_bounded_duration() -> None:
    planner = CombatPlanner(PR27Config(close_idle_soft_frames=2).normalized(), require_visual_facing=True)
    self_value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0))
    for _ in range(2):
        planner.plan((self_value,), arena_shape=(200, 200), close_candidate_count=1)
    assert planner.request_target_reacquire


def test_turn_command_does_not_confirm_visual_facing() -> None:
    observer = FacingObserver(PR27Config(facing_confirm_frames=2).normalized())
    observer.note_physical_actions(("R_HELD_COMBAT", "TURN_RIGHT_60MS"))
    assert observer.commanded == "RIGHT"
    assert observer.observed is None
    assert not observer.confirmed


def test_h_requires_visual_facing_confirmation() -> None:
    planner = CombatPlanner(PR27Config(facing_confirm_frames=2).normalized(), require_visual_facing=True)
    self_value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0))
    enemy_value = track(2, SpriteRole.ENEMY, (112.0, 100.0), (0, 0))
    _, action, state, _ = planner.plan((self_value, enemy_value), arena_shape=(200, 200))
    assert action is CombatAction.TURN_RIGHT
    assert state is RoundState.CLOSE_FACING_RECOVERY


class FakeController:
    def __init__(self) -> None:
        self.repeat_keys = set()
        self.states = []

    def activate(self):
        return None

    def release_all(self):
        self.states.append(())

    def apply_keys(self, keys):
        self.states.append(tuple(keys))


def test_separation_pulse_keeps_r_held(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR27_SEPARATION_PULSE_MS", "60")
    controller = FakeController()
    physical = PR27PhysicalInput(controller, sleep_fn=lambda _seconds: None)
    physical.activate(mode="CONTROL_ENABLED")
    actions = physical.execute(CombatAction.SEPARATE_LEFT, mode="CONTROL_ENABLED")
    assert actions[0] == "R_HELD_COMBAT"
    assert "H_BLOCKED_SEPARATION" in actions
    assert controller.states[-1] == ("r",)
    assert physical.combat_r_latched


def test_separation_pulse_blocks_h(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR27_SEPARATION_PULSE_MS", "60")
    physical = PR27PhysicalInput(FakeController(), sleep_fn=lambda _seconds: None)
    physical.activate(mode="CONTROL_ENABLED")
    actions = physical.execute(CombatAction.SEPARATE_RIGHT, mode="CONTROL_ENABLED")
    assert not any(action.startswith("H_") and action != "H_BLOCKED_SEPARATION" for action in actions)


def test_roi_debug_frames_are_saved_asynchronously(tmp_path: Path) -> None:
    writes = []

    def fake_write(path: str, image: np.ndarray) -> bool:
        writes.append((path, image.shape))
        return True

    writer = AsyncDebugWriter(max_queue=4, imwrite=fake_write)
    assert writer.enqueue(np.zeros((64, 64, 3), dtype=np.uint8), tmp_path / "frame.png")
    writer.close(timeout=2.0)
    assert writer.saved_frames == 1
    assert writes[0][0].endswith("frame.png")


def test_png_write_does_not_block_combat_loop(tmp_path: Path) -> None:
    def slow_write(_path: str, _image: np.ndarray) -> bool:
        time.sleep(0.05)
        return True

    writer = AsyncDebugWriter(max_queue=2, imwrite=slow_write)
    started = time.perf_counter()
    writer.enqueue(np.zeros((32, 32, 3), dtype=np.uint8), tmp_path / "a.png")
    elapsed = time.perf_counter() - started
    writer.close(timeout=2.0)
    assert elapsed < 0.02


def test_overlay_never_draws_enemy_as_player() -> None:
    source = inspect.getsource(PR27DebugOverlay._role_label)
    assert "track.track_id == result.player_track_id" in source
    assert "INVALID ROLE FLIP" in source


def test_frame_475_enemy_cannot_be_labeled_player() -> None:
    config = PR27Config(
        enemy_confirm_frames=2,
        player_anchor_radius_px=80,
        self_association_min_score=0.30,
        association_min_score=0.20,
        target_association_min_score=0.18,
        target_minimum_appearance=0.20,
        body_lock_min_confidence=0.20,
    ).normalized()
    self_tracker = SelfTracker(config)
    generic = SpriteTracker(config)
    self_id = None
    for frame_index in range(5):
        self_observation = observation(1, (100.0, 100.0), (0, 0), seed=1.0)
        enemy_observation = observation(2, (132.0, 100.0), (0, 1), seed=7.0)
        self_track, reserved = self_tracker.update(
            (self_observation, enemy_observation),
            frame_index=frame_index,
            arena_shape=(200, 200),
        )
        generic_tracks = generic.update(
            (self_observation, enemy_observation),
            frame_index=frame_index,
            arena_shape=(200, 200),
            self_track=self_track,
            reserved_observation_ids=reserved,
        )
        self_id = self_track.track_id
    assert self_id == 0
    assert self_tracker.track is not None
    assert self_tracker.track.effective_role is SpriteRole.SELF
    assert all(track.effective_role is not SpriteRole.SELF for track in generic_tracks)
    assert all(track.classification is not SpriteClass.PLAYER for track in generic_tracks)


def test_round_one_role_invariants_survive_overlap() -> None:
    config = PR27Config(close_idle_soft_frames=2, close_idle_turn_frames=3, close_idle_drop_frames=5).normalized()
    self_value = track(0, SpriteRole.SELF, (100.0, 100.0), (0, 0), seed=1.0)
    enemy_value = track(2, SpriteRole.ENEMY, (108.0, 100.0), (0, 0), seed=7.0)
    merged = observation(9, (104.0, 100.0), (0, 0), width=44, height=52, seed=4.0)
    evidence = MergedBodyDetector(config).detect(
        (merged,),
        self_track=self_value,
        enemy_track=enemy_value,
    )
    planner = CombatPlanner(config, require_visual_facing=True)
    _, action, state, _ = planner.plan(
        (self_value, enemy_value),
        arena_shape=(200, 200),
        merged_body=evidence.detected,
    )
    assert self_value.effective_role is SpriteRole.SELF
    assert enemy_value.effective_role is SpriteRole.ENEMY
    assert action is not CombatAction.ATTACK
    assert state is RoundState.MERGED_BODY_RECOVERY
    assert planner.h_block_reason == "MERGED_BODY"
