from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, Any

from .learning import BehaviorCloner, Prediction


class Controller(Protocol):
    def activate(self) -> None: ...
    def apply_keys(self, keys: tuple[str, ...]) -> None: ...
    def release_all(self) -> None: ...
    def tap(self, key: str, duration: float = 0.08) -> None: ...
    def click_normalized(self, x: float, y: float) -> None: ...


@dataclass(frozen=True, slots=True)
class PilotStep:
    prediction: Prediction
    applied_keys: tuple[str, ...]


class Pilot:
    def __init__(
        self,
        model: BehaviorCloner,
        frame_source: Any,
        controller: Controller,
        *,
        min_confidence: float = 0.08,
        decision_hz: float = 10.0,
        base_keys: tuple[str, ...] = (),
        sleep_fn=time.sleep,
    ) -> None:
        self.model = model
        self.frame_source = frame_source
        self.controller = controller
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.decision_hz = max(1.0, min(30.0, float(decision_hz)))
        self.base_keys = tuple(sorted({str(k).strip().lower() for k in base_keys if str(k).strip()}))
        self.sleep_fn = sleep_fn

    def step(self) -> PilotStep:
        frame = self.frame_source.capture()
        prediction = self.model.predict(bytes(frame.jpeg))
        predicted = prediction.keys if prediction.confidence >= self.min_confidence else ()
        keys = tuple(sorted(set(self.base_keys).union(predicted)))
        self.controller.apply_keys(keys)
        return PilotStep(prediction=prediction, applied_keys=keys)

    def run(self, *, seconds: float | None = None) -> int:
        self.controller.activate()
        started = time.monotonic()
        steps = 0
        try:
            while seconds is None or time.monotonic() - started < float(seconds):
                self.step()
                steps += 1
                self.sleep_fn(1.0 / self.decision_hz)
        finally:
            self.controller.release_all()
        return steps


class WindowsGameController:
    def __init__(self) -> None:
        from pc_agent.game_control import GameInputController

        self._controller = GameInputController()

    def activate(self) -> None:
        self._controller.activate()

    def apply_keys(self, keys: tuple[str, ...]) -> None:
        self._controller.apply_state(keys)

    def release_all(self) -> None:
        self._controller.release_all()

    def tap(self, key: str, duration: float = 0.08) -> None:
        self._controller.apply_state((str(key).strip().lower(),))
        time.sleep(max(0.01, float(duration)))
        self._controller.apply_state(())

    def click_normalized(self, x: float, y: float) -> None:
        from pc_agent.game_control import _send_left_click
        from pc_agent.game_window import locate_capture_target
        from pc_agent.windows import ensure_game_window_foreground

        x_value = float(x)
        y_value = float(y)
        if not 0.0 <= x_value <= 1.0 or not 0.0 <= y_value <= 1.0:
            raise ValueError("NORMALIZED_COORDINATE_OUT_OF_RANGE")
        target = locate_capture_target(self._controller.title)
        if target is None or target.minimized:
            raise RuntimeError("GAME_UNAVAILABLE")
        focus = ensure_game_window_foreground(self._controller.title)
        if not focus.ok:
            raise RuntimeError(focus.error or "FOREGROUND_FAILED")
        screen_x = target.left + round(x_value * max(0, target.width - 1))
        screen_y = target.top + round(y_value * max(0, target.height - 1))
        _send_left_click(screen_x, screen_y)
