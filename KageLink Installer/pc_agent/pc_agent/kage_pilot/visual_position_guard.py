from __future__ import annotations

from .visual_position_v351 import PositionState, VisualPositionTracker


def install_visual_position_guard() -> None:
    """Keep LOST coordinates frozen until explicit relocalization or anchor reset.

    Continuous local motion after a teleport can still be observed and logged, but it cannot
    restore an absolute X/Y because the relation to the Trainer origin is unknown.
    """

    if bool(getattr(VisualPositionTracker, "_kagelink_lost_guard", False)):
        return
    original_observe = VisualPositionTracker.observe

    def guarded_observe(self, frame_bgr, observer_state, *, commanded_direction=None):
        if not self.anchored or self.state != PositionState.LOST:
            return original_observe(
                self,
                frame_bgr,
                observer_state,
                commanded_direction=commanded_direction,
            )

        if commanded_direction is not None:
            self.note_command(commanded_direction)
        estimate = self.odometry.observe(frame_bgr, observer_state)
        self._emit(
            "DOJO_VISUAL_MOTION",
            dx_px=f"{estimate.dx_pixels:.3f}",
            dy_px=f"{estimate.dy_pixels:.3f}",
            dx_cells=f"{estimate.dx_cells:.4f}",
            dy_cells=f"{estimate.dy_cells:.4f}",
            confidence=f"{estimate.confidence:.3f}",
        )
        self.confidence = min(self.confidence, max(0.0, estimate.confidence))
        self.state = PositionState.LOST
        self._emit(
            "DOJO_POSITION_REMAINS_LOST",
            dx_local=f"{estimate.dx_cells:.4f}",
            dy_local=f"{estimate.dy_cells:.4f}",
            confidence=f"{estimate.confidence:.3f}",
            reason="absolute origin relation unavailable",
        )
        if self._last_command:
            self._emit(
                "DOJO_MOVE_OBSERVED_POSITION_LOST",
                direction=self._last_command,
                dx_local=f"{estimate.dx_cells:.4f}",
                dy_local=f"{estimate.dy_cells:.4f}",
            )
        self._last_command = None
        self._last_position_before_command = None
        return estimate

    VisualPositionTracker.observe = guarded_observe
    VisualPositionTracker._kagelink_lost_guard = True


__all__ = ["install_visual_position_guard"]
