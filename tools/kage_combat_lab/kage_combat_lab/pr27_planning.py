from __future__ import annotations

from typing import Sequence

from .pr27_facing import opposite
from .pr27_model import (
    CombatAction,
    CombatTarget,
    LocalPerceptionState,
    PR27Config,
    RecoveryState,
    RoundState,
    SpriteClass,
    SpriteRole,
    TrackState,
    TrackedSprite,
)


class CombatPlanner:
    """Plans from immutable SELF/ENEMY roles and observed visual facing."""

    def __init__(self, config: PR27Config, *, require_visual_facing: bool = False) -> None:
        self.config = config.normalized()
        self.require_visual_facing = bool(require_visual_facing)
        self.latched_enemy_track_id: int | None = None
        self.grid_phase = (0, 0)
        self._facing_observed: str | None = None
        self.facing_confirm_frames = 0
        self.facing_invalid_reason: str | None = "startup"
        self.facing_commanded: str | None = None
        self.last_facing_correction_action: str | None = None
        self._plan_frame = 0
        self._last_correction_frame = -10_000
        self.last_separated_enemy_direction: str | None = None
        self.last_nonzero_relative_cell: tuple[int, int] | None = None
        self.recovery_state = RecoveryState.NONE
        self.h_block_reason: str | None = None
        self.recovery_action: str | None = None
        self.separation_action: str | None = None
        self.request_target_reacquire = False
        self.deadlock_counters: dict[str, int] = {
            "overlap_unknown_frames": 0,
            "close_enemy_idle_frames": 0,
            "facing_unknown_frames": 0,
            "self_enemy_conflict_frames": 0,
            "merged_body_frames": 0,
            "target_missing_close_frames": 0,
        }
        self._last_separation_frame = -10_000

    @property
    def facing(self) -> str | None:
        return self._facing_observed

    @facing.setter
    def facing(self, value: str | None) -> None:
        self._facing_observed = value

    def set_grid_phase(self, phase: tuple[int, int]) -> None:
        self.grid_phase = int(phase[0]), int(phase[1])

    def invalidate_facing(self, reason: str) -> None:
        self._facing_observed = None
        self.facing_confirm_frames = 0
        self.facing_invalid_reason = str(reason)
        self.last_facing_correction_action = None

    def update_facing_observation(self, observed: str | None, *, confirmed: bool) -> None:
        if observed is None:
            self._facing_observed = None
            self.facing_confirm_frames = 0
            return
        if self._facing_observed == observed:
            self.facing_confirm_frames += 1
        else:
            self._facing_observed = observed
            self.facing_confirm_frames = 1
        if confirmed:
            self.facing_confirm_frames = max(self.facing_confirm_frames, self.config.facing_confirm_frames)
            self.facing_invalid_reason = None

    def note_physical_actions(self, actions: Sequence[str]) -> None:
        for action in actions:
            upper = str(action).upper()
            for direction in ("LEFT", "RIGHT", "UP", "DOWN"):
                if f"_{direction}" in upper and any(prefix in upper for prefix in ("TURN_", "CHASE_", "SEPARATE_")):
                    self.facing_commanded = direction
                    return

    @property
    def facing_confirmed(self) -> bool:
        return self._facing_observed is not None and self.facing_confirm_frames >= self.config.facing_confirm_frames

    def _direction(self, player: tuple[float, float], target: tuple[float, float]) -> str | None:
        dx, dy = target[0] - player[0], target[1] - player[1]
        threshold = self.config.subcell_direction_threshold_px
        if max(abs(dx), abs(dy)) < threshold:
            return None
        if abs(dx) >= abs(dy):
            return "RIGHT" if dx > 0 else "LEFT"
        return "DOWN" if dy > 0 else "UP"

    @staticmethod
    def _distance_cells(relative_cell: tuple[int, int]) -> int:
        return max(abs(relative_cell[0]), abs(relative_cell[1]))

    def _record_direction_legacy(self, direction: str | None, *, correction: bool = False) -> None:
        if direction is None:
            return
        if self._facing_observed == direction:
            self.facing_confirm_frames += 1
        else:
            self._facing_observed, self.facing_confirm_frames = direction, 1
        if correction:
            self._last_correction_frame = self._plan_frame
            self.last_facing_correction_action = f"TURN_{direction}"
        else:
            self.last_facing_correction_action = None
        if self.facing_confirmed:
            self.facing_invalid_reason = None

    def _target(
        self,
        enemy: TrackedSprite,
        *,
        visible: bool,
        direction: str | None,
        distance: int | None,
        relative_anchor: tuple[float, float] | None,
    ) -> CombatTarget:
        assert enemy.body_anchor is not None
        return CombatTarget(
            enemy.track_id,
            enemy.current_cells,
            enemy.body_anchor,
            direction,
            distance,
            enemy.confidence,
            visible,
            enemy.body_bbox,
            enemy.body_anchor,
            enemy.anchor_cell,
            relative_anchor,
        )

    @staticmethod
    def _player_track(tracks: Sequence[TrackedSprite]) -> TrackedSprite | None:
        return next(
            (
                track
                for track in tracks
                if track.effective_role is SpriteRole.SELF
                and track.track_state is not TrackState.LOST
                and track.has_body_lock
            ),
            None,
        )

    def _player_position(self, tracks: Sequence[TrackedSprite], arena_shape) -> tuple[float, float]:
        player = self._player_track(tracks)
        if player is not None and player.body_anchor is not None:
            return player.body_anchor
        height, width = int(arena_shape[0]), int(arena_shape[1])
        return width * self.config.player_anchor_x_ratio, height * self.config.player_anchor_y_ratio

    @staticmethod
    def _enemy_track(tracks: Sequence[TrackedSprite], track_id: int | None) -> TrackedSprite | None:
        if track_id is None:
            return None
        return next((track for track in tracks if track.track_id == track_id), None)

    @staticmethod
    def _is_enemy(track: TrackedSprite) -> bool:
        return track.effective_role is SpriteRole.ENEMY or (
            track.classification is SpriteClass.ENEMY and track.known_enemy
        )

    def _reset_frame_flags(self) -> None:
        self.recovery_state = RecoveryState.NONE
        self.h_block_reason = None
        self.recovery_action = None
        self.separation_action = None
        self.request_target_reacquire = False

    def _turn_action(self, direction: str) -> CombatAction:
        self.facing_commanded = direction
        self.last_facing_correction_action = f"TURN_{direction}"
        self._last_correction_frame = self._plan_frame
        return CombatAction[f"TURN_{direction}"]

    def _separation_action(self, enemy_direction: str | None) -> CombatAction | None:
        if self._plan_frame - self._last_separation_frame < self.config.separation_cooldown_frames:
            return None
        direction = opposite(enemy_direction or self.last_separated_enemy_direction)
        if direction is None:
            direction = "LEFT" if self._plan_frame % 2 == 0 else "RIGHT"
        self._last_separation_frame = self._plan_frame
        self.facing_commanded = direction
        self.separation_action = f"SEPARATE_{direction}"
        self.recovery_action = self.separation_action
        return CombatAction[f"SEPARATE_{direction}"]

    def _legacy_attack_plan(
        self,
        target: CombatTarget,
        *,
        expected: str | None,
    ):
        if expected is None:
            self.invalidate_facing("overlap_without_known_facing")
            return target, CombatAction.NONE, RoundState.TRACKING, "enemy overlaps player but facing is unknown; H blocked"
        if self._facing_observed != expected:
            self._record_direction_legacy(expected, correction=True)
            return target, CombatAction[f"TURN_{expected}"], RoundState.TRACKING, "facing correction required before H"
        if not self.facing_confirmed:
            self._record_direction_legacy(expected)
            return target, CombatAction.NONE, RoundState.TRACKING, "facing correction observed; confirming before H"
        if self._plan_frame - self._last_correction_frame <= self.config.facing_correction_cooldown_frames:
            return target, CombatAction.NONE, RoundState.TRACKING, "facing corrected; waiting confirmation cooldown before H"
        return target, CombatAction.ATTACK, RoundState.ATTACKING, "enemy body lock in range with confirmed facing"

    def plan(
        self,
        tracks: Sequence[TrackedSprite],
        *,
        arena_shape,
        scene_changed: bool = False,
        local_state: LocalPerceptionState = LocalPerceptionState.NORMAL,
        merged_body: bool = False,
        hit_event: bool = False,
        close_candidate_count: int = 0,
        role_conflict: bool = False,
    ):
        del scene_changed
        self._plan_frame += 1
        self._reset_frame_flags()
        by_id = {track.track_id: track for track in tracks}
        player_position = self._player_position(tracks, arena_shape)

        if role_conflict:
            self.deadlock_counters["self_enemy_conflict_frames"] += 1
            self.recovery_state = RecoveryState.CLOSE_REACQUIRE
            self.h_block_reason = "ROLE_CONFLICT"
            self.request_target_reacquire = self.deadlock_counters["self_enemy_conflict_frames"] >= self.config.close_idle_soft_frames
            return None, CombatAction.NONE, RoundState.CLOSE_REACQUIRE, "ROLE_CONFLICT; SELF preserved; H blocked; close reacquire requested"
        self.deadlock_counters["self_enemy_conflict_frames"] = 0

        if hit_event:
            self.invalidate_facing("hit_event")
            self.recovery_state = RecoveryState.HIT_RECOVERY
            self.h_block_reason = "HIT_RECOVERY"

        if self.latched_enemy_track_id is not None:
            latched = by_id.get(self.latched_enemy_track_id)
            if latched is None or latched.track_state is TrackState.LOST or not latched.has_body_lock or not self._is_enemy(latched):
                self.latched_enemy_track_id = None
        if self.latched_enemy_track_id is None:
            enemy = next(
                (
                    track
                    for track in tracks
                    if self._is_enemy(track)
                    and track.track_state is TrackState.TRACKED
                    and track.has_body_lock
                    and track.body_confidence >= self.config.body_lock_min_confidence
                    and track.rejection_reason is None
                    and track.role_conflict_reason is None
                ),
                None,
            )
            if enemy is not None:
                self.latched_enemy_track_id = enemy.track_id

        if self.latched_enemy_track_id is None:
            if local_state is LocalPerceptionState.LOCAL_VISUAL_OCCLUSION:
                self.invalidate_facing("local_visual_occlusion")
                self.h_block_reason = "LOCAL_VISUAL_OCCLUSION"
                return None, CombatAction.NONE, RoundState.LOCAL_VISUAL_OCCLUSION, "local visual occlusion; no enemy body action"
            if close_candidate_count > 0:
                self.deadlock_counters["close_enemy_idle_frames"] += 1
                self.recovery_state = RecoveryState.CLOSE_TARGET_SEARCH
                self.h_block_reason = "VISIBLE_CLOSE_CANDIDATE_NOT_LOCKED"
                self.request_target_reacquire = self.deadlock_counters["close_enemy_idle_frames"] >= self.config.close_idle_soft_frames
                return None, CombatAction.NONE, RoundState.CLOSE_TARGET_SEARCH, "visible non-SELF body is close; bounded local target search"
            self.deadlock_counters["close_enemy_idle_frames"] = 0
            state = RoundState.LOCAL_UNKNOWN_BACKGROUND if local_state is LocalPerceptionState.LOCAL_UNKNOWN_BACKGROUND else RoundState.SEARCHING
            return None, CombatAction.NONE, state, "no enemy body lock confirmed inside local ROI"

        enemy = by_id.get(self.latched_enemy_track_id)
        if enemy is None or not enemy.has_body_lock or enemy.body_confidence < self.config.body_lock_min_confidence:
            self.latched_enemy_track_id = None
            self.h_block_reason = "ENEMY_BODY_LOCK_INVALID"
            return None, CombatAction.NONE, RoundState.SEARCHING, "candidate rejected: local body lock invalid"

        assert enemy.body_anchor is not None and enemy.anchor_cell is not None
        relative_anchor = (
            enemy.body_anchor[0] - player_position[0],
            enemy.body_anchor[1] - player_position[1],
        )
        direction = self._direction(player_position, enemy.body_anchor)
        distance = self._distance_cells(enemy.anchor_cell)

        if local_state is LocalPerceptionState.LOCAL_VISUAL_OCCLUSION:
            self.invalidate_facing("local_visual_occlusion")
            self.h_block_reason = "LOCAL_VISUAL_OCCLUSION"
            return self._target(enemy, visible=False, direction=None, distance=None, relative_anchor=relative_anchor), CombatAction.NONE, RoundState.LOCAL_VISUAL_OCCLUSION, "local visual occlusion; target identity retained and H blocked"

        if merged_body:
            self.deadlock_counters["merged_body_frames"] += 1
            self.recovery_state = RecoveryState.MERGED_BODY_RECOVERY
            self.h_block_reason = "MERGED_BODY"
            target = self._target(enemy, visible=False, direction=direction, distance=distance, relative_anchor=relative_anchor)
            if self.deadlock_counters["merged_body_frames"] >= self.config.close_idle_turn_frames:
                action = self._separation_action(direction)
                if action is not None:
                    self.recovery_state = RecoveryState.SEPARATION_RECOVERY
                    return target, action, RoundState.SEPARATION_RECOVERY, "MERGED_BODY persisted; bounded separation pulse; H blocked"
            return target, CombatAction.NONE, RoundState.MERGED_BODY_RECOVERY, "MERGED_BODY; SELF and ENEMY identities preserved; H blocked"
        self.deadlock_counters["merged_body_frames"] = 0

        if enemy.track_state is TrackState.TEMPORARILY_MISSING:
            self.h_block_reason = "TARGET_TEMPORARILY_MISSING"
            if close_candidate_count > 0:
                self.deadlock_counters["target_missing_close_frames"] += 1
                self.recovery_state = RecoveryState.CLOSE_REACQUIRE
                self.request_target_reacquire = self.deadlock_counters["target_missing_close_frames"] >= self.config.close_reacquire_confirm_frames
                return self._target(enemy, visible=False, direction=None, distance=None, relative_anchor=relative_anchor), CombatAction.NONE, RoundState.CLOSE_REACQUIRE, "old target missing while close candidate is visible; local rebind evaluation"
            self.deadlock_counters["target_missing_close_frames"] = 0
            return self._target(enemy, visible=False, direction=None, distance=None, relative_anchor=relative_anchor), CombatAction.NONE, RoundState.TARGET_TEMPORARILY_MISSING, "enemy body ID retained inside local ROI; H blocked"
        self.deadlock_counters["target_missing_close_frames"] = 0

        target = self._target(enemy, visible=True, direction=direction, distance=distance, relative_anchor=relative_anchor)
        if direction is not None:
            self.last_separated_enemy_direction = direction
            if enemy.anchor_cell != (0, 0):
                self.last_nonzero_relative_cell = enemy.anchor_cell

        if distance <= self.config.attack_distance_cells:
            if not self.require_visual_facing:
                return self._legacy_attack_plan(target, expected=direction or self._facing_observed)

            if direction is None:
                self.deadlock_counters["overlap_unknown_frames"] += 1
                self.deadlock_counters["close_enemy_idle_frames"] += 1
                self.recovery_state = RecoveryState.CLOSE_FACING_RECOVERY
                self.h_block_reason = "OVERLAP_WITHOUT_SUBCELL_DIRECTION"
                count = self.deadlock_counters["overlap_unknown_frames"]
                if count >= self.config.close_idle_drop_frames:
                    self.request_target_reacquire = True
                    return target, CombatAction.NONE, RoundState.CLOSE_REACQUIRE, "overlap watchdog reached; toxic target association scheduled for local rebind"
                if count >= self.config.close_idle_turn_frames:
                    action = self._separation_action(self.last_separated_enemy_direction)
                    if action is not None:
                        self.recovery_state = RecoveryState.SEPARATION_RECOVERY
                        return target, action, RoundState.SEPARATION_RECOVERY, "same-cell anchors remain coincident; bounded separation pulse"
                if count >= self.config.close_idle_soft_frames and self.last_separated_enemy_direction is not None:
                    action = self._turn_action(self.last_separated_enemy_direction)
                    self.recovery_action = action.value
                    return target, action, RoundState.CLOSE_FACING_RECOVERY, "same-cell direction unknown; microturn uses last separated enemy direction"
                return target, CombatAction.NONE, RoundState.CLOSE_FACING_RECOVERY, "same-cell anchors nearly coincident; observing before bounded recovery"

            self.deadlock_counters["overlap_unknown_frames"] = 0
            expected = direction
            if self._facing_observed != expected or not self.facing_confirmed:
                self.deadlock_counters["facing_unknown_frames"] += 1
                self.deadlock_counters["close_enemy_idle_frames"] += 1
                self.recovery_state = RecoveryState.CLOSE_FACING_RECOVERY
                self.h_block_reason = "VISUAL_FACING_NOT_CONFIRMED"
                count = self.deadlock_counters["facing_unknown_frames"]
                if count >= self.config.close_idle_drop_frames:
                    self.request_target_reacquire = True
                if count == 1 or count >= self.config.close_idle_soft_frames:
                    action = self._turn_action(expected)
                    self.recovery_action = action.value
                    return target, action, RoundState.CLOSE_FACING_RECOVERY, "visual facing differs or is unknown; correction commanded but not yet confirmed"
                return target, CombatAction.NONE, RoundState.CLOSE_FACING_RECOVERY, "turn command sent; waiting for visual facing observation"

            self.deadlock_counters["facing_unknown_frames"] = 0
            self.deadlock_counters["close_enemy_idle_frames"] = 0
            if self._plan_frame - self._last_correction_frame <= self.config.facing_correction_cooldown_frames:
                self.h_block_reason = "FACING_CONFIRMATION_COOLDOWN"
                return target, CombatAction.NONE, RoundState.TRACKING, "visual facing confirmed; waiting short cooldown before H"
            return target, CombatAction.ATTACK, RoundState.ATTACKING, "enemy body lock in range with visually confirmed facing"

        self.deadlock_counters["overlap_unknown_frames"] = 0
        self.deadlock_counters["close_enemy_idle_frames"] = 0
        if direction is None:
            self.h_block_reason = "ENEMY_DIRECTION_UNKNOWN"
            return target, CombatAction.NONE, RoundState.TRACKING, "enemy body anchor direction unavailable"
        self.facing_commanded = direction
        return target, CombatAction[f"CHASE_{direction}"], RoundState.PURSUING, "enemy body lock outside attack distance inside local ROI"


class SceneChangeRebaseliner:
    """Deprecated no-op compatibility shim; PR27.7 never globally rebaselines."""

    active = False

    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()

    def start(self, *_args, **_kwargs) -> None:
        return None

    def observe(self, *_args, **_kwargs) -> bool:
        return False
