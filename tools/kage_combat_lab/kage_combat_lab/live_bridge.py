from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .domain import (
    CELL_SIZE_PX,
    H_PULSE_MS,
    POST_PULSE_OBSERVE_MS,
    CandidateObservation,
    CombatDecision,
    CombatFrame,
    GridCell,
    ObservationKind,
    TargetState,
    require_canonical_cell_size,
)


AIM_PULSE_MS = 50


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _cell_for_point(point: tuple[float, float]) -> GridCell:
    require_canonical_cell_size(CELL_SIZE_PX)
    return GridCell(
        math.floor(float(point[0]) / CELL_SIZE_PX),
        math.floor(float(point[1]) / CELL_SIZE_PX),
    )


def _bbox_cells(bbox: tuple[int, int, int, int]) -> frozenset[GridCell]:
    left, top, width, height = bbox
    right = max(left, left + max(1, width) - 1)
    bottom = max(top, top + max(1, height) - 1)
    return frozenset(
        GridCell(x, y)
        for x in range(math.floor(left / CELL_SIZE_PX), math.floor(right / CELL_SIZE_PX) + 1)
        for y in range(math.floor(top / CELL_SIZE_PX), math.floor(bottom / CELL_SIZE_PX) + 1)
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
) -> CombatFrame:
    """Translate KageLink vision into the neutral PR25 combat domain.

    Visual track ids remain evidence only. Identity stays owned by GridFocusStrategy.
    Every clean body is anchored exclusively by its feet into one immutable 64px cell.
    """

    now = time.monotonic() if timestamp_seconds is None else float(timestamp_seconds)
    player_point = (float(state.player_center[0]), float(state.player_center[1]))
    player_cell = _cell_for_point(player_point)
    candidates: list[CandidateObservation] = []
    tracker: _Tracker = observer.tracker

    for track in tuple(state.tracks):
        context = tracker.context_for(int(track.track_id))
        visible = str(getattr(context, "state", "")).upper() == "VISIBLE"
        left, top, width, height = (int(value) for value in track.bbox)
        foot = (float(left) + float(width) * 0.5, float(top) + float(height))
        anchor_cell = _cell_for_point(foot)
        covered = _bbox_cells((left, top, width, height))
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

        hint = _face_hint(player_point, foot) if anchor_cell == player_cell and visible else None
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
    """Execute CombatDecision using the proven KageLink Windows controller."""

    def __init__(
        self,
        controller: InputController,
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
        aim_pulse_ms: int = AIM_PULSE_MS,
    ) -> None:
        self.controller = controller
        self.sleep_fn = sleep_fn
        self.aim_pulse_ms = max(20, min(100, int(aim_pulse_ms)))
        self._active = False

    def activate(self) -> None:
        self.controller.repeat_keys = {"r"}
        self.controller.activate()
        self.controller.release_all()
        self._active = True

    def start_combat_hold(self) -> None:
        if not self._active:
            raise RuntimeError("LIVE_INPUT_NOT_ACTIVE")
        self.controller.apply_keys(("r",))

    def _apply_base(self) -> None:
        self.controller.apply_keys(("r",))

    def _pulse(self, key: str, duration_ms: int) -> None:
        normalized = str(key).strip().lower()
        self.controller.apply_keys(tuple(sorted({"r", normalized})))
        self.sleep_fn(max(0.01, float(duration_ms) / 1000.0))
        self._apply_base()

    def execute(self, decision: CombatDecision) -> tuple[str, ...]:
        if not self._active:
            raise RuntimeError("LIVE_INPUT_NOT_ACTIVE")
        if not decision.hold_r or decision.target_state is TargetState.ENDED:
            self.controller.release_all()
            return ("RELEASE_ALL",)

        actions: list[str] = []
        self._apply_base()

        # D0/D1 already encode their directional correction as the movement pulse.
        # Ranged H shots aim first, tap H, then perform any approach pulse.
        if decision.press_h:
            if decision.face is None:
                raise RuntimeError("H_REQUIRES_CARDINAL_AIM")
            self._pulse(decision.face, self.aim_pulse_ms)
            actions.append(f"AIM_{decision.face}_{self.aim_pulse_ms}MS")
            self._pulse("h", decision.h_pulse_ms or H_PULSE_MS)
            actions.append(f"H_{decision.h_pulse_ms or H_PULSE_MS}MS")

        if decision.move is not None and decision.move_pulse_profile is not None:
            duration = decision.move_pulse_ms or decision.move_pulse_profile.duration_ms
            self._pulse(decision.move, duration)
            actions.append(f"MOVE_{decision.move.upper()}_{duration}MS")

        if actions:
            observe_ms = max(0, int(decision.post_pulse_observe_ms or POST_PULSE_OBSERVE_MS))
            if observe_ms:
                self.sleep_fn(float(observe_ms) / 1000.0)
                actions.append(f"OBSERVE_{observe_ms}MS")
        return tuple(actions)

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
