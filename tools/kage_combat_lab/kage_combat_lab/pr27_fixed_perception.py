from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np

from .pr27_animated_background import AnimatedBackgroundModel, BackgroundClass, BackgroundEvidence
from .pr27_camera_motion import CameraMotionEstimator, CameraMotionResult
from .pr27_entity_validation import CandidateClass, EntityCandidate, EntityValidator
from .pr27_fixed_grid import DEFAULT_FIXED_GRID, FixedNativeGridCalibration, NativeRect, PR278CalibrationMismatch
from .pr27_fixed_result import FixedPerceptionResult
from .pr27_fixed_self import FixedSelfDetector, SelfVisualObservation, SelfVisualState
from .pr27_hostility import HostilityEvaluator, HostilityState, HostilityTrack
from .pr27_noise_model import NoiseAwareDifferenceGate, NoiseGateResult
from .pr27_object_tracking import PersistentObjectTrack, PersistentObjectTracker
from .pr27_spawn_delta import SpawnDeltaDetector
from .pr27_trainer_identity import TrainerEvidence, TrainerIdentityTracker, TrainerState


class FixedPerceptionSystem:
    """PR27.9 fixed-grid, noise-aware, object-first perception pipeline."""

    def __init__(
        self,
        *,
        grid: FixedNativeGridCalibration = DEFAULT_FIXED_GRID,
        strict_native: bool = True,
    ) -> None:
        self.grid = grid
        self.strict_native = bool(strict_native)
        self.self_detector = FixedSelfDetector(grid)
        self.camera = CameraMotionEstimator()
        self.animated_background = AnimatedBackgroundModel()
        self.noise_gate = NoiseAwareDifferenceGate(grid)
        self.entity_validator = EntityValidator(grid)
        self.object_tracker = PersistentObjectTracker(grid)
        self.hostility = HostilityEvaluator()
        self.trainer_identity = TrainerIdentityTracker()
        self.spawn_detector = SpawnDeltaDetector()
        self.previous_frame: np.ndarray | None = None
        self.previous_residual: np.ndarray | None = None
        self.pre_spawn_frame: np.ndarray | None = None
        self.frame_index = 0
        self.trainer_bbox: NativeRect | None = None
        self._last_static_terrain_mask: np.ndarray | None = None

    def set_pre_spawn(self, frame_bgr: np.ndarray) -> None:
        self.pre_spawn_frame = np.ascontiguousarray(frame_bgr.copy())
        self.spawn_detector.set_pre_spawn(frame_bgr)

    def set_trainer_identity(
        self,
        pre_click_frame_bgr: np.ndarray,
        bbox: NativeRect,
        *,
        detector_score: float = 1.0,
        detector_mode: str = "PRE_CLICK_CAPTURE",
    ) -> None:
        identity = TrainerIdentityTracker.capture(
            pre_click_frame_bgr,
            bbox,
            detector_score=detector_score,
            detector_mode=detector_mode,
        )
        self.trainer_identity = TrainerIdentityTracker(identity)
        self.trainer_bbox = bbox

    @staticmethod
    def _rect_mask(shape: tuple[int, int], rect: NativeRect | None) -> np.ndarray:
        mask = np.zeros(shape, dtype=np.uint8)
        if rect is None:
            return mask
        height, width = shape
        clipped = rect.intersect(NativeRect(0, 0, width, height))
        if clipped is not None:
            mask[clipped.top:clipped.bottom, clipped.left:clipped.right] = 255
        return mask

    @staticmethod
    def _legacy_debug_overlay_mask(frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        saturated = (hsv[:, :, 1] >= 150) & (hsv[:, :, 2] >= 150)
        mask = np.where(saturated, 255, 0).astype(np.uint8)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        dark = np.where(gray <= 75, 255, 0).astype(np.uint8)
        lines = cv2.HoughLinesP(
            dark,
            1,
            np.pi / 180.0,
            threshold=35,
            minLineLength=28,
            maxLineGap=3,
        )
        if lines is not None:
            for raw in np.asarray(lines).reshape(-1, 4):
                x1, y1, x2, y2 = [int(value) for value in raw]
                if abs(x2 - x1) <= 2 or abs(y2 - y1) <= 2:
                    cv2.line(mask, (x1, y1), (x2, y2), 255, 4)
        mask[:90, :] = 255
        mask[890:, :] = 255
        return cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)

    def _camera_exclusion_mask(
        self,
        frame: np.ndarray,
        self_protected_mask: np.ndarray,
        trainer_evidence: TrainerEvidence | None,
    ) -> np.ndarray:
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        mask[self_protected_mask > 0] = 255
        if (
            trainer_evidence is not None
            and trainer_evidence.state is TrainerState.TRAINER_VISIBLE_CONFIRMED
            and trainer_evidence.observed_bbox is not None
        ):
            rect = trainer_evidence.observed_bbox
            mask[rect.top:rect.bottom, rect.left:rect.right] = 255
        for track in self.object_tracker.confirmed_tracks():
            rect = track.bbox.intersect(NativeRect(0, 0, frame.shape[1], frame.shape[0]))
            if rect is not None:
                mask[rect.top:rect.bottom, rect.left:rect.right] = 255
        mask[:90, :] = 255
        mask[890:, :] = 255
        return mask

    @staticmethod
    def _difference_mask(
        left: np.ndarray,
        right: np.ndarray,
        threshold: int = 20,
    ) -> np.ndarray:
        difference = cv2.absdiff(left, right)
        gray = cv2.cvtColor(difference, cv2.COLOR_BGR2GRAY)
        mask = np.where(gray >= threshold, 255, 0).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    def _background_cells(
        self,
        residual_mask: np.ndarray,
        ego_mask: np.ndarray,
    ) -> tuple[dict[tuple[int, int], BackgroundEvidence], np.ndarray]:
        changed_keys: set[tuple[int, int]] = set()
        cell_masks: dict[tuple[int, int], np.ndarray] = {}
        ego_scores: dict[tuple[int, int], float] = {}
        for cell in self.grid.roi_cells():
            rect = cell.native_rect
            patch = residual_mask[rect.top:rect.bottom, rect.left:rect.right]
            ego_patch = ego_mask[rect.top:rect.bottom, rect.left:rect.right]
            cell_masks[cell.relative_key] = patch
            changed_ratio = np.count_nonzero(patch) / max(1, patch.size)
            if changed_ratio >= 0.012:
                changed_keys.add(cell.relative_key)
            ego_scores[cell.relative_key] = float(np.count_nonzero(ego_patch) / max(1, ego_patch.size))
        evidence: dict[tuple[int, int], BackgroundEvidence] = {}
        animated_mask = np.zeros(residual_mask.shape, dtype=np.uint8)
        for cell in self.grid.roi_cells():
            row, column = cell.relative_key
            neighbors = sum(
                (row + dy, column + dx) in changed_keys
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
            )
            item = self.animated_background.observe_cell(
                cell.relative_key,
                cell_masks[cell.relative_key],
                ego_motion_match=min(1.0, ego_scores[cell.relative_key] * 4.0),
                synchronized_neighbors=neighbors,
            )
            evidence[cell.relative_key] = item
            if item.background_class in {
                BackgroundClass.ANIMATED_BACKGROUND,
                BackgroundClass.BACKGROUND_EGO_MOTION,
            }:
                rect = cell.native_rect
                animated_mask[rect.top:rect.bottom, rect.left:rect.right] = 255
        return evidence, animated_mask

    @staticmethod
    def _connected_components(mask: np.ndarray) -> int:
        count, _labels = cv2.connectedComponents((mask > 0).astype(np.uint8), 8)
        return max(0, int(count) - 1)

    def _plan(
        self,
        self_observation: SelfVisualObservation,
        tracks: tuple[HostilityTrack, ...],
        motion: CameraMotionResult,
    ) -> tuple[str, str]:
        if not self_observation.found or self_observation.state is SelfVisualState.SELF_LOST_CRITICAL:
            return "NONE", "SELF_NOT_CONFIRMED"
        hostile = next(
            (
                track
                for track in tracks
                if track.visible and track.hostility_state is HostilityState.HOSTILE_CONFIRMED
            ),
            None,
        )
        if hostile is None:
            return "NONE", "HOSTILE_NOT_CONFIRMED"
        if self.frame_index > 0 and not motion.shift_accepted and motion.shift_rejection_reason is not None:
            return "NONE", "CAMERA_MOTION_NOT_VALIDATED"
        assert self_observation.feet_anchor is not None
        target = hostile.candidate.feet_anchor
        dx = target[0] - self_observation.feet_anchor[0]
        dy = target[1] - self_observation.feet_anchor[1]
        if max(abs(dx), abs(dy)) < 4.0:
            return "NONE", "SAME_CELL_DIRECTION_AMBIGUOUS"
        direction = (
            "RIGHT" if dx > 0 else "LEFT"
            if abs(dx) >= abs(dy)
            else "DOWN" if dy > 0 else "UP"
        )
        relative = hostile.candidate.relative_cell
        distance = 99 if relative is None else max(abs(relative[0]), abs(relative[1]))
        if distance <= 1:
            return f"TURN_{direction}", "PERCEPTION_ONLY_NO_PHYSICAL_INPUT"
        return f"CHASE_{direction}", "PERCEPTION_ONLY_NO_PHYSICAL_INPUT"

    def _render_overlay(
        self,
        frame: np.ndarray,
        *,
        self_observation: SelfVisualObservation,
        motion: CameraMotionResult,
        candidates: Iterable[EntityCandidate],
        object_tracks: Iterable[PersistentObjectTrack],
        hostility_tracks: Iterable[HostilityTrack],
        trainer_evidence: TrainerEvidence,
        noise: NoiseGateResult,
        raw_components: int,
        planned_action: str,
        block_reason: str,
    ) -> np.ndarray:
        output = frame.copy()
        for cell in self.grid.roi_cells():
            rect = cell.native_rect
            cv2.rectangle(output, (rect.left, rect.top), (rect.right - 1, rect.bottom - 1), (80, 160, 80), 1)
            cv2.putText(
                output,
                f"({cell.relative_row:+d},{cell.relative_column:+d})",
                (rect.left + 2, rect.top + 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                (30, 90, 30),
                1,
                cv2.LINE_AA,
            )
        fixed = self.grid.self_cell_rect()
        cv2.rectangle(output, (fixed.left, fixed.top), (fixed.right - 1, fixed.bottom - 1), (255, 255, 0), 2)
        cv2.putText(output, "FIXED SELF CELL (0,0)", (fixed.left - 8, fixed.top - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 0), 1, cv2.LINE_AA)
        if self_observation.bbox is not None:
            rect = self_observation.bbox
            color = (255, 0, 0) if self_observation.found else (100, 100, 100)
            cv2.rectangle(output, (rect.left, rect.top), (rect.right - 1, rect.bottom - 1), color, 2)
        for candidate in candidates:
            rect = candidate.bbox
            color = (0, 165, 255) if candidate.candidate_class is CandidateClass.HUMANOID_CANDIDATE else (0, 255, 255)
            cv2.rectangle(output, (rect.left, rect.top), (rect.right - 1, rect.bottom - 1), color, 1)
        object_tracks_tuple = tuple(object_tracks)
        hostility_tracks_tuple = tuple(hostility_tracks)
        for track in object_tracks_tuple:
            rect = track.bbox
            color = (255, 200, 0) if track.confirmed else (180, 180, 0)
            cv2.rectangle(output, (rect.left, rect.top), (rect.right - 1, rect.bottom - 1), color, 2)
            cv2.putText(output, f"OBJ {track.track_id} {track.state.value}", (rect.left, max(12, rect.top - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.34, color, 1, cv2.LINE_AA)
        for track in hostility_tracks_tuple:
            if track.hostility_state is HostilityState.HOSTILE_CONFIRMED:
                rect = track.candidate.bbox
                cv2.rectangle(output, (rect.left, rect.top), (rect.right - 1, rect.bottom - 1), (0, 0, 255), 2)
        if trainer_evidence.observed_bbox is not None:
            rect = trainer_evidence.observed_bbox
            color = (255, 0, 255) if trainer_evidence.current_frame_match else (160, 80, 160)
            cv2.rectangle(output, (rect.left, rect.top), (rect.right - 1, rect.bottom - 1), color, 1)
            cv2.putText(output, "TRAINER IDENTITY", (rect.left, max(12, rect.top - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)

        body_tracks = sum(track.confirmed for track in object_tracks_tuple)
        opponent_tracks = sum(track.hostility_state in {HostilityState.OPPONENT_CANDIDATE, HostilityState.HOSTILITY_PENDING, HostilityState.HOSTILE_CONFIRMED} for track in hostility_tracks_tuple)
        pending = sum(track.hostility_state is HostilityState.HOSTILITY_PENDING for track in hostility_tracks_tuple)
        hostile = sum(track.hostility_state is HostilityState.HOSTILE_CONFIRMED for track in hostility_tracks_tuple)
        lines = [
            "PR27.9 NOISE-AWARE OBJECT PERCEPTION / PHYSICAL INPUT DISABLED",
            "NATIVE=1920x1037 GRID=64 OFFSET=(0,21) SELF_ABS=(6,15)",
            f"RAW_ACTIVE_PIXELS={noise.raw_active_pixels} NOISE_REMOVED_PERCENT={noise.noise_removed_ratio * 100.0:.1f} NEW_CANDIDATE_GATE=12%",
            f"CAMERA_RAW_SHIFT=({motion.phase_dx:.1f},{motion.phase_dy:.1f}) ACCEPTED_SHIFT=({motion.dx_px:.1f},{motion.dy_px:.1f}) REJECTION={motion.shift_rejection_reason or '-'}",
            f"SELF_SCORE={self_observation.template_score:.3f} SELF_STATE={self_observation.state.value} SELF_TEMPLATE_ID={self_observation.matched_template_id}",
            f"TRAINER_STATE={trainer_evidence.state.value} TRAINER_SCORE={trainer_evidence.identity_score:.3f} TRAINER_BLIND_PIXELS=0",
            f"RAW_COMPONENTS={raw_components} BODY_TRACKS={body_tracks} OPPONENT_TRACKS={opponent_tracks} HOSTILITY_PENDING={pending} HOSTILE_CONFIRMED={hostile}",
            f"PLANNED_ACTION={planned_action} ACTION_BLOCK_REASON={block_reason}",
        ]
        panel_height = 18 * len(lines) + 8
        panel = output.copy()
        cv2.rectangle(panel, (0, 0), (output.shape[1], panel_height), (0, 0, 0), -1)
        cv2.addWeighted(panel, 0.72, output, 0.28, 0.0, output)
        for index, text in enumerate(lines):
            cv2.putText(output, text, (8, 18 + index * 18), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 1, cv2.LINE_AA)
        return output

    def process_native(
        self,
        frame_bgr: np.ndarray,
        *,
        trainer_bbox: NativeRect | None = None,
        source_reconstructed: bool = False,
        source_has_legacy_overlay: bool = False,
        player_stationary: bool = True,
    ) -> FixedPerceptionResult:
        import time

        started = time.perf_counter()
        if self.strict_native:
            self.grid.validate_native_shape(frame_bgr.shape)
        elif frame_bgr.shape[:2] != (self.grid.native_height, self.grid.native_width):
            raise PR278CalibrationMismatch("PR27_CALIBRATION_MISMATCH:normalized replay must be native-sized")
        original = np.ascontiguousarray(frame_bgr.copy())
        self_observation = self.self_detector.observe(original)
        self_protected_mask = self.self_detector.protected_mask(original.shape[:2])

        if trainer_bbox is not None and self.trainer_bbox is None:
            self.trainer_bbox = trainer_bbox
        trainer_evidence_before = self.trainer_identity.last
        camera_exclusion = self._camera_exclusion_mask(original, self_protected_mask, trainer_evidence_before)
        motion = self.camera.observe(
            original,
            exclusion_mask=camera_exclusion,
            static_terrain_mask=self._last_static_terrain_mask,
            stationary_mode=bool(player_stationary),
        )
        trainer_evidence = self.trainer_identity.observe(
            original,
            camera_dx=motion.dx_px if motion.shift_accepted else 0.0,
            camera_dy=motion.dy_px if motion.shift_accepted else 0.0,
        )
        self.trainer_bbox = (
            trainer_evidence.observed_bbox
            or trainer_evidence.predicted_bbox
            or self.trainer_bbox
        )

        raw_mask = np.zeros(original.shape[:2], dtype=np.uint8)
        residual_mask = np.zeros(original.shape[:2], dtype=np.uint8)
        ego_mask = np.zeros(original.shape[:2], dtype=np.uint8)
        if self.previous_frame is not None:
            raw_mask = self._difference_mask(original, self.previous_frame)
            aligned_previous = self.camera.align_previous_to_current(self.previous_frame, motion)
            residual_mask = self._difference_mask(original, aligned_previous)
            ego_mask = cv2.bitwise_and(raw_mask, cv2.bitwise_not(residual_mask))
        if source_has_legacy_overlay:
            legacy_overlay_mask = self._legacy_debug_overlay_mask(original)
            residual_mask[legacy_overlay_mask > 0] = 0
            raw_mask[legacy_overlay_mask > 0] = 0
            ego_mask[legacy_overlay_mask > 0] = 0

        background_evidence, animated_mask = self._background_cells(residual_mask, ego_mask)
        spawn_seed_mask = self.spawn_detector.difference_mask(
            original,
            self_mask=self_protected_mask,
            animated_mask=animated_mask,
        )
        existing_track_mask = self.object_tracker.track_mask(original.shape[:2])
        noise = self.noise_gate.observe(
            residual_mask,
            animated_hint_mask=animated_mask,
            tracked_object_mask=existing_track_mask,
            spawn_delta_mask=spawn_seed_mask,
        )
        self._last_static_terrain_mask = noise.static_terrain_mask

        roi_mask = np.zeros(original.shape[:2], dtype=np.uint8)
        for cell in self.grid.roi_cells():
            rect = cell.native_rect
            roi_mask[rect.top:rect.bottom, rect.left:rect.right] = 255
        entity_proposal = cv2.bitwise_and(noise.proposal_mask, roi_mask)
        candidates_all = self.entity_validator.detect(
            original,
            entity_proposal,
            animated_background_mask=animated_mask,
            trainer_mask=None,
            self_mask=self_protected_mask,
            previous_residual_mask=self.previous_residual,
        )
        candidates, trainer_veto_candidate_ids, trainer_scores = self.trainer_identity.veto_candidates(
            original,
            candidates_all,
        )
        object_tracks = self.object_tracker.update(
            original,
            candidates,
            frame_index=self.frame_index,
        )

        spawn_evidence = self.spawn_detector.observe(
            original,
            candidates,
            self_mask=self_protected_mask,
            animated_mask=animated_mask,
        )
        spawn_candidate_ids = frozenset(spawn_evidence.candidate_ids)
        spawn_object_ids: set[int] = set()
        trainer_veto_object_ids: set[int] = set()
        for track in object_tracks:
            latest_candidate_id = track.lineage[-1] if track.lineage else track.candidate.candidate_id
            track.trainer_similarity = trainer_scores.get(latest_candidate_id, track.trainer_similarity)
            rect = track.bbox.intersect(NativeRect(0, 0, original.shape[1], original.shape[0]))
            if rect is not None:
                protected_patch = self_protected_mask[rect.top:rect.bottom, rect.left:rect.right]
                track.self_similarity = float(np.count_nonzero(protected_patch) / max(1, protected_patch.size))
            if latest_candidate_id in spawn_candidate_ids:
                track.spawned_after_dojo = True
            if track.spawned_after_dojo:
                spawn_object_ids.add(track.track_id)
            if latest_candidate_id in trainer_veto_candidate_ids or track.trainer_similarity >= 0.82:
                trainer_veto_object_ids.add(track.track_id)

        self_anchor = self_observation.feet_anchor if self_observation.found else None
        hostility_tracks = self.hostility.update(
            self.object_tracker.confirmed_tracks(),
            frame_index=self.frame_index,
            self_anchor=self_anchor,
            player_stationary=player_stationary and not source_has_legacy_overlay,
            self_confirmed=self_observation.found,
            spawn_object_track_ids=spawn_object_ids,
            trainer_veto_object_track_ids=trainer_veto_object_ids,
        )
        planned_action, block_reason = self._plan(self_observation, hostility_tracks, motion)
        body_mask = self.entity_validator.mask_for_candidates(original.shape[:2], candidates)
        trainer_match_mask = np.zeros(original.shape[:2], dtype=np.uint8)
        for candidate in candidates_all:
            if candidate.candidate_id in trainer_veto_candidate_ids:
                rect = candidate.bbox
                trainer_match_mask[rect.top:rect.bottom, rect.left:rect.right] = 255
        raw_components = self._connected_components(residual_mask)
        overlay = self._render_overlay(
            original,
            self_observation=self_observation,
            motion=motion,
            candidates=candidates_all,
            object_tracks=object_tracks,
            hostility_tracks=hostility_tracks,
            trainer_evidence=trainer_evidence,
            noise=noise,
            raw_components=raw_components,
            planned_action=planned_action,
            block_reason=block_reason,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        result = FixedPerceptionResult(
            frame_index=self.frame_index,
            native_size=(original.shape[1], original.shape[0]),
            fixed_self_cell=(self.grid.self_row, self.grid.self_column),
            fixed_self_bbox=self.grid.self_cell_rect(),
            self_observation=self_observation,
            camera_motion=motion,
            camera_compensated=motion.compensated,
            background_evidence=background_evidence,
            candidates=candidates_all,
            hostility_tracks=hostility_tracks,
            trainer_bbox=self.trainer_bbox,
            trainer_evidence=trainer_evidence,
            trainer_mask_only=self.trainer_bbox is not None,
            trainer_rgb_replaced=False,
            planned_action=planned_action,
            action_block_reason=block_reason,
            original_bgr=original,
            overlay_bgr=overlay,
            raw_difference_mask=raw_mask,
            compensated_residual_mask=residual_mask,
            animated_background_mask=animated_mask,
            body_mask=body_mask,
            noise_gate=noise,
            object_tracks=object_tracks,
            spawn_evidence=spawn_evidence,
            self_protected_mask=self_protected_mask,
            trainer_identity_match_mask=trainer_match_mask,
            object_proposal_mask=entity_proposal,
            camera_static_terrain_mask=noise.static_terrain_mask,
            source_reconstructed=source_reconstructed,
            source_has_legacy_overlay=source_has_legacy_overlay,
            timings_ms={"total_ms": elapsed_ms},
        )
        self.previous_frame = original
        self.previous_residual = residual_mask
        self.frame_index += 1
        return result

    def process_debug_arena(
        self,
        arena_bgr: np.ndarray,
        *,
        arena_rect: NativeRect = NativeRect(77, 41, 1843, 892),
        trainer_bbox: NativeRect | None = None,
    ) -> FixedPerceptionResult:
        expected = (arena_rect.height, arena_rect.width)
        if arena_bgr.shape[:2] != expected:
            raise PR278CalibrationMismatch(
                "PR27_REPLAY_SOURCE_SHAPE_UNSUPPORTED:"
                f"expected_debug_arena={expected[::-1]} actual={arena_bgr.shape[1]}x{arena_bgr.shape[0]}"
            )
        fill = np.median(arena_bgr.reshape(-1, 3), axis=0).astype(np.uint8)
        native = np.empty((self.grid.native_height, self.grid.native_width, 3), dtype=np.uint8)
        native[:] = fill
        native[arena_rect.top:arena_rect.bottom, arena_rect.left:arena_rect.right] = arena_bgr
        return self.process_native(
            native,
            trainer_bbox=trainer_bbox,
            source_reconstructed=True,
            source_has_legacy_overlay=True,
            player_stationary=False,
        )


__all__ = [
    "FixedPerceptionResult",
    "FixedPerceptionSystem",
    "FixedSelfDetector",
    "SelfVisualObservation",
    "SelfVisualState",
]
