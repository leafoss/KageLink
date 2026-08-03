from __future__ import annotations

import math
import time
from collections import Counter, deque
from pathlib import Path
from typing import Mapping

import numpy as np

from .pr27_cells import (
    ArenaCropper, CellBaselineStore, CellDifferenceDetector, ChangedCellGrouper,
    LocalBackgroundModel, NativeGrid64, PlayerCentricCombatGrid,
)
from .pr27_fragments import SpriteAssembler, SpriteFragmentExtractor
from .pr27_model import (
    CELL_SIZE_PX, ArenaRect, CellDifference, CellSearchGroup, CellState,
    CombatAction, CombatTarget, FragmentRole, GridCell, LocalBackgroundState,
    LocalPerceptionState, PR27Config, PR27FrameResult, RoundState, SpriteClass,
    SpriteFragment, SpriteObservation, TrackState, TrackedSprite,
)
from .pr27_planning import CombatPlanner
from .pr27_registry import KnownSpriteRegistry
from .pr27_tracker import SpriteTracker


class PR27CombatSystem:
    """PR27.6 local player-centric combat perception."""

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
        self.combat_grid = PlayerCentricCombatGrid(self.config)
        self.baselines = baselines or CellBaselineStore()
        self.local_background = LocalBackgroundModel(self.config)
        self.difference_detector = CellDifferenceDetector(self.config)
        self.grouper = ChangedCellGrouper()
        self.extractor = SpriteFragmentExtractor(self.config)
        self.assembler = SpriteAssembler(self.config)
        self.tracker = SpriteTracker(self.config, registry)
        self.planner = CombatPlanner(self.config)
        self.frame_index = 0
        self.visual_burst_active = False
        self.local_occlusion_active = False
        self.local_occlusion_clear_count = 0
        self.local_occlusion_frames = 0
        self.previous_changed_count = 0
        self.trainer_exclusion_bbox: tuple[int, int, int, int] | None = None
        self.reference_arena: np.ndarray | None = None
        self.reference_valid: np.ndarray | None = None
        self.previous_player_anchor: tuple[float, float] | None = None
        self.player_calibration_samples: deque[tuple[tuple[int,int,int,int], tuple[float,float]]] = deque(maxlen=7)

    @staticmethod
    def _bbox_intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (ax+aw <= bx or bx+bw <= ax or ay+ah <= by or by+bh <= ay)

    def _configure_trainer_exclusion(
        self,
        metadata: Mapping[str, object],
        *,
        native_shape: tuple[int, int],
        arena_rect: ArenaRect,
        arena_shape: tuple[int, int],
    ) -> None:
        center_normalized = metadata.get("trainer_center_normalized")
        center_frame: tuple[float, float] | None = None
        if isinstance(center_normalized, list) and len(center_normalized) == 2:
            source_h, source_w = native_shape
            output_w, output_h = 960.0, 540.0
            scale = min(output_w/max(1.0,source_w), output_h/max(1.0,source_h))
            rendered_w, rendered_h = source_w*scale, source_h*scale
            offset_x = (output_w-rendered_w)/2.0
            offset_y = (output_h-rendered_h)/2.0
            output_x = float(center_normalized[0])*(output_w-1.0)
            output_y = float(center_normalized[1])*(output_h-1.0)
            center_frame = (
                min(source_w-1.0, max(0.0, (output_x-offset_x)/scale)),
                min(source_h-1.0, max(0.0, (output_y-offset_y)/scale)),
            )
        elif isinstance(metadata.get("trainer_bbox"), list) and len(metadata["trainer_bbox"]) == 4:
            raw = [float(value) for value in metadata["trainer_bbox"]]
            center_frame = (
                ((raw[0]+raw[2]/2.0)/960.0)*native_shape[1],
                ((raw[1]+raw[3]/2.0)/540.0)*native_shape[0],
            )
        if center_frame is None:
            self.trainer_exclusion_bbox = None
            self.tracker.set_trainer_exclusion(None)
            return
        center_x = center_frame[0]-arena_rect.x
        center_y = center_frame[1]-arena_rect.y
        margin = self.config.trainer_exclusion_cell_margin*CELL_SIZE_PX
        left = max(0, int(round(center_x-CELL_SIZE_PX/2.0-margin)))
        top = max(0, int(round(center_y-CELL_SIZE_PX/2.0-margin)))
        right = min(arena_shape[1], int(round(center_x+CELL_SIZE_PX/2.0+margin)))
        bottom = min(arena_shape[0], int(round(center_y+CELL_SIZE_PX/2.0+margin)))
        self.trainer_exclusion_bbox = None if right <= left or bottom <= top else (left,top,right-left,bottom-top)
        self.tracker.set_trainer_exclusion(self.trainer_exclusion_bbox)

    def _update_trainer_relative_cells(self, cells: tuple[GridCell, ...]) -> None:
        if self.trainer_exclusion_bbox is None:
            self.tracker.set_trainer_exclusion(None)
            return
        forbidden = [
            (cell.row,cell.column) for cell in cells
            if self._bbox_intersects(cell.bbox, self.trainer_exclusion_bbox)
        ]
        self.tracker.set_trainer_exclusion(self.trainer_exclusion_bbox, forbidden)

    def load_baseline(self, path: Path, native_frame_bgr: np.ndarray) -> int:
        rect, arena = self.cropper.crop(native_frame_bgr)
        metadata = CellBaselineStore.read_metadata(path)
        self.grid.set_phase(int(metadata.get("grid_phase_x",0) or 0), int(metadata.get("grid_phase_y",0) or 0))
        cells = self.grid.build(arena.shape)
        loaded = self.baselines.load_npz(path, cells)
        self.reference_arena, self.reference_valid = self.baselines.render_arena(arena.shape)
        self._configure_trainer_exclusion(
            metadata,
            native_shape=native_frame_bgr.shape[:2],
            arena_rect=rect,
            arena_shape=arena.shape[:2],
        )
        expected = (arena.shape[1]*self.config.player_anchor_x_ratio, arena.shape[0]*self.config.player_anchor_y_ratio)
        self.combat_grid.update_center(expected)
        return loaded

    def _ensure_reference(self, arena: np.ndarray) -> None:
        if len(self.baselines) == 0:
            raise RuntimeError("PR27_BASELINE_NOT_LOADED")
        if self.reference_arena is None or self.reference_arena.shape != arena.shape:
            self.reference_arena, self.reference_valid = self.baselines.render_arena(arena.shape)
        assert self.reference_valid is not None

    def _player_track(self) -> TrackedSprite | None:
        if self.tracker.player_track_id is None:
            return None
        track = self.tracker.tracks.get(self.tracker.player_track_id)
        if track is None or track.track_state is TrackState.LOST or not track.has_body_lock:
            return None
        return track

    def _roi_anchor(self, arena: np.ndarray) -> tuple[float, float]:
        player = self._player_track()
        if player is not None and player.body_anchor is not None:
            return player.body_anchor
        if self.combat_grid.center_anchor is not None:
            return self.combat_grid.center_anchor
        return arena.shape[1]*self.config.player_anchor_x_ratio, arena.shape[0]*self.config.player_anchor_y_ratio

    def _focused_differences(self, differences: Mapping[tuple[int,int], CellDifference]) -> Mapping[tuple[int,int], CellDifference]:
        target_id = self.tracker.enemy_track_id
        if target_id is None:
            return differences
        target = self.tracker.tracks.get(target_id)
        if target is None or target.anchor_cell is None:
            return differences
        radius = self.config.target_focus_radius_cells
        row,column = target.anchor_cell
        focus = {
            (row+dr,column+dc)
            for dr in range(-radius,radius+1)
            for dc in range(-radius,radius+1)
            if (row+dr)*(row+dr)+(column+dc)*(column+dc) <= self.config.roi_radius_cells**2
        }
        return {key:value for key,value in differences.items() if key in focus}

    def _detect_local_occlusion(self, differences: Mapping[tuple[int,int],CellDifference]) -> tuple[bool,set[tuple[int,int]],str]:
        changed = [key for key,diff in differences.items() if diff.state is CellState.CHANGED]
        row_counts = Counter(row for row,_ in changed)
        long_row = max(row_counts.values(), default=0) >= self.config.local_occlusion_row_span_cells
        dense = len(changed) >= self.config.local_occlusion_min_changed_cells
        spike = len(changed) >= max(self.config.local_occlusion_min_changed_cells, int(max(1,self.previous_changed_count)*1.65))
        detected = dense or (long_row and len(changed) >= 5) or spike
        reason = f"local visual occlusion changed={len(changed)} max_row={max(row_counts.values(),default=0)}"
        return detected,set(changed),reason

    def _result(
        self,
        *,
        now: float,
        rect: ArenaRect,
        arena: np.ndarray,
        cells: tuple[GridCell,...],
        differences: Mapping[tuple[int,int],CellDifference],
        groups: tuple[CellSearchGroup,...]=(),
        fragments: tuple[SpriteFragment,...]=(),
        observations: tuple[SpriteObservation,...]=(),
        tracks: tuple[TrackedSprite,...]|None=None,
        target: CombatTarget|None=None,
        action: CombatAction=CombatAction.NONE,
        state: RoundState=RoundState.SEARCHING,
        reason: str,
        local_state: LocalPerceptionState=LocalPerceptionState.NORMAL,
        local_occlusion: bool=False,
        timings: Mapping[str,float]|None=None,
    ) -> PR27FrameResult:
        rejections = Counter(self.extractor.last_rejections)
        rejections.update(self.assembler.last_rejections)
        tracks_value = tracks if tracks is not None else tuple(sorted(self.tracker.tracks.values(),key=lambda item:item.track_id))
        player = next((track for track in tracks_value if track.track_id == self.tracker.player_track_id),None)
        containment = self.combat_grid.containment_ratio(
            None if player is None else player.body_bbox,
            None if player is None else player.body_anchor,
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
            tracks=tracks_value,
            player_track_id=self.tracker.player_track_id,
            target=target,
            action=action,
            state=state,
            scene_changed=False,
            reason=reason,
            grid_phase=self.combat_grid.phase,
            fragment_rejections=dict(rejections),
            candidate_rejections=tuple(self.tracker.last_candidate_rejections),
            roi_center=self.combat_grid.center_anchor,
            roi_radius_cells=self.config.roi_radius_cells,
            roi_processed_cell_count=len(cells),
            ignored_outside_roi_count=max(0,math.ceil(arena.shape[0]/64)*math.ceil(arena.shape[1]/64)-len(cells)),
            player_cell=(0,0),
            player_body_bbox=None if player is None else player.body_bbox,
            player_body_anchor=None if player is None else player.body_anchor,
            player_body_containment_ratio=containment,
            enemy_relative_cell=None if target is None else target.anchor_cell,
            local_state=local_state,
            local_background_states=dict(self.local_background.states),
            local_occlusion_detected=local_occlusion,
            facing_expected=None if target is None else target.direction,
            facing_detected=self.planner.facing,
            facing_confirmed=self.planner.facing_confirmed,
            facing_correction_action=self.planner.last_facing_correction_action,
            timings_ms=dict(timings or {}),
        )
        self.frame_index += 1
        return result

    def process(self, native_frame_bgr: np.ndarray, *, timestamp: float|None=None) -> PR27FrameResult:
        total_started = time.perf_counter()
        now = time.monotonic() if timestamp is None else float(timestamp)
        crop_started = time.perf_counter()
        rect,arena = self.cropper.crop(native_frame_bgr)
        crop_ms = (time.perf_counter()-crop_started)*1000.0
        self._ensure_reference(arena)
        localization_started = time.perf_counter()
        anchor = self._roi_anchor(arena)
        self.combat_grid.update_center(anchor)
        cells = self.combat_grid.build(arena.shape)
        localization_ms = (time.perf_counter()-localization_started)*1000.0
        self._update_trainer_relative_cells(cells)
        assert self.reference_arena is not None and self.reference_valid is not None
        self.local_background.sync_from_reference(self.reference_arena,self.reference_valid,arena,cells)

        diff_started = time.perf_counter()
        differences = self.difference_detector.compare(arena,cells,self.local_background.baselines)
        diff_ms = (time.perf_counter()-diff_started)*1000.0

        occlusion_differences = {
            key: value for key, value in differences.items()
            if self.local_background.states.get(key) is not LocalBackgroundState.LEARNING_BACKGROUND
        }
        detected,effect_cells,occlusion_reason = self._detect_local_occlusion(occlusion_differences)
        changed_count = sum(diff.state is CellState.CHANGED for diff in occlusion_differences.values())
        self.previous_changed_count = changed_count
        forced_unknown_cells: set[tuple[int,int]] = set()
        if self.local_occlusion_active:
            self.local_occlusion_frames += 1
            if not detected:
                self.local_occlusion_clear_count += 1
                if self.local_occlusion_clear_count >= self.config.local_occlusion_clear_frames:
                    self.local_occlusion_active = False
                    self.visual_burst_active = False
                    self.local_occlusion_clear_count = 0
                    self.local_occlusion_frames = 0
            else:
                self.local_occlusion_clear_count = 0
                if self.local_occlusion_frames >= self.config.local_occlusion_max_frames:
                    self.local_occlusion_active = False
                    self.visual_burst_active = False
                    forced_unknown_cells = set(effect_cells)
                    self.local_background.begin_learning(forced_unknown_cells)
                    self.local_occlusion_frames = 0
        elif detected:
            self.local_occlusion_active = True
            self.visual_burst_active = True
            self.local_occlusion_clear_count = 0
            self.local_occlusion_frames = 1
            self.planner.invalidate_facing("local_visual_occlusion")

        timings = {
            "capture_ms":0.0,
            "roi_crop_ms":crop_ms,
            "player_localization_ms":localization_ms,
            "cell_difference_ms":diff_ms,
            "fragment_ms":0.0,
            "tracking_ms":0.0,
            "planning_ms":0.0,
            "overlay_ms":0.0,
            "total_loop_ms":(time.perf_counter()-total_started)*1000.0,
        }
        if self.local_occlusion_active:
            retained_enemy_cells = {
                track.anchor_cell for track in self.tracker.tracks.values()
                if track.track_id == self.tracker.enemy_track_id and track.anchor_cell is not None
            }
            self.local_background.mark_occupancy(player_cells={(0,0)},enemy_cells=retained_enemy_cells,effect_cells=effect_cells)
            target,action,state,reason = self.planner.plan(
                tuple(self.tracker.tracks.values()),
                arena_shape=arena.shape,
                local_state=LocalPerceptionState.LOCAL_VISUAL_OCCLUSION,
            )
            return self._result(
                now=now,rect=rect,arena=arena,cells=cells,differences=differences,
                target=target,action=action,state=state,
                reason=f"{occlusion_reason}; body tracking frozen locally frame={self.local_occlusion_frames}/{self.config.local_occlusion_max_frames}",
                local_state=LocalPerceptionState.LOCAL_VISUAL_OCCLUSION,
                local_occlusion=True,timings=timings,
            )

        usable_differences = {
            key: value for key, value in differences.items()
            if self.local_background.states.get(key) is not LocalBackgroundState.LEARNING_BACKGROUND
        }
        search_differences = self._focused_differences(usable_differences)
        fragment_started = time.perf_counter()
        groups = self.grouper.group(search_differences)
        fragments = self.extractor.extract(arena,groups,search_differences)
        observations = self.assembler.assemble(arena,groups,fragments,cells=cells)
        fragment_ms = (time.perf_counter()-fragment_started)*1000.0

        tracking_started = time.perf_counter()
        tracks = self.tracker.update(observations,frame_index=self.frame_index,arena_shape=arena.shape)
        tracking_ms = (time.perf_counter()-tracking_started)*1000.0

        player = self._player_track()
        if player is not None and player.body_anchor is not None and player.body_bbox is not None:
            if self.previous_player_anchor is not None:
                displacement = max(
                    abs(player.body_anchor[0]-self.previous_player_anchor[0]),
                    abs(player.body_anchor[1]-self.previous_player_anchor[1]),
                )
                if displacement >= self.config.hit_displacement_px:
                    self.planner.invalidate_facing(f"player_displacement_{displacement:.1f}px")
            self.previous_player_anchor = player.body_anchor
            self.player_calibration_samples.append((player.body_bbox, player.body_anchor))
            if len(self.player_calibration_samples) >= 3:
                boxes = np.asarray([item[0] for item in self.player_calibration_samples], dtype=np.float32)
                anchors = np.asarray([item[1] for item in self.player_calibration_samples], dtype=np.float32)
                median_box = tuple(int(round(value)) for value in np.median(boxes, axis=0))
                median_anchor_raw = np.median(anchors, axis=0)
                median_anchor = (float(median_anchor_raw[0]), float(median_anchor_raw[1]))
                self.combat_grid.calibrate_to_body(median_box, median_anchor)

        if forced_unknown_cells:
            local_state = LocalPerceptionState.LOCAL_UNKNOWN_BACKGROUND
        else:
            local_state = (
                LocalPerceptionState.LOCAL_UNKNOWN_BACKGROUND
                if self.local_background.unknown_count > 0
                else LocalPerceptionState.NORMAL
            )
        planning_started = time.perf_counter()
        target,action,state,reason = self.planner.plan(tracks,arena_shape=arena.shape,local_state=local_state)
        planning_ms = (time.perf_counter()-planning_started)*1000.0

        protected = {(0,0)}
        player_cells = {(0,0)}
        enemy_cells = set()
        for track in tracks:
            if track.anchor_cell is None:
                continue
            protected.add(track.anchor_cell)
            if track.classification is SpriteClass.PLAYER:
                player_cells.add(track.anchor_cell)
            elif track.classification is SpriteClass.ENEMY:
                enemy_cells.add(track.anchor_cell)
        self.local_background.mark_occupancy(player_cells=player_cells,enemy_cells=enemy_cells,effect_cells=set())
        self.local_background.learn(arena,cells,differences,protected_cells=protected,effect_cells=set())

        timings.update({
            "fragment_ms":fragment_ms,
            "tracking_ms":tracking_ms,
            "planning_ms":planning_ms,
            "total_loop_ms":(time.perf_counter()-total_started)*1000.0,
        })
        return self._result(
            now=now,rect=rect,arena=arena,cells=cells,differences=differences,
            groups=groups,fragments=fragments,observations=observations,tracks=tracks,
            target=target,action=action,state=state,reason=reason,
            local_state=local_state,local_occlusion=False,timings=timings,
        )


__all__ = [
    "CELL_SIZE_PX","ArenaCropper","ArenaRect","CellBaselineStore","CellDifference",
    "CellSearchGroup","CellState","CombatAction","CombatTarget","FragmentRole","GridCell",
    "KnownSpriteRegistry","LocalBackgroundState","LocalPerceptionState","NativeGrid64",
    "PlayerCentricCombatGrid","PR27CombatSystem","PR27Config","PR27FrameResult","RoundState",
    "SpriteClass","SpriteFragment","SpriteObservation","TrackState","TrackedSprite",
]
