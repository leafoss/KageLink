from __future__ import annotations

import math
import time
from collections import Counter, deque
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .pr27_cells import (
    ArenaCropper,
    CellBaselineStore,
    CellDifferenceDetector,
    ChangedCellGrouper,
    LocalBackgroundModel,
    NativeGrid64,
    PlayerCentricCombatGrid,
)
from .pr27_facing import FacingObserver, HitDetector
from .pr27_fragments import SpriteAssembler, SpriteFragmentExtractor
from .pr27_identity import SelfTracker
from .pr27_model import (
    CELL_SIZE_PX,
    ArenaRect,
    CellDifference,
    CellSearchGroup,
    CellState,
    CombatAction,
    CombatTarget,
    FragmentRole,
    GridCell,
    LocalBackgroundState,
    LocalPerceptionState,
    PR27Config,
    PR27FrameResult,
    RecoveryState,
    RoundState,
    SelfTrackState,
    SpriteClass,
    SpriteFragment,
    SpriteObservation,
    SpriteRole,
    TrackState,
    TrackedSprite,
)
from .pr27_overlap import MergedBodyDetector, MergedBodyEvidence, role_conflict
from .pr27_planning import CombatPlanner
from .pr27_registry import KnownSpriteRegistry
from .pr27_tracker import SpriteTracker


