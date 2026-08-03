from __future__ import annotations

from typing import Iterable, Mapping

import cv2
import numpy as np

from .pr27_animated_background import AnimatedBackgroundModel, BackgroundClass, BackgroundEvidence
from .pr27_camera_motion import CameraMotionEstimator, CameraMotionResult
from .pr27_entity_validation import CandidateClass, EntityCandidate, EntityValidator
from .pr27_fixed_grid import DEFAULT_FIXED_GRID, FixedNativeGridCalibration, NativeRect, PR278CalibrationMismatch
from .pr27_fixed_result import FixedPerceptionResult
from .pr27_fixed_self import FixedSelfDetector, SelfVisualObservation, SelfVisualState
from .pr27_hostility import HostilityEvaluator, HostilityState, HostilityTrack
from .pr27_trainer_mask import TrainerMaskEvidence, TrainerMaskTracker


class FixedPerceptionSystem:
    """PR27.8 fixed-grid, perception-only pipeline."""

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
        self.entity_validator = EntityValidator(grid)
        self.hostility = HostilityEvaluator()
        self.previous_frame: np.ndarray | None = None
        self.previous_residual: np.ndarray | None = None
        self.frame_index = 0
        self.trainer_bbox: NativeRect | None = None
        self.trainer_tracker: TrainerMaskTracker | None = None

    @staticmethod
    def _rect_mask(shape: tuple[int, int], rect: NativeRect | None) -> np.ndarray:
        mask = np.zeros(shape, dtype=np.uint8)
        if rect is None:
            return mask
        height, width = shape
        left = max(0, min(width, rect.left))
        top = max(0, min(height, rect.top))
        right = max(left, min(width, rect.right))
        bottom = max(top, min(height, rect.bottom))
        mask[top:bottom, left:right] = 255
        return mask

    @staticmethod
    def _legacy_debug_overlay_mask(frame: np.ndarray) -> np.ndarray:
        """Mask PR27.7 annotations when replaying legacy debug evidence."""
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
            for raw in lines[:, 0]:
                x1, y1, x2, y2 = [int(value) for value in raw]
                if abs(x2 - x1) <= 2 or abs(y2 - y1) <= 2:
                    cv2.line(mask, (x1, y1), (x2, y2), 255, 4)
        mask[:90, :] = 255
        mask[890:, :] = 255
        return cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)

    def _camera_exclusion_mask(
        self,
        frame: np.ndarray,
        trainer_bbox: NativeRect | None,
    ) -> np.ndarray:
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        self_rect = self.grid.self_search_rect(
            side_margin=28,
            top_margin=32,
            bottom_margin=12,
        )
        mask[self_rect.top:self_rect.bottom, self_rect.left:self_rect.right] = 255
        if trainer_bbox is not None:
            mask[trainer_bbox.top:trainer_bbox.bottom, trainer_bbox.left:trainer_bbox.right] = 255
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
            ego_scores[cell.relative_key] = float(
                np.count_nonzero(ego_patch) / max(1, ego_patch.size)
            )
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

    def _plan(
        self,
        self_observation: SelfVisualObservation,
        tracks: tuple[HostilityTrack, ...],
        motion: CameraMotionResult,
    ) -> tuple[str, str]:
        if (
            not self_observation.found
            or self_observation.state is not SelfVisualState.SELF_TRACKED
        ):
            return "NONE", "SELF_NOT_CONFIRMED"
        hostile = next(
            (
                track
                for track in tracks
                if track.visible
                and track.hostility_state is HostilityState.HOSTILE_CONFIRMED
            ),
            None,
        )
        if hostile is None:
            return "NONE", "HOSTILE_NOT_CONFIRMED"
        if self.frame_index > 0 and not motion.compensated:
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
        evidence: Mapping[tuple[int, int], BackgroundEvidence],
        candidates: Iterable[EntityCandidate],
        tracks: Iterable[HostilityTrack],
        trainer_bbox: NativeRect | None,
        planned_action: str,
        block_reason: str,
    ) -> np.ndarray:
        del evidence
        output = frame.copy()
        for cell in self.grid.roi_cells():
            rect = cell.native_rect
            cv2.rectangle(
                output,
                (rect.left, rect.top),
                (rect.right - 1, rect.bottom - 1),
                (80, 160, 80),
                1,
            )
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
        cv2.rectangle(
            output,
            (fixed.left, fixed.top),
            (fixed.right - 1, fixed.bottom - 1),
            (255, 255, 0),
            2,
        )
        cv2.putText(
            output,
            "FIXED SELF CELL (0,0)",
            (fixed.left - 8, fixed.top - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (255, 255, 0),
            1,
            cv2.LINE_AA,
        )
        if self_observation.bbox is not None:
            rect = self_observation.bbox
            color = (255, 0, 0) if self_observation.found else (100, 100, 100)
            cv2.rectangle(
                output,
                (rect.left, rect.top),
                (rect.right - 1, rect.bottom - 1),
                color,
                2,
            )
            if self_observation.feet_anchor is not None:
                cv2.circle(
                    output,
                    tuple(int(round(value)) for value in self_observation.feet_anchor),
                    4,
                    color,
                    -1,
                )
        for candidate in candidates:
            rect = candidate.bbox
            color = (
                (0, 165, 255)
                if candidate.candidate_class is CandidateClass.HUMANOID_CANDIDATE
                else (0, 255, 255)
            )
            cv2.rectangle(
                output,
                (rect.left, rect.top),
                (rect.right - 1, rect.bottom - 1),
                color,
                1,
            )
        for track in tracks:
            if track.hostility_state is HostilityState.HOSTILE_CONFIRMED:
                rect = track.candidate.bbox
                cv2.rectangle(
                    output,
                    (rect.left, rect.top),
                    (rect.right - 1, rect.bottom - 1),
                    (0, 0, 255),
                    2,
                )
        if trainer_bbox is not None:
            cv2.rectangle(
                output,
                (trainer_bbox.left, trainer_bbox.top),
                (trainer_bbox.right - 1, trainer_bbox.bottom - 1),
                (255, 0, 255),
                2,
            )
            cv2.putText(
                output,
                "TRAINER MASK ONLY",
                (trainer_bbox.left, max(12, trainer_bbox.top - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                (255, 0, 255),
                1,
                cv2.LINE_AA,
            )
        lines = [
            "PR27.8 FIXED NATIVE GRID / PERCEPTION ONLY",
            "NATIVE_SIZE=1920x1037 GRID_SIZE=64 GRID_OFFSET=(0,21)",
            "FIXED_SELF_CELL_ABS=(6,15) FIXED_SELF_BBOX=[960,405,1024,469)",
            f"SELF_BODY_FOUND={self_observation.found} SELF_STATE={self_observation.state.value} SELF_SCORE={self_observation.template_score:.3f}",
            f"CAMERA_SHIFT=({motion.dx_px:.1f},{motion.dy_px:.1f}) CONF={motion.confidence:.3f} COMPENSATED={motion.compensated}",
            f"TRAINER_MASK_ONLY={trainer_bbox is not None} TRAINER_RGB_REPLACED=false",
            f"PLANNED_ACTION={planned_action} ACTION_BLOCK_REASON={block_reason}",
        ]
        panel_height = 18 * len(lines) + 8
        panel = output.copy()
        cv2.rectangle(panel, (0, 0), (output.shape[1], panel_height), (0, 0, 0), -1)
        cv2.addWeighted(panel, 0.72, output, 0.28, 0.0, output)
        for index, text in enumerate(lines):
            cv2.putText(
                output,
                text,
                (8, 18 + index * 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
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
            raise PR278CalibrationMismatch(
                "PR27_CALIBRATION_MISMATCH:normalized replay must be native-sized"
            )
        original = np.ascontiguousarray(frame_bgr.copy())
        self_observation = self.self_detector.observe(original)
        self_mask = self._rect_mask(original.shape[:2], self_observation.bbox)
        if (
            trainer_bbox is not None
            and (
                self.trainer_tracker is None
                or self.trainer_tracker.bbox != trainer_bbox
            )
        ):
            self.trainer_tracker = TrainerMaskTracker(trainer_bbox)
            self.trainer_bbox = trainer_bbox
        camera_exclusion = self._camera_exclusion_mask(original, self.trainer_bbox)
        motion = self.camera.observe(original, exclusion_mask=camera_exclusion)
        if self.trainer_tracker is not None:
            trainer_evidence = self.trainer_tracker.update(
                original,
                camera_motion=motion,
            )
            self.trainer_bbox = trainer_evidence.bbox
        else:
            trainer_evidence = TrainerMaskEvidence(None, 0.0, "NO_TRAINER_BBOX")
        raw_mask = np.zeros(original.shape[:2], dtype=np.uint8)
        residual_mask = np.zeros(original.shape[:2], dtype=np.uint8)
        ego_mask = np.zeros(original.shape[:2], dtype=np.uint8)
        if self.previous_frame is not None:
            raw_mask = self._difference_mask(original, self.previous_frame)
            aligned_previous = self.camera.align_previous_to_current(
                self.previous_frame,
                motion,
            )
            residual_mask = self._difference_mask(original, aligned_previous)
            ego_mask = cv2.bitwise_and(raw_mask, cv2.bitwise_not(residual_mask))
        residual_mask[camera_exclusion > 0] = 0
        if source_has_legacy_overlay:
            legacy_overlay_mask = self._legacy_debug_overlay_mask(original)
            residual_mask[legacy_overlay_mask > 0] = 0
            raw_mask[legacy_overlay_mask > 0] = 0
            ego_mask[legacy_overlay_mask > 0] = 0
        background_evidence, animated_mask = self._background_cells(
            residual_mask,
            ego_mask,
        )
        roi_mask = np.zeros(original.shape[:2], dtype=np.uint8)
        for cell in self.grid.roi_cells():
            rect = cell.native_rect
            roi_mask[rect.top:rect.bottom, rect.left:rect.right] = 255
        entity_residual = cv2.bitwise_and(residual_mask, roi_mask)
        trainer_mask = self._rect_mask(original.shape[:2], self.trainer_bbox)
        candidates = self.entity_validator.detect(
            original,
            entity_residual,
            animated_background_mask=animated_mask,
            trainer_mask=trainer_mask,
            self_mask=self_mask,
            previous_residual_mask=self.previous_residual,
        )
        self_anchor = (
            self_observation.feet_anchor
            if self_observation.feet_anchor is not None
            else (
                (self.grid.self_cell_rect().left + self.grid.self_cell_rect().right) / 2.0,
                self.grid.self_cell_rect().bottom - 8.0,
            )
        )
        tracks = self.hostility.update(
            candidates,
            frame_index=self.frame_index,
            self_anchor=self_anchor,
            player_stationary=player_stationary and not source_has_legacy_overlay,
        )
        planned_action, block_reason = self._plan(
            self_observation,
            tracks,
            motion,
        )
        body_mask = self.entity_validator.mask_for_candidates(
            original.shape[:2],
            candidates,
        )
        overlay = self._render_overlay(
            original,
            self_observation=self_observation,
            motion=motion,
            evidence=background_evidence,
            candidates=candidates,
            tracks=tracks,
            trainer_bbox=self.trainer_bbox,
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
            candidates=candidates,
            hostility_tracks=tracks,
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
                f"expected_debug_arena={expected[::-1]} "
                f"actual={arena_bgr.shape[1]}x{arena_bgr.shape[0]}"
            )
        fill = np.median(arena_bgr.reshape(-1, 3), axis=0).astype(np.uint8)
        native = np.empty(
            (self.grid.native_height, self.grid.native_width, 3),
            dtype=np.uint8,
        )
        native[:] = fill
        native[
            arena_rect.top:arena_rect.bottom,
            arena_rect.left:arena_rect.right,
        ] = arena_bgr
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
