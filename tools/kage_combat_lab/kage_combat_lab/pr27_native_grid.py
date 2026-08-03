from __future__ import annotations

import math
import time
from collections import Counter
from pathlib import Path
from typing import Mapping

import numpy as np

from .pr27_cells import (
    ArenaCropper, CellBaselineStore, CellDifferenceDetector,
    ChangedCellGrouper, NativeGrid64,
)
from .pr27_fragments import SpriteAssembler, SpriteFragmentExtractor
from .pr27_model import (
    CELL_SIZE_PX, ArenaRect, CellDifference, CellSearchGroup, CellState,
    CombatAction, CombatTarget, FragmentRole, GridCell, PR27Config, PR27FrameResult,
    RoundState, SpriteClass, SpriteFragment, SpriteObservation, TrackState,
    TrackedSprite,
)
from .pr27_planning import CombatPlanner, SceneChangeRebaseliner
from .pr27_registry import KnownSpriteRegistry
from .pr27_tracker import SpriteTracker


class PR27CombatSystem:
    def __init__(
        self,
        *,
        config: PR27Config | None = None,
        cropper: ArenaCropper | None = None,
        baselines: CellBaselineStore | None = None,
        registry: KnownSpriteRegistry | None = None,
    ) -> None:
        self.config = (config or PR27Config()).normalized()
        self.cropper = cropper or ArenaCropper()
        self.grid = NativeGrid64()
        self.baselines = baselines or CellBaselineStore()
        self.difference_detector = CellDifferenceDetector(self.config)
        self.grouper = ChangedCellGrouper()
        self.extractor = SpriteFragmentExtractor(self.config)
        self.assembler = SpriteAssembler(self.config)
        self.tracker = SpriteTracker(self.config, registry)
        self.planner = CombatPlanner(self.config)
        self.rebaseliner = SceneChangeRebaseliner(self.config)
        self.frame_index = 0
        self.visual_burst_active = False
        self.previous_changed_count = 0
        self.trainer_exclusion_bbox: tuple[int, int, int, int] | None = None

    def _configure_trainer_exclusion(
        self,
        metadata: Mapping[str, object],
        *,
        native_shape: tuple[int, int],
        arena_rect: ArenaRect,
        arena_shape: tuple[int, int],
        cells: tuple[GridCell, ...],
    ) -> None:
        center_normalized = metadata.get("trainer_center_normalized")
        center_frame: tuple[float, float] | None = None
        if isinstance(center_normalized, list) and len(center_normalized) == 2:
            center_frame = (
                float(center_normalized[0]) * max(1, native_shape[1] - 1),
                float(center_normalized[1]) * max(1, native_shape[0] - 1),
            )
        elif isinstance(metadata.get("trainer_bbox"), list) and len(metadata["trainer_bbox"]) == 4:
            raw = [float(value) for value in metadata["trainer_bbox"]]
            center_frame = (
                ((raw[0] + raw[2] / 2.0) / 960.0) * native_shape[1],
                ((raw[1] + raw[3] / 2.0) / 540.0) * native_shape[0],
            )
        if center_frame is None:
            self.trainer_exclusion_bbox = None
            self.tracker.set_trainer_exclusion(None)
            return
        center_x = center_frame[0] - arena_rect.x
        center_y = center_frame[1] - arena_rect.y
        margin = self.config.trainer_exclusion_cell_margin * CELL_SIZE_PX
        left = max(0, int(round(center_x - CELL_SIZE_PX / 2.0 - margin)))
        top = max(0, int(round(center_y - CELL_SIZE_PX / 2.0 - margin)))
        right = min(arena_shape[1], int(round(center_x + CELL_SIZE_PX / 2.0 + margin)))
        bottom = min(arena_shape[0], int(round(center_y + CELL_SIZE_PX / 2.0 + margin)))
        if right <= left or bottom <= top:
            self.trainer_exclusion_bbox = None
            self.tracker.set_trainer_exclusion(None)
            return
        self.trainer_exclusion_bbox = (left, top, right - left, bottom - top)
        forbidden = [
            (cell.row, cell.column)
            for cell in cells
            if not (
                cell.x + cell.width <= left
                or right <= cell.x
                or cell.y + cell.height <= top
                or bottom <= cell.y
            )
        ]
        self.tracker.set_trainer_exclusion(self.trainer_exclusion_bbox, forbidden)

    def load_baseline(self, path: Path, native_frame_bgr: np.ndarray) -> int:
        rect, arena = self.cropper.crop(native_frame_bgr)
        metadata = CellBaselineStore.read_metadata(path)
        self.grid.set_phase(int(metadata.get("grid_phase_x", 0) or 0), int(metadata.get("grid_phase_y", 0) or 0))
        self.planner.set_grid_phase(self.grid.phase)
        cells = self.grid.build(arena.shape)
        loaded = self.baselines.load_npz(path, cells)
        self._configure_trainer_exclusion(
            metadata,
            native_shape=native_frame_bgr.shape[:2],
            arena_rect=rect,
            arena_shape=arena.shape[:2],
            cells=cells,
        )
        return loaded

    def _focused_differences(self, differences: Mapping[tuple[int, int], CellDifference]) -> Mapping[tuple[int, int], CellDifference]:
        target_id = self.tracker.enemy_track_id
        if target_id is None:
            return differences
        target = self.tracker.tracks.get(target_id)
        if target is None or target.anchor_cell is None:
            return differences
        radius = self.config.target_focus_radius_cells
        row, column = target.anchor_cell
        focus_keys = {(row + dr, column + dc) for dr in range(-radius, radius + 1) for dc in range(-radius, radius + 1)}
        focused = {key: value for key, value in differences.items() if key in focus_keys}
        if target.track_state is TrackState.TRACKED:
            return focused
        if self.frame_index % self.config.global_reacquire_interval_frames == 0:
            return differences
        return focused

    def _result(
        self,
        *,
        now: float,
        rect: ArenaRect,
        arena: np.ndarray,
        cells: tuple[GridCell, ...],
        differences: Mapping[tuple[int, int], CellDifference],
        groups: tuple[CellSearchGroup, ...] = (),
        fragments: tuple[SpriteFragment, ...] = (),
        observations: tuple[SpriteObservation, ...] = (),
        tracks: tuple[TrackedSprite, ...] | None = None,
        target: CombatTarget | None = None,
        action: CombatAction = CombatAction.NONE,
        state: RoundState = RoundState.SEARCHING,
        scene_changed: bool = False,
        reason: str,
    ) -> PR27FrameResult:
        rejections = Counter(self.extractor.last_rejections)
        rejections.update(self.assembler.last_rejections)
        result = PR27FrameResult(
            frame_index=self.frame_index,
            timestamp=now,
            arena_rect=rect,
            arena_bgr=arena,
            cells=cells,
            differences=differences,
            groups=groups,
            fragments=fragments,
            observations=observations,
            tracks=tracks if tracks is not None else tuple(sorted(self.tracker.tracks.values(), key=lambda item: item.track_id)),
            player_track_id=self.tracker.player_track_id,
            target=target,
            action=action,
            state=state,
            scene_changed=scene_changed,
            reason=reason,
            grid_phase=self.grid.phase,
            fragment_rejections=dict(rejections),
            candidate_rejections=tuple(self.tracker.last_candidate_rejections),
        )
        self.frame_index += 1
        return result

    def process(self, native_frame_bgr: np.ndarray, *, timestamp: float | None = None) -> PR27FrameResult:
        now = time.monotonic() if timestamp is None else float(timestamp)
        rect, arena = self.cropper.crop(native_frame_bgr)
        cells = self.grid.build(arena.shape)
        if len(self.baselines) == 0:
            raise RuntimeError("PR27_BASELINE_NOT_LOADED")
        if self.rebaseliner.active:
            rebuilt = self.rebaseliner.observe(arena, cells, self.baselines)
            return self._result(
                now=now, rect=rect, arena=arena, cells=cells, differences={},
                state=RoundState.SEARCHING if rebuilt else RoundState.SCENE_CHANGED,
                scene_changed=not rebuilt,
                reason="native phased-cell baselines rebuilt" if rebuilt else "waiting for stable phased cells after scene change",
            )
        differences = self.difference_detector.compare(arena, cells, self.baselines)
        changed_count = sum(item.state is CellState.CHANGED for item in differences.values())
        changed_limit = max(self.config.scene_changed_min_cells, int(math.ceil(len(cells) * self.config.scene_changed_cell_ratio)))
        if changed_count >= changed_limit:
            self.visual_burst_active = False
            self.previous_changed_count = changed_count
            self.rebaseliner.start(self.baselines)
            target, action, state, reason = self.planner.plan(tuple(self.tracker.tracks.values()), arena_shape=arena.shape, scene_changed=True)
            return self._result(
                now=now, rect=rect, arena=arena, cells=cells, differences=differences,
                target=target, action=action, state=state, scene_changed=True, reason=reason,
            )
        burst_enter = max(72, int(math.ceil(len(cells) * 0.25)))
        burst_clear = max(48, int(math.ceil(len(cells) * 0.18)))
        burst_spike = changed_count >= max(burst_enter, int(math.ceil(max(1, self.previous_changed_count) * 1.45)))
        if self.visual_burst_active:
            if changed_count > burst_clear:
                self.previous_changed_count = changed_count
                return self._result(
                    now=now, rect=rect, arena=arena, cells=cells, differences=differences,
                    state=RoundState.TRACKING,
                    reason=f"visual effect burst ({changed_count} cells); body identity and actions suspended",
                )
            self.visual_burst_active = False
        elif burst_spike:
            self.visual_burst_active = True
            self.previous_changed_count = changed_count
            return self._result(
                now=now, rect=rect, arena=arena, cells=cells, differences=differences,
                state=RoundState.TRACKING,
                reason=f"visual effect burst ({changed_count} cells); body identity and actions suspended",
            )
        self.previous_changed_count = changed_count
        search_differences = self._focused_differences(differences)
        groups = self.grouper.group(search_differences)
        fragments = self.extractor.extract(arena, groups, search_differences)
        observations = self.assembler.assemble(arena, groups, fragments, cells=cells)
        tracks = self.tracker.update(observations, frame_index=self.frame_index, arena_shape=arena.shape)
        target, action, state, reason = self.planner.plan(tracks, arena_shape=arena.shape, scene_changed=False)
        return self._result(
            now=now, rect=rect, arena=arena, cells=cells, differences=differences,
            groups=groups, fragments=fragments, observations=observations, tracks=tracks,
            target=target, action=action, state=state, scene_changed=False, reason=reason,
        )


__all__ = [
    "CELL_SIZE_PX", "ArenaCropper", "ArenaRect", "CellBaselineStore", "CellDifference",
    "CellSearchGroup", "CellState", "CombatAction", "CombatTarget", "FragmentRole",
    "GridCell", "KnownSpriteRegistry", "NativeGrid64", "PR27CombatSystem", "PR27Config",
    "PR27FrameResult", "RoundState", "SpriteClass", "SpriteFragment", "SpriteObservation",
    "TrackState", "TrackedSprite",
]
