from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np

from .pr27_cells import (
    ArenaCropper, CellBaselineStore, CellDifferenceDetector,
    ChangedCellGrouper, NativeGrid64,
)
from .pr27_fragments import SpriteAssembler, SpriteFragmentExtractor
from .pr27_model import (
    CELL_SIZE_PX, ArenaRect, CellDifference, CellSearchGroup, CellState,
    CombatAction, CombatTarget, GridCell, PR27Config, PR27FrameResult,
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

    def load_baseline(self, path: Path, native_frame_bgr: np.ndarray) -> int:
        _, arena = self.cropper.crop(native_frame_bgr)
        cells = self.grid.build(arena.shape)
        return self.baselines.load_npz(path, cells)

    def process(self, native_frame_bgr: np.ndarray, *, timestamp: float | None = None) -> PR27FrameResult:
        now = time.monotonic() if timestamp is None else float(timestamp)
        rect, arena = self.cropper.crop(native_frame_bgr)
        cells = self.grid.build(arena.shape)
        if len(self.baselines) == 0:
            raise RuntimeError("PR27_BASELINE_NOT_LOADED")

        if self.rebaseliner.active:
            rebuilt = self.rebaseliner.observe(arena, cells, self.baselines)
            state = RoundState.SEARCHING if rebuilt else RoundState.SCENE_CHANGED
            result = PR27FrameResult(
                frame_index=self.frame_index,
                timestamp=now,
                arena_rect=rect,
                arena_bgr=arena,
                cells=cells,
                differences={},
                groups=(),
                fragments=(),
                observations=(),
                tracks=tuple(self.tracker.tracks.values()),
                player_track_id=self.tracker.player_track_id,
                target=None,
                action=CombatAction.NONE,
                state=state,
                scene_changed=not rebuilt,
                reason="native per-cell baselines rebuilt" if rebuilt else "waiting for stable cells after scene change",
            )
            self.frame_index += 1
            return result

        differences = self.difference_detector.compare(arena, cells, self.baselines)
        changed_count = sum(item.state is CellState.CHANGED for item in differences.values())
        changed_limit = max(
            self.config.scene_changed_min_cells,
            int(math.ceil(len(cells) * self.config.scene_changed_cell_ratio)),
        )
        scene_changed = changed_count >= changed_limit
        if scene_changed:
            self.rebaseliner.start(self.baselines)
            target, action, state, reason = self.planner.plan(
                tuple(self.tracker.tracks.values()),
                arena_shape=arena.shape,
                scene_changed=True,
            )
            result = PR27FrameResult(
                frame_index=self.frame_index,
                timestamp=now,
                arena_rect=rect,
                arena_bgr=arena,
                cells=cells,
                differences=differences,
                groups=(),
                fragments=(),
                observations=(),
                tracks=tuple(self.tracker.tracks.values()),
                player_track_id=self.tracker.player_track_id,
                target=target,
                action=action,
                state=state,
                scene_changed=True,
                reason=reason,
            )
            self.frame_index += 1
            return result

        groups = self.grouper.group(differences)
        fragments = self.extractor.extract(arena, groups, differences)
        observations = self.assembler.assemble(arena, groups, fragments)
        tracks = self.tracker.update(observations, frame_index=self.frame_index, arena_shape=arena.shape)
        target, action, state, reason = self.planner.plan(
            tracks,
            arena_shape=arena.shape,
            scene_changed=False,
        )
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
            tracks=tracks,
            player_track_id=self.tracker.player_track_id,
            target=target,
            action=action,
            state=state,
            scene_changed=False,
            reason=reason,
        )
        self.frame_index += 1
        return result


__all__ = [
    "CELL_SIZE_PX",
    "ArenaCropper",
    "ArenaRect",
    "CellBaselineStore",
    "CellDifference",
    "CellSearchGroup",
    "CellState",
    "CombatAction",
    "CombatTarget",
    "GridCell",
    "KnownSpriteRegistry",
    "NativeGrid64",
    "PR27CombatSystem",
    "PR27Config",
    "PR27FrameResult",
    "RoundState",
    "SpriteClass",
    "SpriteFragment",
    "SpriteObservation",
    "TrackState",
    "TrackedSprite",
]
