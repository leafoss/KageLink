from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

import win32api
import win32con
import win32gui

from .config import InputControlPreference
from .windows import (
    GA_ROOT,
    WindowCandidate,
    choose_input_candidate,
    ensure_game_window_foreground,
    input_candidates,
    safe_window_rect,
)


VALID_CHANNELS = {"ooc", "ic"}

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t


class ChatSender:
    def __init__(
        self,
        game_title: str,
        input_class: str,
        preferences: dict[str, InputControlPreference],
        min_interval_seconds: float,
    ) -> None:
        self.game_title = game_title
        self.input_class = input_class
        self.preferences = preferences
        self.min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._last_send_at = 0.0

    @staticmethod
    def _channel(channel: str) -> str:
        normalized = str(channel or "ooc").strip().lower()
        if normalized not in VALID_CHANNELS:
            raise ValueError("INVALID_CHANNEL")
        return normalized

    def preference(self, channel: str) -> InputControlPreference:
        return self.preferences[self._channel(channel)]

    def update_preference(self, channel: str, preference: InputControlPreference) -> None:
        self.preferences[self._channel(channel)] = preference

    @staticmethod
    def _normalized_center(
        game_hwnd: int,
        candidate: WindowCandidate,
    ) -> tuple[float, float] | None:
        """Returns the candidate center relative to the main game window.

        The Shinobi layout has two independent Edit controls:
        - IC/RP in the lower center;
        - OOC in the lower-right corner.

        HWND values are temporary, so geometry is the stable distinction.
        """

        game_left, game_top, game_right, game_bottom = safe_window_rect(game_hwnd)
        game_width = max(0, game_right - game_left)
        game_height = max(0, game_bottom - game_top)
        if game_width <= 0 or game_height <= 0:
            return None

        center_x = candidate.left + (candidate.width / 2.0)
        center_y = candidate.top + (candidate.height / 2.0)
        return (
            (center_x - game_left) / float(game_width),
            (center_y - game_top) / float(game_height),
        )

    def _channel_region_candidates(
        self,
        game_hwnd: int,
        candidates: list[WindowCandidate],
        channel: str,
        excluded_hwnds: set[int] | None = None,
    ) -> list[WindowCandidate]:
        """Keeps each chat destination inside its own screen region.

        This intentionally prevents a saved OOC preference from resolving to
        the center IC/RP field, or an IC preference from resolving to the
        lower-right OOC field.
        """

        excluded = excluded_hwnds or set()
        same_game_root = [
            item
            for item in candidates
            if item.hwnd not in excluded and item.root == game_hwnd
        ]
        if not same_game_root:
            same_game_root = [item for item in candidates if item.hwnd not in excluded]

        bottom_candidates: list[WindowCandidate] = []
        region_candidates: list[WindowCandidate] = []
        for item in same_game_root:
            normalized = self._normalized_center(game_hwnd, item)
            if normalized is None:
                continue
            x, y = normalized
            if y < 0.52:
                continue
            bottom_candidates.append(item)

            if channel == "ooc":
                # The OOC input is in the lower-right portion of the game.
                if x >= 0.62:
                    region_candidates.append(item)
            else:
                # The IC/RP input is centered along the lower edge.
                if 0.20 <= x <= 0.62:
                    region_candidates.append(item)

        return region_candidates or bottom_candidates or same_game_root

    def _geometry_choice(
        self,
        game_hwnd: int,
        candidates: list[WindowCandidate],
        channel: str,
    ) -> WindowCandidate | None:
        if not candidates:
            return None

        target_x = 0.84 if channel == "ooc" else 0.50
        target_y = 0.91
        reference_index = 4 if channel == "ooc" else 2

        def score(item: WindowCandidate) -> tuple[float, int, int]:
            normalized = self._normalized_center(game_hwnd, item)
            if normalized is None:
                return float("inf"), 1, -item.area
            x, y = normalized
            geometry_distance = abs(x - target_x) * 10_000 + abs(y - target_y) * 5_000
            index_penalty = 0 if item.index == reference_index else 1
            return geometry_distance, index_penalty, -item.area

        return min(candidates, key=score)

    def _locate_channel_from_scan(
        self,
        game_hwnd: int,
        candidates: list[WindowCandidate],
        channel: str,
        excluded_hwnds: set[int] | None = None,
    ) -> WindowCandidate | None:
        safe_channel = self._channel(channel)
        preference = self.preference(safe_channel)
        channel_candidates = self._channel_region_candidates(
            game_hwnd,
            candidates,
            safe_channel,
            excluded_hwnds,
        )
        if not channel_candidates:
            return None

        # Position-based calibration is safe only after the candidate has
        # already passed the channel-specific screen-region filter.
        calibrated = (
            preference.relative_left is not None
            and preference.relative_top is not None
        ) or bool(preference.parent_class)
        if calibrated:
            selected = choose_input_candidate(
                channel_candidates,
                preference.preferred_width,
                preference.preferred_height,
                preference.relative_left,
                preference.relative_top,
                preference.candidate_index,
                preference.parent_class,
            )
            if selected is not None:
                return selected

        # Detector indices 002 (IC) and 004 (OOC) are useful references, but
        # geometry remains authoritative because HWND/order can change.
        reference_index = 4 if safe_channel == "ooc" else 2
        indexed = next(
            (item for item in channel_candidates if item.index == reference_index),
            None,
        )
        if indexed is not None:
            return indexed

        return self._geometry_choice(game_hwnd, channel_candidates, safe_channel)

    def locate_ooc(self) -> tuple[int | None, WindowCandidate | None]:
        game_hwnd, candidates = input_candidates(self.game_title, self.input_class)
        if game_hwnd is None:
            return None, None
        return game_hwnd, self._locate_channel_from_scan(
            game_hwnd,
            candidates,
            "ooc",
        )

    def locate_ic(self) -> tuple[int | None, WindowCandidate | None]:
        game_hwnd, candidates = input_candidates(self.game_title, self.input_class)
        if game_hwnd is None:
            return None, None
        ooc_input = self._locate_channel_from_scan(game_hwnd, candidates, "ooc")
        excluded = {ooc_input.hwnd} if ooc_input is not None else set()
        return game_hwnd, self._locate_channel_from_scan(
            game_hwnd,
            candidates,
            "ic",
            excluded,
        )

    def locate(self, channel: str = "ooc") -> tuple[int | None, WindowCandidate | None]:
        return self.locate_ic() if self._channel(channel) == "ic" else self.locate_ooc()

    def locate_channels(self) -> tuple[int | None, dict[str, WindowCandidate | None]]:
        game_hwnd, candidates = input_candidates(self.game_title, self.input_class)
        if game_hwnd is None:
            return None, {"ooc": None, "ic": None}

        # OOC and IC are located independently by their actual screen regions.
        ooc_input = self._locate_channel_from_scan(game_hwnd, candidates, "ooc")
        excluded = {ooc_input.hwnd} if ooc_input is not None else set()
        ic_input = self._locate_channel_from_scan(
            game_hwnd,
            candidates,
            "ic",
            excluded,
        )
        return game_hwnd, {"ooc": ooc_input, "ic": ic_input}

    def send_ooc(self, message: str) -> dict:
        return self._send_to_channel(message, "ooc")

    def send_ic(self, message: str) -> dict:
        return self._send_to_channel(message, "ic")

    def send(self, message: str, channel: str = "ooc") -> dict:
        # Backward-compatible dispatcher for existing web/API clients.
        return self.send_ic(message) if self._channel(channel) == "ic" else self.send_ooc(message)

    def _send_to_channel(self, message: str, channel: str) -> dict:
        safe_channel = self._channel(channel)
        cleaned = message.replace("\r", " ").replace("\n", " ").strip()
        if not cleaned:
            raise ValueError("EMPTY_MESSAGE")

        with self._lock:
            elapsed = time.monotonic() - self._last_send_at
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)

            focus = ensure_game_window_foreground(self.game_title)
            if not focus.window_found:
                raise RuntimeError("GAME_NOT_FOUND")
            if not focus.foreground_confirmed:
                raise RuntimeError("FOREGROUND_FAILED")

            # Locate again after restore/focus because BYOND can recreate controls.
            if safe_channel == "ooc":
                game_hwnd, input_control = self.locate_ooc()
            else:
                game_hwnd, input_control = self.locate_ic()

            if game_hwnd is None:
                raise RuntimeError("GAME_NOT_FOUND")
            if input_control is None:
                raise RuntimeError(f"{safe_channel.upper()}_INPUT_NOT_FOUND")

            self._write_text(input_control.hwnd, cleaned)
            self._click_and_press_enter(game_hwnd, input_control.hwnd)
            self._last_send_at = time.monotonic()

            return {
                "ok": True,
                "message": cleaned,
                "channel": safe_channel,
                "input": input_control.to_dict(),
                "focus": focus.to_dict(),
            }

    @staticmethod
    def _write_text(input_hwnd: int, message: str) -> None:
        buffer = ctypes.create_unicode_buffer(message)
        accepted = user32.SendMessageW(
            input_hwnd,
            win32con.WM_SETTEXT,
            0,
            ctypes.addressof(buffer),
        )
        if not accepted:
            raise RuntimeError("GAME_INPUT_WRITE_FAILED")

        written_length = int(
            user32.SendMessageW(input_hwnd, win32con.WM_GETTEXTLENGTH, 0, 0)
        )
        if written_length < len(message):
            empty = ctypes.create_unicode_buffer("")
            user32.SendMessageW(
                input_hwnd,
                win32con.WM_SETTEXT,
                0,
                ctypes.addressof(empty),
            )
            raise RuntimeError("GAME_INPUT_TRUNCATED")
        time.sleep(0.15)

    @staticmethod
    def _click_and_press_enter(game_hwnd: int, input_hwnd: int) -> None:
        if not win32gui.IsWindow(input_hwnd):
            raise RuntimeError("INPUT_NOT_FOUND")
        root_hwnd = int(user32.GetAncestor(input_hwnd, GA_ROOT) or 0) or game_hwnd
        if not win32gui.IsWindow(root_hwnd):
            raise RuntimeError("GAME_NOT_FOUND")

        old_mouse_position = win32api.GetCursorPos()
        try:
            left, top, right, bottom = win32gui.GetWindowRect(input_hwnd)
            if right <= left or bottom <= top:
                raise RuntimeError("INPUT_INVALID_RECT")
            center = ((left + right) // 2, (top + bottom) // 2)
            win32api.SetCursorPos(center)
            time.sleep(0.10)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.20)
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            time.sleep(0.08)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.30)
        finally:
            try:
                win32api.SetCursorPos(old_mouse_position)
            except Exception:
                pass
