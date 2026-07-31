from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..mapping.sparse_map import SparseTileMap
from ..models import CellState, Point
from .command_verifier import MovementCommandResolution, MovementCommandVerifier
from .motion import MotionSample, PhaseCorrelationMotionEstimator
from .tile_odometry import TileOdometry, TileOdometryUpdate


@dataclass(slots=True)
class MappingSnapshot:
    frame_index: int
    raw_frame: Any
    processed_frame: Any
    motion: MotionSample
    odometry: TileOdometryUpdate | None
    map_ascii: str
    command_resolution: MovementCommandResolution | None = None
    pending_direction: str | None = None
    mapping_strategy: str = "input"


class MappingObserverEngine:
    def __init__(
        self,
        region_id: str,
        tile_size_px: int = 64,
        camera_mode: str = "following",
        map_radius: int = 10,
        min_motion_response: float = 0.18,
        invert_x: bool = False,
        invert_y: bool = False,
        mapping_strategy: str = "input",
        command_timeout_seconds: float = 0.70,
        min_command_shift_px: float = 2.0,
    ) -> None:
        if mapping_strategy not in {"input", "continuous"}:
            raise ValueError("mapping_strategy must be input or continuous")
        self.region_map = SparseTileMap(region_id, tile_size_px)
        self.odometry = TileOdometry(
            tile_size_px,
            camera_mode,
            invert_x=invert_x,
            invert_y=invert_y,
            min_confidence=min_motion_response,
        )
        self.estimator = PhaseCorrelationMotionEstimator(min_response=min_motion_response)
        self.verifier = MovementCommandVerifier(
            camera_mode=camera_mode,
            timeout_seconds=command_timeout_seconds,
            min_shift_px=min_command_shift_px,
            min_response=min_motion_response,
            invert_x=invert_x,
            invert_y=invert_y,
        )
        self.mapping_strategy = mapping_strategy
        self.map_radius = map_radius
        self.frame_index = 0
        self.previous_frame: Any | None = None
        self.command_baseline_frame: Any | None = None
        self.last_resolution: MovementCommandResolution | None = None

    def begin_movement(self, direction: str, baseline_frame: Any, started_at: float | None = None) -> bool:
        """Register one user movement-key attempt without sending any input."""
        if self.mapping_strategy != "input" or baseline_frame is None:
            return False
        accepted = self.verifier.begin(direction, time.perf_counter() if started_at is None else started_at)
        if accepted:
            self.command_baseline_frame = baseline_frame.copy()
        return accepted

    def process_frame(self, frame: Any, now: float | None = None) -> MappingSnapshot:
        import cv2

        observed_at = time.perf_counter() if now is None else float(now)
        self.frame_index += 1
        if self.previous_frame is None:
            self.previous_frame = frame.copy()
            motion = MotionSample.baseline()
            processed = self._annotate(frame.copy(), motion, None, cv2)
            return MappingSnapshot(
                self.frame_index,
                frame,
                processed,
                motion,
                None,
                self.region_map.render_ascii(self.map_radius),
                pending_direction=self._pending_direction(),
                mapping_strategy=self.mapping_strategy,
            )

        consecutive_motion = self.estimator.estimate(self.previous_frame, frame)
        self.previous_frame = frame.copy()
        displayed_motion = consecutive_motion
        odometry: TileOdometryUpdate | None = None
        resolution: MovementCommandResolution | None = None

        if self.mapping_strategy == "continuous":
            if consecutive_motion.accepted:
                odometry = self.odometry.update(
                    consecutive_motion.screen_dx_px,
                    consecutive_motion.screen_dy_px,
                    consecutive_motion.response,
                )
                if odometry.traversed:
                    self.region_map.mark_path(list(odometry.traversed), confidence=consecutive_motion.response)
                self.region_map.set_current_position(odometry.position, consecutive_motion.response)
        elif self.verifier.pending is not None and self.command_baseline_frame is not None:
            displayed_motion = self.estimator.estimate(self.command_baseline_frame, frame)
            resolution = self.verifier.observe(displayed_motion, observed_at)
            if resolution is not None:
                self._apply_resolution(resolution)
                self.command_baseline_frame = None
                self.last_resolution = resolution

        processed = self._annotate(frame.copy(), displayed_motion, odometry, cv2)
        return MappingSnapshot(
            self.frame_index,
            frame,
            processed,
            displayed_motion,
            odometry,
            self.region_map.render_ascii(self.map_radius),
            command_resolution=resolution,
            pending_direction=self._pending_direction(),
            mapping_strategy=self.mapping_strategy,
        )

    def reset(self) -> None:
        region_id = self.region_map.region_id
        tile_size = self.region_map.tile_size_px
        self.region_map = SparseTileMap(region_id, tile_size)
        self.odometry.reset()
        self.verifier.cancel()
        self.command_baseline_frame = None
        self.last_resolution = None
        self.previous_frame = None
        self.frame_index = 0

    def restore_state(self, payload: dict) -> None:
        restored_map = SparseTileMap.from_dict(payload["mapping"])
        if restored_map.tile_size_px != self.odometry.tile_size_px:
            raise ValueError("Saved map tile size does not match the requested tile size")
        self.region_map = restored_map
        self.odometry.restore(payload.get("odometry", {}))
        self.odometry.position = self.region_map.current_position
        self.region_map.set_current_position(self.odometry.position)
        self.frame_index = int(payload.get("frame_index", 0))
        self.previous_frame = None
        self.command_baseline_frame = None
        self.verifier.cancel()

    def export_state(self) -> dict:
        return {
            "schema_version": 2,
            "mapping_strategy": self.mapping_strategy,
            "mapping": self.region_map.to_dict(),
            "odometry": self.odometry.to_dict(),
            "frame_index": self.frame_index,
        }

    def _pending_direction(self) -> str | None:
        return self.verifier.pending.direction if self.verifier.pending is not None else None

    def _apply_resolution(self, resolution: MovementCommandResolution) -> None:
        current = self.region_map.current_position
        target = Point(
            current.x + resolution.world_delta.x,
            current.y + resolution.world_delta.y,
        )
        if resolution.moved:
            self.region_map.mark_visited(target, confidence=1.0, label=f"input:{resolution.direction}")
            self.region_map.set_current_position(target, confidence=1.0)
            self.odometry.position = target
            self.odometry.residual_x_px = 0.0
            self.odometry.residual_y_px = 0.0
            self.odometry.total_world_x_px = float(target.x * self.odometry.tile_size_px)
            self.odometry.total_world_y_px = float(target.y * self.odometry.tile_size_px)
        else:
            self.region_map.observe(
                target,
                CellState.BLOCKED,
                confidence=max(0.80, resolution.response),
                label=f"blocked_input:{resolution.direction}",
            )

    def _annotate(self, frame: Any, motion: MotionSample, odometry: TileOdometryUpdate | None, cv2: Any) -> Any:
        height, width = frame.shape[:2]
        tile = self.region_map.tile_size_px
        center_x, center_y = width // 2, height // 2
        for x in range(center_x % tile, width, tile):
            cv2.line(frame, (x, 0), (x, height), (90, 90, 90), 1)
        for y in range(center_y % tile, height, tile):
            cv2.line(frame, (0, y), (width, y), (90, 90, 90), 1)
        end = (int(center_x + motion.screen_dx_px * 4), int(center_y + motion.screen_dy_px * 4))
        cv2.arrowedLine(frame, (center_x, center_y), end, (255, 255, 255), 2, tipLength=0.25)
        position = odometry.position if odometry else self.region_map.current_position
        pending = self._pending_direction() or "none"
        cv2.putText(
            frame,
            f"screen=({motion.screen_dx_px:+.1f},{motion.screen_dy_px:+.1f}) response={motion.response:.2f}",
            (12, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"tile=({position.x},{position.y}) logical={tile}px strategy={self.mapping_strategy} pending={pending}",
            (12, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return frame
