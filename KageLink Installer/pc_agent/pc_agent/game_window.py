from __future__ import annotations

from dataclasses import asdict, dataclass

import win32con
import win32gui

from pc_agent.game_protocol import GAME_WINDOW_TITLE
from pc_agent.windows import descendants


_EXCLUDED_CLASSES = {
    "button",
    "edit",
    "richedit",
    "richedit20a",
    "richedit20w",
    "richedit50w",
    "static",
    "combobox",
    "listbox",
    "scrollbar",
    "mdiclient",
    "systabcontrol32",
    "toolbarwindow32",
}
_PREFERRED_CLASS_HINTS = ("byond", "dream", "map", "render", "pane")


@dataclass(frozen=True, slots=True)
class CaptureTarget:
    game_hwnd: int
    capture_hwnd: int
    title: str
    class_name: str
    left: int
    top: int
    width: int
    height: int
    minimized: bool
    source_kind: str

    def to_dict(self) -> dict:
        return asdict(self)


def _exact_title_match(actual: str, expected: str) -> bool:
    return actual.strip().casefold() == expected.strip().casefold()


def find_exact_game_window(title: str = GAME_WINDOW_TITLE) -> int | None:
    matches: list[tuple[int, int]] = []

    def callback(hwnd: int, _: object) -> bool:
        try:
            if not win32gui.IsWindow(hwnd):
                return True
            actual = win32gui.GetWindowText(hwnd)
            if not _exact_title_match(actual, title):
                return True
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            area = max(0, right - left) * max(0, bottom - top)
            matches.append((area, int(hwnd)))
        except win32gui.error:
            pass
        return True

    win32gui.EnumWindows(callback, None)
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]


def _client_screen_rect(hwnd: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    screen_left, screen_top = win32gui.ClientToScreen(hwnd, (left, top))
    screen_right, screen_bottom = win32gui.ClientToScreen(hwnd, (right, bottom))
    return screen_left, screen_top, screen_right, screen_bottom


def _child_candidate(game_hwnd: int) -> tuple[int, str] | None:
    root_left, root_top, root_right, root_bottom = _client_screen_rect(game_hwnd)
    root_width = max(1, root_right - root_left)
    root_height = max(1, root_bottom - root_top)
    root_area = root_width * root_height
    candidates: list[tuple[int, int, int, str]] = []

    for child in descendants(game_hwnd):
        try:
            if not win32gui.IsWindowVisible(child):
                continue
            class_name = win32gui.GetClassName(child)
            lowered = class_name.casefold()
            if lowered in _EXCLUDED_CLASSES or lowered.startswith("richedit"):
                continue
            left, top, right, bottom = _client_screen_rect(child)
            width = max(0, right - left)
            height = max(0, bottom - top)
            area = width * height
            if width < 320 or height < 220 or area < root_area * 0.20:
                continue
            if left < root_left - 4 or top < root_top - 4:
                continue
            if right > root_right + 4 or bottom > root_bottom + 4:
                continue

            score = area
            if any(hint in lowered for hint in _PREFERRED_CLASS_HINTS):
                score += root_area * 2
            # The playfield is usually in the upper/central part of the BYOND client.
            vertical_offset = max(0, top - root_top)
            score -= vertical_offset * max(1, width // 3)
            candidates.append((score, area, int(child), class_name))
        except (win32gui.error, OSError):
            continue

    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, _, hwnd, class_name = candidates[0]
    return hwnd, class_name


def locate_capture_target(title: str = GAME_WINDOW_TITLE) -> CaptureTarget | None:
    game_hwnd = find_exact_game_window(title)
    if game_hwnd is None:
        return None

    minimized = bool(win32gui.IsIconic(game_hwnd))
    selected = _child_candidate(game_hwnd)
    capture_hwnd = selected[0] if selected else game_hwnd
    class_name = selected[1] if selected else win32gui.GetClassName(game_hwnd)
    source_kind = "render_child" if selected else "client_area"

    left, top, right, bottom = _client_screen_rect(capture_hwnd)
    width = max(0, right - left)
    height = max(0, bottom - top)
    if width <= 0 or height <= 0:
        return None

    return CaptureTarget(
        game_hwnd=int(game_hwnd),
        capture_hwnd=int(capture_hwnd),
        title=win32gui.GetWindowText(game_hwnd),
        class_name=class_name,
        left=left,
        top=top,
        width=width,
        height=height,
        minimized=minimized,
        source_kind=source_kind,
    )


def is_valid_game_target(hwnd: int, title: str = GAME_WINDOW_TITLE) -> bool:
    try:
        return bool(
            hwnd
            and win32gui.IsWindow(hwnd)
            and _exact_title_match(win32gui.GetWindowText(hwnd), title)
        )
    except win32gui.error:
        return False


def show_state(hwnd: int) -> str:
    if not hwnd or not win32gui.IsWindow(hwnd):
        return "missing"
    if win32gui.IsIconic(hwnd):
        return "minimized"
    placement = win32gui.GetWindowPlacement(hwnd)
    if placement and placement[1] == win32con.SW_SHOWMAXIMIZED:
        return "maximized"
    return "normal"
