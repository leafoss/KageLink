from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..mapping.sparse_map import SparseTileMap
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
    ) -> None:
        self.region_map = SparseTileMap(region_id, tile_size_px)
        self.odometry = TileOdometry(
            tile_size_px,
            camera_mode,
            invert_x=invert_x,
            invert_y=invert_y,
            min_confidence=min_motion_response,
        )
        self.estimator = PhaseCorrelationMotionEstimator(min_response=min_motion_response)
        self.map_radius = map_radius
        self.frame_index = 0
        self.previous_frame: Any | None = None

    def process_frame(self, frame: Any) -> MappingSnapshot:
        import cv2

        self.frame_index += 1
        if self.previous_frame is None:
            self.previous_frame = frame.copy()
            motion = MotionSample.baseline()
            processed = self._annotate(frame.copy(), motion, None, cv2)
            return MappingSnapshot(self.frame_index, frame, processed, motion, None, self.region_map.render_ascii(self.map_radius))
        motion = self.estimator.estimate(self.previous_frame, frame)
        self.previous_frame = frame.copy()
        odometry = None
        if motion.accepted:
            odometry = self.odometry.update(motion.screen_dx_px, motion.screen_dy_px, motion.response)
            if odometry.traversed:
                self.region_map.mark_path(list(odometry.traversed), confidence=motion.response)
            self.region_map.set_current_position(odometry.position, motion.response)
        processed = self._annotate(frame.copy(), motion, odometry, cv2)
        return MappingSnapshot(self.frame_index, frame, processed, motion, odometry, self.region_map.render_ascii(self.map_radius))

    def reset(self) -> None:
        region_id = self.region_map.region_id
        tile_size = self.region_map.tile_size_px
        self.region_map = SparseTileMap(region_id, tile_size)
        self.odometry.reset()
        self.previous_frame = None
        self.frame_index = 0

    def restore_state(self, payload: dict) -> None:
        restored_map = SparseTileMap.from_dict(payload["mapping"])
        if restored_map.tile_size_px != self.odometry.tile_size_px:
            raise ValueError("Saved map tile size does not match the requested tile size")
        self.region_map = restored_map
        self.odometry.restore(payload.get("odometry", {}))
        self.region_map.set_current_position(self.odometry.position)
        self.frame_index = int(payload.get("frame_index", 0))
        self.previous_frame = None

    def export_state(self) -> dict:
        return {
            "schema_version": 1,
            "mapping": self.region_map.to_dict(),
            "odometry": self.odometry.to_dict(),
            "frame_index": self.frame_index,
        }

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
        position = odometry.position if odometry else self.odometry.position
        cv2.putText(frame, f"screen=({motion.screen_dx_px:+.1f},{motion.screen_dy_px:+.1f}) response={motion.response:.2f}", (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"tile=({position.x},{position.y}) size={tile}px", (12, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
        return frame
