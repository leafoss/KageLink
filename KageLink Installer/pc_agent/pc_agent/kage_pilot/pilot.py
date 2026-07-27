from __future__ import annotations

import ctypes
import threading
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
    """Safe Windows controller used by Kage Pilot.

    Legacy callers keep strict normal key-state behavior by default. Kage Pilot
    v0.2 can additionally mark one or more keys as BYOND repeat-held keys.

    Shinobi Story Online's combat R binding was verified on real hardware to
    require the pattern produced by a physically held repeating key: one
    scan-code KEYDOWN, an initial repeat delay, repeated KEYDOWN events while
    the key remains logically down, and one final KEYUP. Those repeats run on a
    small daemon worker so visual inference frequency does not control combat
    repeat frequency.
    """

    def __init__(
        self,
        *,
        recover_foreground: bool = False,
        debug: bool = False,
        repeat_delay_seconds: float = 0.35,
        repeat_interval_seconds: float = 0.05,
    ) -> None:
        from pc_agent.game_control import GameInputController

        self._controller = GameInputController()
        self.recover_foreground = bool(recover_foreground)
        self.debug = bool(debug)

        # Public configuration used by TemporalCombatPilot. Empty by default so
        # legacy v0.1 behavior remains unchanged.
        self.repeat_keys: set[str] = set()
        self.repeat_delay_seconds = max(0.05, float(repeat_delay_seconds))
        self.repeat_interval_seconds = max(0.01, float(repeat_interval_seconds))

        self._repeat_lock = threading.RLock()
        self._repeat_pressed: set[str] = set()
        self._repeat_next_at: dict[str, float] = {}
        self._repeat_stop = threading.Event()
        self._repeat_thread = threading.Thread(
            target=self._repeat_loop,
            name="kage-pilot-byond-repeat",
            daemon=True,
        )
        self._repeat_thread.start()

    def _focus_exact_game(self) -> None:
        from pc_agent.windows import ensure_game_window_foreground, is_game_window_foreground
        from pc_agent.game_window import find_exact_game_window

        focus = ensure_game_window_foreground(self._controller.title)
        if not focus.ok:
            raise RuntimeError(focus.error or "FOREGROUND_FAILED")
        hwnd = find_exact_game_window(self._controller.title)
        if hwnd is None or not is_game_window_foreground(hwnd):
            raise RuntimeError("FOREGROUND_FAILED")

    def activate(self) -> None:
        self._controller.activate()
        try:
            self._focus_exact_game()
        except Exception:
            self._controller.deactivate()
            raise

    @staticmethod
    def _scan_code_for_key(key: str) -> int:
        from ctypes import wintypes
        from pc_agent.game_control import KEYS, _user32

        normalized = str(key).strip().lower()
        definition = KEYS.get(normalized)
        if definition is None:
            raise RuntimeError(f"UNKNOWN_REPEAT_KEY:{normalized}")

        # MAPVK_VK_TO_VSC = 0. Letter R resolves to scan code 0x13 on the
        # user's Windows keyboard, matching the successful real-game test.
        if not hasattr(_user32, "MapVirtualKeyW"):
            raise RuntimeError("MAP_VIRTUAL_KEY_UNAVAILABLE")
        _user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
        _user32.MapVirtualKeyW.restype = wintypes.UINT
        scan_code = int(_user32.MapVirtualKeyW(definition.vk, 0))
        if not scan_code:
            raise RuntimeError(f"SCAN_CODE_NOT_FOUND:{normalized}")
        return scan_code

    @classmethod
    def _send_repeat_scan(cls, key: str, *, down: bool) -> None:
        from pc_agent.game_control import (
            INPUT,
            INPUT_KEYBOARD,
            INPUT_UNION,
            KEYBDINPUT,
            _user32,
        )

        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_SCANCODE = 0x0008
        flags = KEYEVENTF_SCANCODE
        if not down:
            flags |= KEYEVENTF_KEYUP
        event = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=0,
                    wScan=cls._scan_code_for_key(key),
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())

    def _release_repeat_locked(self, keys: set[str] | None = None) -> None:
        targets = set(self._repeat_pressed if keys is None else keys.intersection(self._repeat_pressed))
        for key in sorted(targets):
            try:
                self._send_repeat_scan(key, down=False)
            except Exception:
                pass
            self._repeat_pressed.discard(key)
            self._repeat_next_at.pop(key, None)

    def _repeat_loop(self) -> None:
        from pc_agent.game_window import find_exact_game_window
        from pc_agent.windows import is_game_window_foreground

        while not self._repeat_stop.wait(0.01):
            with self._repeat_lock:
                if not self._repeat_pressed:
                    continue

                hwnd = find_exact_game_window(self._controller.title)
                if hwnd is None or not is_game_window_foreground(hwnd):
                    # Never leave a synthetic held key behind when foreground is
                    # lost. The next normal apply_keys call may safely recover
                    # focus and press it again.
                    self._release_repeat_locked()
                    continue

                now = time.monotonic()
                for key in sorted(self._repeat_pressed):
                    if now < self._repeat_next_at.get(key, now):
                        continue
                    try:
                        self._send_repeat_scan(key, down=True)
                    except Exception:
                        self._release_repeat_locked({key})
                        continue
                    self._repeat_next_at[key] = now + self.repeat_interval_seconds

    def _recover_focus(self) -> None:
        # Repeat-held keys are not tracked by GameInputController, so release
        # them explicitly before using the core controller's recovery path.
        with self._repeat_lock:
            self._release_repeat_locked()
        self._controller.deactivate()
        self._focus_exact_game()
        self._controller.activate()
        if self.debug:
            print("V0.2 focus=recovered / foco=recuperado")

    def apply_keys(self, keys: tuple[str, ...]) -> None:
        from pc_agent.game_control import GameControlError
        from pc_agent.game_window import find_exact_game_window
        from pc_agent.windows import is_game_window_foreground

        desired = {str(key).strip().lower() for key in keys if str(key).strip()}
        repeat_desired = desired.intersection({str(key).strip().lower() for key in self.repeat_keys})
        normal_desired = tuple(sorted(desired.difference(repeat_desired)))

        if self.recover_foreground:
            hwnd = find_exact_game_window(self._controller.title)
            if hwnd is not None and not is_game_window_foreground(hwnd):
                self._recover_focus()

        try:
            self._controller.apply_state(normal_desired)
        except GameControlError as error:
            if not self.recover_foreground or str(error) != "FOREGROUND_LOST":
                raise
            self._recover_focus()
            self._controller.apply_state(normal_desired)

        with self._repeat_lock:
            self._release_repeat_locked(self._repeat_pressed.difference(repeat_desired))
            now = time.monotonic()
            for key in sorted(repeat_desired.difference(self._repeat_pressed)):
                self._send_repeat_scan(key, down=True)
                self._repeat_pressed.add(key)
                self._repeat_next_at[key] = now + self.repeat_delay_seconds
                if self.debug:
                    print(
                        f"V0.2 repeat_hold={key} delay={self.repeat_delay_seconds:.2f}s "
                        f"interval={self.repeat_interval_seconds:.2f}s"
                    )

    def release_all(self) -> None:
        with self._repeat_lock:
            self._release_repeat_locked()
        self._controller.release_all()

    def tap(self, key: str, duration: float = 0.08) -> None:
        normalized = str(key).strip().lower()
        self.apply_keys((normalized,))
        time.sleep(max(0.01, float(duration)))
        self.apply_keys(())

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