class PR27CombatSystem:
    """PR27.7 SELF-first local combat perception and bounded recovery."""

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
        self.self_tracker = SelfTracker(self.config)
        self.tracker = SpriteTracker(self.config, registry)
        self.overlap_detector = MergedBodyDetector(self.config)
        self.facing_observer = FacingObserver(self.config)
        self.hit_detector = HitDetector(self.config)
        self.planner = CombatPlanner(self.config, require_visual_facing=True)
        self.frame_index = 0
        self.visual_burst_active = False
        self.local_occlusion_active = False
        self.local_occlusion_clear_count = 0
        self.local_occlusion_frames = 0
        self.previous_changed_count = 0
        self.trainer_exclusion_bbox: tuple[int, int, int, int] | None = None
        self.reference_arena: np.ndarray | None = None
        self.reference_valid: np.ndarray | None = None
        self.player_calibration_samples: deque[
            tuple[tuple[int, int, int, int], tuple[float, float]]
        ] = deque(maxlen=7)
        self.last_merged = MergedBodyEvidence()
        self.last_role_conflict_reason: str | None = None
        self.last_physical_actions: tuple[str, ...] = ()

    @staticmethod
    def _bbox_intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

    def record_physical_actions(self, actions: Sequence[str]) -> None:
        self.last_physical_actions = tuple(str(action) for action in actions)
        self.facing_observer.note_physical_actions(self.last_physical_actions)
        self.planner.note_physical_actions(self.last_physical_actions)

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
            scale = min(output_w / max(1.0, source_w), output_h / max(1.0, source_h))
            rendered_w, rendered_h = source_w * scale, source_h * scale
            offset_x = (output_w - rendered_w) / 2.0
            offset_y = (output_h - rendered_h) / 2.0
            output_x = float(center_normalized[0]) * (output_w - 1.0)
            output_y = float(center_normalized[1]) * (output_h - 1.0)
            center_frame = (
                min(source_w - 1.0, max(0.0, (output_x - offset_x) / scale)),
                min(source_h - 1.0, max(0.0, (output_y - offset_y) / scale)),
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
        self.trainer_exclusion_bbox = None if right <= left or bottom <= top else (left, top, right - left, bottom - top)
        self.tracker.set_trainer_exclusion(self.trainer_exclusion_bbox)

    def _update_trainer_relative_cells(self, cells: tuple[GridCell, ...]) -> None:
        if self.trainer_exclusion_bbox is None:
            self.tracker.set_trainer_exclusion(None)
            return
        forbidden = [
            (cell.row, cell.column)
            for cell in cells
            if self._bbox_intersects(cell.bbox, self.trainer_exclusion_bbox)
        ]
        self.tracker.set_trainer_exclusion(self.trainer_exclusion_bbox, forbidden)

    def load_baseline(self, path: Path, native_frame_bgr: np.ndarray) -> int:
        rect, arena = self.cropper.crop(native_frame_bgr)
        metadata = CellBaselineStore.read_metadata(path)
        self.grid.set_phase(
            int(metadata.get("grid_phase_x", 0) or 0),
            int(metadata.get("grid_phase_y", 0) or 0),
        )
        cells = self.grid.build(arena.shape)
        loaded = self.baselines.load_npz(path, cells)
        self.reference_arena, self.reference_valid = self.baselines.render_arena(arena.shape)
        self._configure_trainer_exclusion(
            metadata,
            native_shape=native_frame_bgr.shape[:2],
            arena_rect=rect,
            arena_shape=arena.shape[:2],
        )
        self.self_tracker.bootstrap_metadata(metadata)
        expected = (
            arena.shape[1] * self.config.player_anchor_x_ratio,
            arena.shape[0] * self.config.player_anchor_y_ratio,
        )
        self.self_tracker.expected_anchor = expected
        self.combat_grid.update_center(expected)
        return loaded

    def _ensure_reference(self, arena: np.ndarray) -> None:
        if len(self.baselines) == 0:
            raise RuntimeError("PR27_BASELINE_NOT_LOADED")
        if self.reference_arena is None or self.reference_arena.shape != arena.shape:
            self.reference_arena, self.reference_valid = self.baselines.render_arena(arena.shape)
        assert self.reference_valid is not None

    def _player_track(self) -> TrackedSprite | None:
        track = self.self_tracker.track
        if track is None or track.track_state is TrackState.LOST or not track.has_body_lock:
            return None
        return track

    def _enemy_track(self) -> TrackedSprite | None:
        if self.tracker.enemy_track_id is None:
            return None
        return self.tracker.tracks.get(self.tracker.enemy_track_id)

    def _roi_anchor(self, arena: np.ndarray) -> tuple[float, float]:
        player = self._player_track()
        if player is not None:
            return player.predicted_anchor or player.body_anchor or self.combat_grid.center_anchor or (
                arena.shape[1] * self.config.player_anchor_x_ratio,
                arena.shape[0] * self.config.player_anchor_y_ratio,
            )
        if self.combat_grid.center_anchor is not None:
            return self.combat_grid.center_anchor
        return (
            arena.shape[1] * self.config.player_anchor_x_ratio,
            arena.shape[0] * self.config.player_anchor_y_ratio,
        )

    def _focused_differences(
        self,
        differences: Mapping[tuple[int, int], CellDifference],
    ) -> Mapping[tuple[int, int], CellDifference]:
        target = self._enemy_track()
        if target is None or target.anchor_cell is None or target.track_state is not TrackState.TRACKED:
            return differences
        radius = self.config.target_focus_radius_cells
        row, column = target.anchor_cell
        target_focus = {
            (row + dr, column + dc)
            for dr in range(-radius, radius + 1)
            for dc in range(-radius, radius + 1)
            if dr * dr + dc * dc <= radius * radius
        }
        # Keep the two-cell ring around SELF visible even while a target is latched.
        close_self = {
            (dy, dx)
            for dy in range(-2, 3)
            for dx in range(-2, 3)
            if dx * dx + dy * dy <= 4
        }
        focus = target_focus | close_self
        return {key: value for key, value in differences.items() if key in focus}

    def _detect_local_occlusion(
        self,
        differences: Mapping[tuple[int, int], CellDifference],
    ) -> tuple[bool, set[tuple[int, int]], str]:
        changed = [key for key, difference in differences.items() if difference.state is CellState.CHANGED]
        row_counts = Counter(row for row, _ in changed)
        long_row = max(row_counts.values(), default=0) >= self.config.local_occlusion_row_span_cells
        dense = len(changed) >= self.config.local_occlusion_min_changed_cells
        spike = len(changed) >= max(
            self.config.local_occlusion_min_changed_cells,
            int(max(1, self.previous_changed_count) * 1.65),
        )
        detected = dense or (long_row and len(changed) >= 5) or spike
        reason = f"local visual occlusion changed={len(changed)} max_row={max(row_counts.values(), default=0)}"
        return detected, set(changed), reason

    def _all_tracks(self, non_self_tracks: Sequence[TrackedSprite] | None = None) -> tuple[TrackedSprite, ...]:
        values: list[TrackedSprite] = []
        if self.self_tracker.track is not None:
            values.append(self.self_tracker.track)
        if non_self_tracks is None:
            values.extend(self.tracker.tracks.values())
        else:
            values.extend(non_self_tracks)
        return tuple(sorted(values, key=lambda track: track.track_id))

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
        reason: str,
        local_state: LocalPerceptionState = LocalPerceptionState.NORMAL,
        local_occlusion: bool = False,
        timings: Mapping[str, float] | None = None,
        role_conflict_flag: bool = False,
        hit_event: bool = False,
    ) -> PR27FrameResult:
        rejections = Counter(self.extractor.last_rejections)
        rejections.update(self.assembler.last_rejections)
        tracks_value = tracks if tracks is not None else self._all_tracks()
        player = self.self_tracker.track
        enemy = self._enemy_track()
        containment = self.combat_grid.containment_ratio(
            None if player is None else player.body_bbox,
            None if player is None else player.body_anchor,
        )
        role_flip_blocked = self.tracker.role_flip_blocked
        candidate_rejections = list(self.tracker.last_candidate_rejections)
        if self.self_tracker.last_rejection != "-":
            candidate_rejections.append(self.self_tracker.last_rejection)
        if role_flip_blocked:
            candidate_rejections.append(role_flip_blocked)
        if self.last_merged.detected:
            candidate_rejections.append("MERGED_BODY")
        association_diagnostics = tuple(self.self_tracker.diagnostics + self.tracker.association_diagnostics)
        relative_anchor = None if target is None else target.relative_anchor_px
        subcell_direction = None
        subcell_confidence = 0.0
        if relative_anchor is not None:
            dx, dy = relative_anchor
            magnitude = max(abs(dx), abs(dy))
            if magnitude >= self.config.subcell_direction_threshold_px:
                subcell_direction = target.direction
                subcell_confidence = min(1.0, magnitude / CELL_SIZE_PX)
        return_value = PR27FrameResult(
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
            player_track_id=None if player is None else player.track_id,
            target=target,
            action=action,
            state=state,
            scene_changed=False,
            reason=reason,
            grid_phase=self.combat_grid.phase,
            fragment_rejections=dict(rejections),
            candidate_rejections=tuple(candidate_rejections),
            roi_center=self.combat_grid.center_anchor,
            roi_radius_cells=self.config.roi_radius_cells,
            roi_processed_cell_count=len(cells),
            ignored_outside_roi_count=max(
                0,
                math.ceil(arena.shape[0] / CELL_SIZE_PX) * math.ceil(arena.shape[1] / CELL_SIZE_PX) - len(cells),
            ),
            player_cell=(0, 0),
            player_body_bbox=None if player is None else player.body_bbox,
            player_body_anchor=None if player is None else player.body_anchor,
            player_body_containment_ratio=containment,
            enemy_relative_cell=None if target is None else target.anchor_cell,
            local_state=local_state,
            local_background_states=dict(self.local_background.states),
            local_occlusion_detected=local_occlusion,
            facing_expected=None if target is None else target.direction,
            facing_detected=self.facing_observer.observed,
            facing_confirmed=self.facing_observer.confirmed,
            facing_correction_action=self.planner.last_facing_correction_action,
            timings_ms=dict(timings or {}),
            self_track_state=self.self_tracker.state,
            self_role_source=self.self_tracker.last_role_source,
            self_confidence=0.0 if player is None else player.confidence,
            self_observation_id=self.self_tracker.last_observation_id,
            self_predicted_anchor=None if player is None else player.predicted_anchor,
            self_association_score=self.self_tracker.last_association_score,
            self_identity_score=self.self_tracker.last_identity_score,
            enemy_observation_id=None if enemy is None else enemy.observation_id,
            enemy_association_score=0.0 if enemy is None else enemy.association_score,
            enemy_identity_score=0.0 if enemy is None else enemy.identity_score,
            enemy_relative_anchor_px=relative_anchor,
            subcell_direction=subcell_direction,
            subcell_direction_confidence=subcell_confidence,
            role_conflict=role_conflict_flag,
            role_flip_attempt=self.tracker.role_flip_attempt,
            role_flip_blocked=role_flip_blocked,
            shared_observation_blocked=self.tracker.shared_observation_blocked,
            merged_body_detected=self.last_merged.detected,
            merged_body_bbox=self.last_merged.bbox,
            self_enemy_iou=self.last_merged.self_enemy_iou,
            close_candidate_count=self.tracker.close_candidate_count,
            close_reacquire_state=self.planner.recovery_state,
            deadlock_counters=dict(self.planner.deadlock_counters),
            hit_event=hit_event,
            facing_commanded=self.facing_observer.commanded,
            facing_observed=self.facing_observer.observed,
            facing_template_scores=dict(self.facing_observer.template_scores),
            h_block_reason=self.planner.h_block_reason,
            recovery_action=self.planner.recovery_action,
            separation_action=self.planner.separation_action,
            association_diagnostics=association_diagnostics,
        )
        self.frame_index += 1
        return return_value

    def process(self, native_frame_bgr: np.ndarray, *, timestamp: float | None = None) -> PR27FrameResult:
        total_started = time.perf_counter()
        now = time.monotonic() if timestamp is None else float(timestamp)
        crop_started = time.perf_counter()
        rect, arena = self.cropper.crop(native_frame_bgr)
        crop_ms = (time.perf_counter() - crop_started) * 1000.0
        self._ensure_reference(arena)

        localization_started = time.perf_counter()
        anchor = self._roi_anchor(arena)
        self.combat_grid.update_center(anchor)
        cells = self.combat_grid.build(arena.shape)
        localization_ms = (time.perf_counter() - localization_started) * 1000.0
        self._update_trainer_relative_cells(cells)
        assert self.reference_arena is not None and self.reference_valid is not None
        self.local_background.sync_from_reference(
            self.reference_arena,
            self.reference_valid,
            arena,
            cells,
        )

        diff_started = time.perf_counter()
        differences = self.difference_detector.compare(arena, cells, self.local_background.baselines)
        diff_ms = (time.perf_counter() - diff_started) * 1000.0
        occlusion_differences = {
            key: value
            for key, value in differences.items()
            if self.local_background.states.get(key) is not LocalBackgroundState.LEARNING_BACKGROUND
        }
        detected, effect_cells, occlusion_reason = self._detect_local_occlusion(occlusion_differences)
        self.previous_changed_count = sum(
            difference.state is CellState.CHANGED
            for difference in occlusion_differences.values()
        )
        forced_unknown_cells: set[tuple[int, int]] = set()
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
            self.facing_observer.invalidate("local_visual_occlusion")

        timings = {
            "capture_ms": 0.0,
            "roi_crop_ms": crop_ms,
            "self_tracking_ms": 0.0,
            "player_localization_ms": localization_ms,
            "cell_difference_ms": diff_ms,
            "fragment_ms": 0.0,
            "non_self_detection_ms": 0.0,
            "association_ms": 0.0,
            "tracking_ms": 0.0,
            "planning_ms": 0.0,
            "overlay_render_ms": 0.0,
            "debug_enqueue_ms": 0.0,
            "total_loop_ms": (time.perf_counter() - total_started) * 1000.0,
        }

        if self.local_occlusion_active:
            self.self_tracker.coast(
                arena_shape=arena.shape,
                frame_index=self.frame_index,
                occluded=True,
            )
            retained_enemy_cells = {
                track.anchor_cell
                for track in self.tracker.tracks.values()
                if track.track_id == self.tracker.enemy_track_id and track.anchor_cell is not None
            }
            self.local_background.mark_occupancy(
                player_cells={(0, 0)},
                enemy_cells=retained_enemy_cells,
                effect_cells=effect_cells,
            )
            tracks = self._all_tracks()
            target, action, state, reason = self.planner.plan(
                tracks,
                arena_shape=arena.shape,
                local_state=LocalPerceptionState.LOCAL_VISUAL_OCCLUSION,
            )
            return self._result(
                now=now,
                rect=rect,
                arena=arena,
                cells=cells,
                differences=differences,
                tracks=tracks,
                target=target,
                action=action,
                state=state,
                reason=f"{occlusion_reason}; local body tracking coasts frame={self.local_occlusion_frames}/{self.config.local_occlusion_max_frames}",
                local_state=LocalPerceptionState.LOCAL_VISUAL_OCCLUSION,
                local_occlusion=True,
                timings=timings,
            )

        usable_differences = {
            key: value
            for key, value in differences.items()
            if self.local_background.states.get(key) is not LocalBackgroundState.LEARNING_BACKGROUND
        }
        search_differences = self._focused_differences(usable_differences)
        fragment_started = time.perf_counter()
        groups = self.grouper.group(search_differences)
        fragments = self.extractor.extract(arena, groups, search_differences)
        observations = self.assembler.assemble(arena, groups, fragments, cells=cells)
        fragment_ms = (time.perf_counter() - fragment_started) * 1000.0

        previous_self = self.self_tracker.track
        previous_enemy = self._enemy_track()
        self.last_merged = self.overlap_detector.detect(
            observations,
            self_track=previous_self,
            enemy_track=previous_enemy,
        )

        self_started = time.perf_counter()
        self_track, reserved_ids = self.self_tracker.update(
            observations,
            frame_index=self.frame_index,
            arena_shape=arena.shape,
            excluded_observation_ids=self.last_merged.observation_ids,
        )
        self_tracking_ms = (time.perf_counter() - self_started) * 1000.0
        if self_track is not None and self_track.body_anchor is not None:
            self.combat_grid.update_center(self_track.body_anchor)

        association_started = time.perf_counter()
        non_self_tracks = self.tracker.update(
            observations,
            frame_index=self.frame_index,
            arena_shape=arena.shape,
            self_track=self_track,
            reserved_observation_ids=reserved_ids,
            merged_observation_ids=self.last_merged.observation_ids,
        )
        association_ms = (time.perf_counter() - association_started) * 1000.0
        tracks = self._all_tracks(non_self_tracks)
        enemy = self._enemy_track()
        conflict = role_conflict(self_track, enemy)
        role_conflict_flag = conflict.conflict or self.tracker.role_flip_blocked is not None
        self.last_role_conflict_reason = conflict.reason or self.tracker.role_flip_blocked

        hit_event = self.hit_detector.observe(
            self_track,
            commanded_direction=self.facing_observer.commanded,
        )
        if hit_event:
            self.planner.invalidate_facing("HIT_EVENT_DETECTED")
            self.facing_observer.invalidate("HIT_EVENT_DETECTED")
        observed, confirmed, _scores = self.facing_observer.observe(
            arena,
            self_track,
            hit_event=hit_event,
        )
        self.planner.update_facing_observation(observed, confirmed=confirmed)

        if self_track is not None and self_track.body_anchor is not None and self_track.body_bbox is not None:
            if self.self_tracker.state is SelfTrackState.SELF_TRACKED:
                self.player_calibration_samples.append((self_track.body_bbox, self_track.body_anchor))
                if len(self.player_calibration_samples) >= 3:
                    boxes = np.asarray([item[0] for item in self.player_calibration_samples], dtype=np.float32)
                    anchors = np.asarray([item[1] for item in self.player_calibration_samples], dtype=np.float32)
                    median_box = tuple(int(round(value)) for value in np.median(boxes, axis=0))
                    median_anchor_raw = np.median(anchors, axis=0)
                    median_anchor = (float(median_anchor_raw[0]), float(median_anchor_raw[1]))
                    self.combat_grid.calibrate_to_body(median_box, median_anchor)

        local_state = (
            LocalPerceptionState.LOCAL_UNKNOWN_BACKGROUND
            if forced_unknown_cells or self.local_background.unknown_count > 0
            else LocalPerceptionState.NORMAL
        )
        planning_started = time.perf_counter()
        target, action, state, reason = self.planner.plan(
            tracks,
            arena_shape=arena.shape,
            local_state=local_state,
            merged_body=self.last_merged.detected,
            hit_event=hit_event,
            close_candidate_count=self.tracker.close_candidate_count,
            role_conflict=role_conflict_flag,
        )
        planning_ms = (time.perf_counter() - planning_started) * 1000.0
        if self.planner.request_target_reacquire:
            self.tracker.invalidate_enemy_lock("DEADLOCK_WATCHDOG_LOCAL_REACQUIRE")

        protected = {(0, 0)}
        player_cells = {(0, 0)}
        enemy_cells = set()
        for track in tracks:
            if track.anchor_cell is None:
                continue
            protected.add(track.anchor_cell)
            if track.effective_role is SpriteRole.ENEMY:
                enemy_cells.add(track.anchor_cell)
        protected.update(
            observation.anchor_cell
            for observation in observations
            if observation.merged_body and observation.anchor_cell is not None
        )
        self.local_background.mark_occupancy(
            player_cells=player_cells,
            enemy_cells=enemy_cells,
            effect_cells=set(),
        )
        self.local_background.learn(
            arena,
            cells,
            differences,
            protected_cells=protected,
            effect_cells=set(),
        )

        timings.update(
            {
                "fragment_ms": fragment_ms,
                "self_tracking_ms": self_tracking_ms,
                "non_self_detection_ms": association_ms,
                "association_ms": association_ms,
                "tracking_ms": self_tracking_ms + association_ms,
                "planning_ms": planning_ms,
                "total_loop_ms": (time.perf_counter() - total_started) * 1000.0,
            }
        )
        return self._result(
            now=now,
            rect=rect,
            arena=arena,
            cells=cells,
            differences=differences,
            groups=groups,
            fragments=fragments,
            observations=observations,
            tracks=tracks,
            target=target,
            action=action,
            state=state,
            reason=reason,
            local_state=local_state,
            local_occlusion=False,
            timings=timings,
            role_conflict_flag=role_conflict_flag,
            hit_event=hit_event,
        )


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
    "FragmentRole",
    "GridCell",
    "KnownSpriteRegistry",
    "LocalBackgroundState",
    "LocalPerceptionState",
    "NativeGrid64",
    "PlayerCentricCombatGrid",
    "PR27CombatSystem",
    "PR27Config",
    "PR27FrameResult",
    "RecoveryState",
    "RoundState",
    "SelfTrackState",
    "SpriteClass",
    "SpriteFragment",
    "SpriteObservation",
    "SpriteRole",
    "TrackState",
    "TrackedSprite",
]
