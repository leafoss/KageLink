from __future__ import annotations

from dataclasses import asdict, dataclass

import win32gui
import win32process

from pc_agent.game_protocol import GAME_WINDOW_TITLE
from pc_agent.game_window import find_exact_game_window
from pc_agent.stats_protocol import STATS_WINDOW_CLASS, STATS_WINDOW_TITLE


@dataclass(frozen=True, slots=True)
class StatsTarget:
    game_hwnd: int
    hwnd: int
    process_id: int
    title: str
    class_name: str
    left: int
    top: int
    width: int
    height: int
    minimized: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _exact_match(actual: str, expected: str) -> bool:
    return actual.strip().casefold() == expected.strip().casefold()


def _process_id(hwnd: int) -> int:
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return int(pid)


def _client_screen_rect(hwnd: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    screen_left, screen_top = win32gui.ClientToScreen(hwnd, (left, top))
    screen_right, screen_bottom = win32gui.ClientToScreen(hwnd, (right, bottom))
    return screen_left, screen_top, screen_right, screen_bottom


def find_stats_window(
    game_title: str = GAME_WINDOW_TITLE,
    *,
    stats_title: str = STATS_WINDOW_TITLE,
    stats_class: str = STATS_WINDOW_CLASS,
) -> tuple[int, int, int] | None:
    game_hwnd = find_exact_game_window(game_title)
    if game_hwnd is None:
        return None
    try:
        game_pid = _process_id(game_hwnd)
    except (win32gui.error, OSError):
        return None

    matches: list[tuple[int, int]] = []

    def callback(hwnd: int, _: object) -> bool:
        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return True
            if _process_id(hwnd) != game_pid:
                return True
            if not _exact_match(win32gui.GetWindowText(hwnd), stats_title):
                return True
            if not _exact_match(win32gui.GetClassName(hwnd), stats_class):
                return True
            left, top, right, bottom = _client_screen_rect(hwnd)
            area = max(0, right - left) * max(0, bottom - top)
            if area > 0:
                matches.append((area, int(hwnd)))
        except (win32gui.error, OSError):
            pass
        return True

    win32gui.EnumWindows(callback, None)
    if not matches:
        return None
    matches.sort(reverse=True)
    return int(game_hwnd), matches[0][1], game_pid


def locate_stats_target(
    game_title: str = GAME_WINDOW_TITLE,
    *,
    stats_title: str = STATS_WINDOW_TITLE,
    stats_class: str = STATS_WINDOW_CLASS,
) -> StatsTarget | None:
    found = find_stats_window(
        game_title,
        stats_title=stats_title,
        stats_class=stats_class,
    )
    if found is None:
        return None
    game_hwnd, hwnd, pid = found
    try:
        left, top, right, bottom = _client_screen_rect(hwnd)
        width = max(0, right - left)
        height = max(0, bottom - top)
        if width <= 0 or height <= 0:
            return None
        return StatsTarget(
            game_hwnd=game_hwnd,
            hwnd=hwnd,
            process_id=pid,
            title=win32gui.GetWindowText(hwnd),
            class_name=win32gui.GetClassName(hwnd),
            left=left,
            top=top,
            width=width,
            height=height,
            minimized=bool(win32gui.IsIconic(hwnd)),
        )
    except (win32gui.error, OSError):
        return None


def is_valid_stats_target(
    hwnd: int,
    expected_pid: int,
    *,
    stats_title: str = STATS_WINDOW_TITLE,
    stats_class: str = STATS_WINDOW_CLASS,
) -> bool:
    try:
        return bool(
            hwnd
            and win32gui.IsWindow(hwnd)
            and _process_id(hwnd) == expected_pid
            and _exact_match(win32gui.GetWindowText(hwnd), stats_title)
            and _exact_match(win32gui.GetClassName(hwnd), stats_class)
        )
    except (win32gui.error, OSError):
        return False
