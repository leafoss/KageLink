from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .domain import (
    CELL_SIZE_PX,
    H_PULSE_MS,
    POST_OK_SETTLE_MS,
    POST_PULSE_OBSERVE_MS,
    START_RIGHT_PULSE_MS,
    START_RIGHT_SETTLE_MS,
    TURN_PRE_RELEASE_MS,
    TURN_PULSE_MS,
    TURN_SETTLE_MS,
    CandidateObservation,
    CombatDecision,
    CombatFrame,
    GridCell,
    ObservationKind,
    TargetState,
    require_canonical_cell_size,
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _cell_for_point(
    point: tuple[float, float],
    *,
    origin: tuple[float, float] = (0.0, 0.0),
) -> GridCell:
    require_canonical_cell_size(CELL_SIZE_PX)
    return GridCell(
        math.floor((float(point[0]) - float(origin[0])) / CELL_SIZE_PX),
        math.floor((float(point[1]) - float(origin[1])) / CELL_SIZE_PX),
    )


def _bbox_cells(
    bbox: tuple[int, int, int, int],
    *,
    origin: tuple[float, float] = (0.0, 0.0),
) -> frozenset[GridCell]:
    left, top, width, height = bbox
    right = max(left, left + max(1, width) - 1)
    bottom = max(top, top + max(1, height) - 1)
    start = _cell_for_point((left, top), origin=origin)
    end = _cell_for_point((right, bottom), origin=origin)
    return frozenset(
        GridCell(x, y)
        for x in range(start.x, end.x + 1)
        for y in range(start.y, end.y + 1)
    )


def _face_hint(
    player_point: tuple[float, float],
    target_point: tuple[float, float],
) -> str | None:
    dx = float(target_point[0]) - float(player_point[0])
    dy = float(target_point[1]) - float(player_point[1])
    if max(abs(dx), abs(dy)) < 4.0:
        return None
    if abs(dx) >= abs(dy):
        return "RIGHT" if dx > 0 else "LEFT"
    return "DOWN" if dy > 0 else "UP"


@dataclass(frozen=True, slots=True)
class LiveVisionPolicy:
    minimum_enemy_score: float = 55.0
    minimum_observations: int = 2
    minimum_shape_score: float = 0.18
    minimum_width: int = 6
    maximum_width: int = 96
    minimum_height: int = 14
    maximum_height: int = 192
    minimum_aspect: float = 0.45
    maximum_aspect: float = 5.5
    maximum_clean_bbox_cells: int = 4


DEFAULT_LIVE_VISION_POLICY = LiveVisionPolicy()


class _TrackerContext(Protocol):
    state: str


class _Tracker(Protocol):
    def context_for(self, track_id: int) -> _TrackerContext: ...


def _body_like(track: Any, policy: LiveVisionPolicy) -> bool:
    _, _, width, height = track.bbox
    width = max(1, int(width))
    height = max(1, int(height))
    aspect = float(height) / float(width)
    return (
        int(getattr(track, "observations", 0)) >= policy.minimum_observations
        and float(getattr(track, "enemy_score", 0.0)) >= policy.minimum_enemy_score
        and float(getattr(track, "shape_score", 0.0)) >= policy.minimum_shape_score
        and policy.minimum_width <= width <= policy.maximum_width
        and policy.minimum_height <= height <= policy.maximum_height
        and policy.minimum_aspect <= aspect <= policy.maximum_aspect
    )


def combat_frame_from_observer_state(
    *,
    observer: Any,
    state: Any,
    frame_index: int,
    timestamp_seconds: float | None = None,
    ko_confirmed: bool = False,
    policy: LiveVisionPolicy = DEFAULT_LIVE_VISION_POLICY,
    frame_bgr: Any | None = None,
    target_memory: Any | None = None,
) -> CombatFrame:
    now = time.monotonic() if timestamp_seconds is None else float(timestamp_seconds)
    player_point = (float(state.player_center[0]), float(state.player_center[1]))
    raw_origin = getattr(observer, "grid_origin", (0.0, 0.0))
    origin = (float(raw_origin[0]), float(raw_origin[1]))
    player_cell = _cell_for_point(player_point, origin=origin)
    candidates: list[CandidateObservation] = []
    tracker: _Tracker = observer.tracker

    for track in tuple(state.tracks):
        context = tracker.context_for(int(track.track_id))
        visible = str(getattr(context, "state", "")).upper() == "VISIBLE"
        left, top, width, height = (int(value) for value in track.bbox)
        foot = (float(left) + float(width) * 0.5, float(top) + float(height))
        anchor_cell = _cell_for_point(foot, origin=origin)
        covered = _bbox_cells((left, top, width, height), origin=origin)
        plausible_body = visible and _body_like(track, policy)
        clearly_multicell = (
            width > policy.maximum_width
            or height > policy.maximum_height
            or len(covered) > policy.maximum_clean_bbox_cells
        )

        if plausible_body and not clearly_multicell:
            kind = ObservationKind.CLEAN_BODY
            cells_touched = frozenset({anchor_cell})
        elif clearly_multicell:
            kind = ObservationKind.MULTI_CELL_BLOB
            cells_touched = covered
        else:
            kind = ObservationKind.CONTAMINATED_ACTIVITY
            cells_touched = covered or frozenset({anchor_cell})

        relative_offset = (
            float(foot[0]) - float(player_point[0]),
            float(foot[1]) - float(player_point[1]),
        )
        hint = _face_hint(player_point, foot) if anchor_cell == player_cell and visible else None
        residual_speed = float(getattr(track, "residual_speed", 0.0) or 0.0)
        motion_score = _clamp01(0.45 + min(0.55, residual_speed / 80.0))
        candidates.append(
            CandidateObservation(
                track_id=int(track.track_id),
                anchor_cell=anchor_cell,
                kind=kind,
                visible=visible,
                body_like=plausible_body,
                confidence=_clamp01(float(getattr(track, "enemy_score", 0.0)) / 100.0),
                cells_touched=cells_touched,
                face_hint=hint,
                bbox=(left, top, width, height),
                foot_point=foot,
                relative_offset_px=relative_offset,
                motion_score=motion_score,
            )
        )

    if target_memory is not None and frame_bgr is not None:
        candidates = list(
            target_memory.enrich_candidates(
                frame_bgr=frame_bgr,
                state=state,
                candidates=candidates,
                timestamp=now,
            )
        )

    return CombatFrame.from_iterable(
        frame_index,
        player_cell,
        candidates,
        ko_confirmed=ko_confirmed,
        timestamp_seconds=now,
    )


class InputController(Protocol):
    repeat_keys: set[str]

    def activate(self) -> None: ...
    def apply_keys(self, keys: tuple[str, ...]) -> None: ...
    def release_all(self) -> None: ...


class PhysicalCombatInput:
    """Execute only actions already authorized by the facing state machine."""

    def __init__(
        self,
        controller: InputController,
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.controller = controller
        self.sleep_fn = sleep_fn
        self._active = False

    def activate(self) -> None:
        self.controller.repeat_keys = {"r"}
        self.controller.activate()
        self.controller.release_all()
        self._active = True

    def start_combat_hold(self) -> None:
        """Compatibility helper; FullLoop no longer calls this before target lock."""
        if not self._active:
            raise RuntimeError("LIVE_INPUT_NOT_ACTIVE")
        self.controller.apply_keys(("r",))

    def _apply_base(self) -> None:
        self.controller.apply_keys(("r",))

    def _pulse_with_r(self, key: str, duration_ms: int) -> None:
        normalized = str(key).strip().lower()
        self.controller.apply_keys(tuple(sorted({"r", normalized})))
        self.sleep_fn(max(0.01, float(duration_ms) / 1000.0))
        self._apply_base()

    def startup_face_right(
        self,
        *,
        post_ok_settle_ms: int = POST_OK_SETTLE_MS,
        pulse_ms: int = START_RIGHT_PULSE_MS,
        settle_ms: int = START_RIGHT_SETTLE_MS,
    ) -> tuple[str, ...]:
        if not self._active:
            raise RuntimeError("LIVE_INPUT_NOT_ACTIVE")
        actions: list[str] = []
        self.controller.release_all()
        try:
            self.sleep_fn(max(0.0, float(post_ok_settle_ms) / 1000.0))
            actions.append(f"POST_OK_SETTLE_{int(post_ok_settle_ms)}MS")
            self.controller.apply_keys(("right",))
            self.sleep_fn(max(0.01, float(pulse_ms) / 1000.0))
            actions.append(f"STARTUP_RIGHT_PULSE_{int(pulse_ms)}MS")
        finally:
            self.controller.release_all()
        self.sleep_fn(max(0.0, float(settle_ms) / 1000.0))
        actions.append(f"STARTUP_RIGHT_SETTLE_{int(settle_ms)}MS")
        return tuple(actions)

    def execute_turn(
        self,
        direction: str,
        *,
        pre_release_ms: int = TURN_PRE_RELEASE_MS,
        pulse_ms: int = TURN_PULSE_MS,
        settle_ms: int = TURN_SETTLE_MS,
    ) -> tuple[str, ...]:
        if not self._active:
            raise RuntimeError("LIVE_INPUT_NOT_ACTIVE")
        normalized = str(direction).strip().lower()
        if normalized not in {"left", "right", "up", "down"}:
            raise ValueError(f"TURN_DIRECTION_INVALID:{direction!r}")
        actions: list[str] = []
        self.controller.release_all()
        try:
            self.sleep_fn(max(0.0, float(pre_release_ms) / 1000.0))
            actions.append(f"TURN_PRE_RELEASE_{int(pre_release_ms)}MS")
            self.controller.apply_keys((normalized,))
            self.sleep_fn(max(0.01, float(pulse_ms) / 1000.0))
            actions.append(f"TURN_{normalized.upper()}_{int(pulse_ms)}MS")
        finally:
            self.controller.release_all()
        self.sleep_fn(max(0.0, float(settle_ms) / 1000.0))
        actions.append(f"TURN_SETTLE_{int(settle_ms)}MS")
        return tuple(actions)

    def execute(self, decision: CombatDecision) -> tuple[str, ...]:
        if not self._active:
            raise RuntimeError("LIVE_INPUT_NOT_ACTIVE")
        if (
            decision.target_state is TargetState.ENDED
            or not decision.hold_r
            or not decision.r_authorized
        ):
            self.controller.release_all()
            return ("RELEASE_ALL", "WAIT_FOR_TARGET_OR_ALIGNMENT")

        actions: list[str] = []
        self._apply_base()
        actions.append("R_AUTHORIZED")

        if decision.press_h:
            if not decision.h_authorized:
                actions.append("H_SKIPPED_NOT_AUTHORIZED")
            else:
                self._pulse_with_r("h", decision.h_pulse_ms or H_PULSE_MS)
                actions.append(f"H_{decision.h_pulse_ms or H_PULSE_MS}MS")

        if decision.move is not None and decision.move_pulse_profile is not None:
            duration = decision.move_pulse_ms or decision.move_pulse_profile.duration_ms
            self._pulse_with_r(decision.move, duration)
            actions.append(f"MOVE_{decision.move.upper()}_{duration}MS")

        if len(actions) > 1:
            observe_ms = max(0, int(decision.post_pulse_observe_ms or POST_PULSE_OBSERVE_MS))
            if observe_ms:
                self.sleep_fn(float(observe_ms) / 1000.0)
                actions.append(f"OBSERVE_{observe_ms}MS")
        return tuple(actions)

    @staticmethod
    def h_fired(actions: tuple[str, ...]) -> bool:
        return any(
            action.startswith("H_") and not action.startswith("H_SKIPPED")
            for action in actions
        )

    def shutdown(self) -> None:
        try:
            self.controller.release_all()
        finally:
            stop = getattr(self.controller, "_repeat_stop", None)
            if stop is not None:
                stop.set()
            thread = getattr(self.controller, "_repeat_thread", None)
            if thread is not None and thread.is_alive():
                thread.join(timeout=0.5)
            try:
                self.controller.release_all()
            except Exception:
                pass
            core = getattr(self.controller, "_controller", None)
            if core is not None and hasattr(core, "deactivate"):
                try:
                    core.deactivate()
                except Exception:
                    pass
            self._active = False
