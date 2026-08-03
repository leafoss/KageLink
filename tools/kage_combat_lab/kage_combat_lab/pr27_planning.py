from __future__ import annotations

from typing import Sequence

from .pr27_model import (
    CombatAction, CombatTarget, LocalPerceptionState, PR27Config,
    RoundState, SpriteClass, TrackState, TrackedSprite,
)


class CombatPlanner:
    """Plans exclusively from player-relative body anchors and authoritative cells."""

    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.latched_enemy_track_id: int | None = None
        self.grid_phase = (0, 0)
        self.facing: str | None = None
        self.facing_confirm_frames = 0
        self.facing_invalid_reason: str | None = "startup"
        self.last_facing_correction_action: str | None = None
        self._plan_frame = 0
        self._last_correction_frame = -10_000

    def set_grid_phase(self, phase: tuple[int, int]) -> None:
        self.grid_phase = int(phase[0]), int(phase[1])

    def invalidate_facing(self, reason: str) -> None:
        self.facing = None
        self.facing_confirm_frames = 0
        self.facing_invalid_reason = str(reason)
        self.last_facing_correction_action = None

    @property
    def facing_confirmed(self) -> bool:
        return self.facing is not None and self.facing_confirm_frames >= self.config.facing_confirm_frames

    @staticmethod
    def _direction(player: tuple[float, float], target: tuple[float, float]) -> str | None:
        dx, dy = target[0]-player[0], target[1]-player[1]
        if max(abs(dx), abs(dy)) < 4.0:
            return None
        if abs(dx) >= abs(dy):
            return "RIGHT" if dx > 0 else "LEFT"
        return "DOWN" if dy > 0 else "UP"

    @staticmethod
    def _distance_cells(relative_cell: tuple[int, int]) -> int:
        return max(abs(relative_cell[0]), abs(relative_cell[1]))

    def _record_direction(self, direction: str | None, *, correction=False) -> None:
        if direction is None:
            return
        if self.facing == direction:
            self.facing_confirm_frames += 1
        else:
            self.facing, self.facing_confirm_frames = direction, 1
        if correction:
            self._last_correction_frame = self._plan_frame
            self.last_facing_correction_action = f"TURN_{direction}"
        else:
            self.last_facing_correction_action = None
        if self.facing_confirmed:
            self.facing_invalid_reason = None

    def _target(self, enemy: TrackedSprite, *, visible: bool, direction, distance) -> CombatTarget:
        assert enemy.body_anchor is not None
        return CombatTarget(
            enemy.track_id, enemy.current_cells, enemy.body_anchor, direction, distance,
            enemy.confidence, visible, enemy.body_bbox, enemy.body_anchor, enemy.anchor_cell,
        )

    def _player_position(self, tracks: Sequence[TrackedSprite], arena_shape) -> tuple[float, float]:
        player = next((t for t in tracks if t.classification is SpriteClass.PLAYER and t.track_state is not TrackState.LOST and t.has_body_lock), None)
        if player is not None and player.body_anchor is not None:
            return player.body_anchor
        h, w = int(arena_shape[0]), int(arena_shape[1])
        return w*self.config.player_anchor_x_ratio, h*self.config.player_anchor_y_ratio

    def plan(self, tracks: Sequence[TrackedSprite], *, arena_shape, scene_changed=False, local_state=LocalPerceptionState.NORMAL):
        del scene_changed
        self._plan_frame += 1
        by_id = {t.track_id: t for t in tracks}
        player_position = self._player_position(tracks, arena_shape)
        if self.latched_enemy_track_id is not None:
            latched = by_id.get(self.latched_enemy_track_id)
            if latched is None or latched.track_state is TrackState.LOST or not latched.has_body_lock:
                self.latched_enemy_track_id = None
        if self.latched_enemy_track_id is None:
            enemy = next((t for t in tracks if t.classification is SpriteClass.ENEMY and t.known_enemy and t.track_state is TrackState.TRACKED and t.has_body_lock and t.body_confidence >= self.config.body_lock_min_confidence and t.rejection_reason is None), None)
            if enemy is not None:
                self.latched_enemy_track_id = enemy.track_id
        if self.latched_enemy_track_id is None:
            if local_state is LocalPerceptionState.LOCAL_VISUAL_OCCLUSION:
                self.invalidate_facing("local_visual_occlusion")
                return None, CombatAction.NONE, RoundState.LOCAL_VISUAL_OCCLUSION, "local visual occlusion; no enemy body action"
            state = RoundState.LOCAL_UNKNOWN_BACKGROUND if local_state is LocalPerceptionState.LOCAL_UNKNOWN_BACKGROUND else RoundState.SEARCHING
            return None, CombatAction.NONE, state, "no enemy body lock confirmed inside local ROI"
        enemy = by_id.get(self.latched_enemy_track_id)
        if enemy is None or not enemy.has_body_lock or enemy.body_confidence < self.config.body_lock_min_confidence:
            self.latched_enemy_track_id = None
            return None, CombatAction.NONE, RoundState.SEARCHING, "candidate rejected: local body lock invalid"
        assert enemy.body_anchor is not None and enemy.anchor_cell is not None
        direction = self._direction(player_position, enemy.body_anchor)
        distance = self._distance_cells(enemy.anchor_cell)
        if local_state is LocalPerceptionState.LOCAL_VISUAL_OCCLUSION:
            self.invalidate_facing("local_visual_occlusion")
            return self._target(enemy, visible=False, direction=None, distance=None), CombatAction.NONE, RoundState.LOCAL_VISUAL_OCCLUSION, "local visual occlusion; target identity retained and H blocked"
        if enemy.track_state is TrackState.TEMPORARILY_MISSING:
            return self._target(enemy, visible=False, direction=None, distance=None), CombatAction.NONE, RoundState.TARGET_TEMPORARILY_MISSING, "enemy body ID retained inside local ROI; H blocked"
        target = self._target(enemy, visible=True, direction=direction, distance=distance)
        if distance <= self.config.attack_distance_cells:
            expected = direction or self.facing
            if expected is None:
                self.invalidate_facing("overlap_without_known_facing")
                return target, CombatAction.NONE, RoundState.TRACKING, "enemy overlaps player but facing is unknown; H blocked"
            if self.facing != expected:
                self._record_direction(expected, correction=True)
                return target, CombatAction[f"TURN_{expected}"], RoundState.TRACKING, "facing correction required before H"
            if not self.facing_confirmed:
                self._record_direction(expected)
                return target, CombatAction.NONE, RoundState.TRACKING, "facing correction observed; confirming before H"
            if self._plan_frame-self._last_correction_frame <= self.config.facing_correction_cooldown_frames:
                return target, CombatAction.NONE, RoundState.TRACKING, "facing corrected; waiting confirmation cooldown before H"
            return target, CombatAction.ATTACK, RoundState.ATTACKING, "enemy body lock in range with confirmed facing"
        if direction is None:
            return target, CombatAction.NONE, RoundState.TRACKING, "enemy body anchor overlaps player anchor"
        self._record_direction(direction)
        return target, CombatAction[f"CHASE_{direction}"], RoundState.PURSUING, "enemy body lock outside attack distance inside local ROI"


class SceneChangeRebaseliner:
    """Deprecated no-op compatibility shim; PR27.6 never globally rebaselines."""
    active = False
    def __init__(self, config: PR27Config) -> None: self.config = config.normalized()
    def start(self, *_args, **_kwargs) -> None: return None
    def observe(self, *_args, **_kwargs) -> bool: return False
