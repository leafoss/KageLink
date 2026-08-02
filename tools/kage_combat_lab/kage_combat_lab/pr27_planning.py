from __future__ import annotations

from collections import defaultdict, deque
from typing import Sequence

import numpy as np

from .pr27_cells import CellBaselineStore
from .pr27_model import (
    CELL_SIZE_PX, CombatAction, CombatTarget, GridCell, PR27Config,
    RoundState, SpriteClass, TrackState, TrackedSprite,
)


class CombatPlanner:
    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.latched_enemy_track_id: int | None = None

    @staticmethod
    def _direction(player: tuple[float, float], target: tuple[float, float]) -> str | None:
        dx, dy = target[0] - player[0], target[1] - player[1]
        if max(abs(dx), abs(dy)) < 4.0:
            return None
        if abs(dx) >= abs(dy):
            return "RIGHT" if dx > 0 else "LEFT"
        return "DOWN" if dy > 0 else "UP"

    @staticmethod
    def _distance_cells(player: tuple[float, float], target: tuple[float, float]) -> int:
        return int(max(abs(target[0] - player[0]), abs(target[1] - player[1])) // CELL_SIZE_PX)

    def plan(
        self,
        tracks: Sequence[TrackedSprite],
        *,
        arena_shape: Sequence[int],
        scene_changed: bool,
    ) -> tuple[CombatTarget | None, CombatAction, RoundState, str]:
        if scene_changed:
            return None, CombatAction.NONE, RoundState.SCENE_CHANGED, "global cell change; combat suspended"

        by_id = {track.track_id: track for track in tracks}
        player = next(
            (
                track
                for track in tracks
                if track.classification is SpriteClass.PLAYER and track.track_state is not TrackState.LOST
            ),
            None,
        )
        if player is None:
            arena_h, arena_w = int(arena_shape[0]), int(arena_shape[1])
            player_position = (
                arena_w * self.config.player_anchor_x_ratio,
                arena_h * self.config.player_anchor_y_ratio,
            )
        else:
            player_position = player.center

        if self.latched_enemy_track_id is not None:
            latched = by_id.get(self.latched_enemy_track_id)
            if latched is None or latched.track_state is TrackState.LOST:
                self.latched_enemy_track_id = None

        if self.latched_enemy_track_id is None:
            enemy = next(
                (
                    track
                    for track in tracks
                    if track.classification is SpriteClass.ENEMY
                    and track.known_enemy
                    and track.track_state is TrackState.TRACKED
                ),
                None,
            )
            if enemy is not None:
                self.latched_enemy_track_id = enemy.track_id

        if self.latched_enemy_track_id is None:
            return None, CombatAction.NONE, RoundState.SEARCHING, "no visually confirmed enemy ID"

        enemy = by_id[self.latched_enemy_track_id]
        if enemy.track_state is TrackState.TEMPORARILY_MISSING:
            target = CombatTarget(
                track_id=enemy.track_id,
                cells=enemy.current_cells,
                position=enemy.center,
                direction=None,
                distance_cells=None,
                confidence=enemy.confidence,
                visible=False,
            )
            return (
                target,
                CombatAction.NONE,
                RoundState.TARGET_TEMPORARILY_MISSING,
                "enemy ID retained; no blind movement or attack",
            )

        direction = self._direction(player_position, enemy.center)
        distance = self._distance_cells(player_position, enemy.center)
        target = CombatTarget(
            track_id=enemy.track_id,
            cells=enemy.current_cells,
            position=enemy.center,
            direction=direction,
            distance_cells=distance,
            confidence=enemy.confidence,
            visible=True,
        )
        if distance <= self.config.attack_distance_cells:
            return target, CombatAction.ATTACK, RoundState.ATTACKING, "confirmed enemy within attack distance"
        if direction is None:
            return target, CombatAction.NONE, RoundState.TRACKING, "confirmed enemy overlaps player anchor"
        action = CombatAction[f"CHASE_{direction}"]
        return target, action, RoundState.PURSUING, "confirmed enemy outside attack distance"


class SceneChangeRebaseliner:
    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.active = False
        self.samples: dict[tuple[int, int], deque[np.ndarray]] = defaultdict(
            lambda: deque(maxlen=self.config.scene_stable_frames)
        )
        self.previous: dict[tuple[int, int], np.ndarray] = {}

    def start(self, baselines: CellBaselineStore) -> None:
        if self.active:
            return
        self.active = True
        self.samples.clear()
        self.previous.clear()
        baselines.invalidate_all()

    def observe(
        self,
        arena_bgr: np.ndarray,
        cells: Sequence[GridCell],
        baselines: CellBaselineStore,
    ) -> bool:
        if not self.active:
            return False
        for cell in cells:
            key = (cell.row, cell.column)
            crop = arena_bgr[cell.y : cell.y + cell.height, cell.x : cell.x + cell.width].copy()
            old = self.previous.get(key)
            self.previous[key] = crop
            if old is None:
                continue
            temporal = float(np.mean(np.abs(crop.astype(np.int16) - old.astype(np.int16)))) / 255.0
            if temporal <= 0.010:
                self.samples[key].append(crop)
            else:
                self.samples[key].clear()
        ready = [
            cell
            for cell in cells
            if len(self.samples[(cell.row, cell.column)]) >= self.config.scene_stable_frames
        ]
        if len(ready) < max(1, int(len(cells) * 0.80)):
            return False
        for cell in ready:
            stack = np.stack(tuple(self.samples[(cell.row, cell.column)]))
            baselines.set(cell, np.median(stack, axis=0).astype(np.uint8))
        self.active = False
        return True
