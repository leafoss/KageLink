from __future__ import annotations

import ctypes
import re
import time
from dataclasses import asdict, dataclass
from ctypes import wintypes

import win32api
import win32con
import win32gui
import win32process


GA_ROOT = 2
ES_READONLY = 0x0800
ERROR_ALREADY_EXISTS = 183

DEFAULT_CHAT_CLASS = "RICHEDIT50W"
DEFAULT_INPUT_CLASS = "Edit"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


@dataclass(slots=True)
class WindowCandidate:
    hwnd: int
    class_name: str
    title: str
    left: int
    top: int
    width: int
    height: int
    visible: bool
    enabled: bool
    readonly: bool
    parent: int
    root: int
    relative_left: int
    relative_top: int
    parent_class: str
    index: int = 0

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_dict(self) -> dict:
        result = asdict(self)
        result["area"] = self.area
        return result


@dataclass(slots=True)
class ForegroundResult:
    ok: bool
    window_found: bool
    restored: bool
    brought_to_front: bool
    foreground_confirmed: bool
    hwnd: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def safe_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    try:
        return win32gui.GetWindowRect(hwnd)
    except win32gui.error:
        return 0, 0, 0, 0


def window_area(hwnd: int) -> int:
    left, top, right, bottom = safe_window_rect(hwnd)
    return max(0, right - left) * max(0, bottom - top)


def describe_window(hwnd: int) -> WindowCandidate | None:
    if not hwnd or not win32gui.IsWindow(hwnd):
        return None
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        parent = int(win32gui.GetParent(hwnd) or 0)
        root = int(user32.GetAncestor(hwnd, GA_ROOT) or 0)
        root_left, root_top, _, _ = safe_window_rect(root)
        try:
            parent_class = win32gui.GetClassName(parent) if parent else ""
        except win32gui.error:
            parent_class = ""
        return WindowCandidate(
            hwnd=int(hwnd),
            class_name=win32gui.GetClassName(hwnd),
            title=win32gui.GetWindowText(hwnd),
            left=left,
            top=top,
            width=max(0, right - left),
            height=max(0, bottom - top),
            visible=bool(win32gui.IsWindowVisible(hwnd)),
            enabled=bool(win32gui.IsWindowEnabled(hwnd)),
            readonly=bool(style & ES_READONLY),
            parent=parent,
            root=root,
            relative_left=left - root_left,
            relative_top=top - root_top,
            parent_class=parent_class,
        )
    except win32gui.error:
        return None


def _normalize_title(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _title_tokens(value: str) -> set[str]:
    ignored = {"the", "game", "client", "online"}
    return {
        token
        for token in _normalize_title(value).split()
        if len(token) >= 3 and token not in ignored
    }


def _top_level_windows() -> list[int]:
    result: list[int] = []

    def callback(hwnd: int, _: object) -> bool:
        try:
            if win32gui.IsWindow(hwnd):
                result.append(hwnd)
        except win32gui.error:
            pass
        return True

    win32gui.EnumWindows(callback, None)
    return result


def descendants(parent_hwnd: int) -> list[int]:
    result: list[int] = []

    def callback(hwnd: int, _: object) -> bool:
        result.append(hwnd)
        return True

    try:
        win32gui.EnumChildWindows(parent_hwnd, callback, None)
    except win32gui.error:
        pass
    return result


def _child_class_names(hwnd: int) -> set[str]:
    classes: set[str] = set()
    for child in descendants(hwnd):
        try:
            classes.add(win32gui.GetClassName(child).casefold())
        except win32gui.error:
            pass
    return classes


def _candidate_score(hwnd: int, title_fragment: str) -> int:
    try:
        title = win32gui.GetWindowText(hwnd)
        title_normalized = _normalize_title(title)
        fragment_normalized = _normalize_title(title_fragment)
        tokens = _title_tokens(title_fragment)
        classes = _child_class_names(hwnd)
        visible = bool(win32gui.IsWindowVisible(hwnd))
        area = window_area(hwnd)

        score = 0
        if fragment_normalized and fragment_normalized in title_normalized:
            score += 100_000
        if tokens and tokens.issubset(set(title_normalized.split())):
            score += 40_000
        if "shinobi" in title_normalized:
            score += 25_000
        if "byond" in title_normalized:
            score += 5_000

        has_chat = DEFAULT_CHAT_CLASS.casefold() in classes
        has_input = DEFAULT_INPUT_CLASS.casefold() in classes
        if has_chat:
            score += 35_000
        if has_input:
            score += 10_000
        if has_chat and has_input:
            score += 80_000

        if visible:
            score += 1_000
        score += min(area // 10_000, 1_000)
        return score
    except Exception:
        return 0


def find_game_window(title_fragment: str) -> int | None:
    candidates: list[tuple[int, int, int]] = []

    for hwnd in _top_level_windows():
        score = _candidate_score(hwnd, title_fragment)
        if score <= 0:
            continue
        candidates.append((score, window_area(hwnd), hwnd))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    best_score, _, best_hwnd = candidates[0]

    # Require either a meaningful title match or the characteristic
    # RICHEDIT50W + Edit control pair. This avoids random false positives.
    if best_score < 25_000:
        return None
    return best_hwnd


def window_scan_snapshot(title_fragment: str, limit: int = 30) -> list[dict]:
    snapshot: list[dict] = []
    for hwnd in _top_level_windows():
        info = describe_window(hwnd)
        if info is None:
            continue
        classes = sorted(_child_class_names(hwnd))
        score = _candidate_score(hwnd, title_fragment)
        if not info.title and not classes:
            continue
        snapshot.append(
            {
                "hwnd": info.hwnd,
                "title": info.title,
                "class_name": info.class_name,
                "visible": info.visible,
                "width": info.width,
                "height": info.height,
                "score": score,
                "child_classes": classes[:40],
            }
        )
    snapshot.sort(key=lambda item: (item["score"], item["width"] * item["height"]), reverse=True)
    return snapshot[:limit]


def is_game_window_foreground(game_hwnd: int | None) -> bool:
    if not game_hwnd or not win32gui.IsWindow(game_hwnd):
        return False
    foreground = int(user32.GetForegroundWindow() or 0)
    if not foreground:
        return False
    root = int(user32.GetAncestor(foreground, GA_ROOT) or foreground)
    game_root = int(user32.GetAncestor(game_hwnd, GA_ROOT) or game_hwnd)
    return root == game_root


def _thread_id(hwnd: int) -> int:
    if not hwnd:
        return 0
    return int(user32.GetWindowThreadProcessId(hwnd, None) or 0)


def ensure_game_window_foreground(title_fragment: str) -> ForegroundResult:
    game_hwnd = find_game_window(title_fragment)
    if game_hwnd is None:
        return ForegroundResult(False, False, False, False, False, error="GAME_NOT_FOUND")

    root_hwnd = int(user32.GetAncestor(game_hwnd, GA_ROOT) or game_hwnd)
    restored = False
    try:
        if not win32gui.IsWindowVisible(root_hwnd):
            win32gui.ShowWindow(root_hwnd, win32con.SW_SHOW)
            restored = True
            time.sleep(0.15)
        if win32gui.IsIconic(root_hwnd):
            win32gui.ShowWindow(root_hwnd, win32con.SW_RESTORE)
            restored = True
            time.sleep(0.35)

        if is_game_window_foreground(root_hwnd):
            return ForegroundResult(True, True, restored, True, True, hwnd=root_hwnd)

        try:
            win32gui.BringWindowToTop(root_hwnd)
            win32gui.SetForegroundWindow(root_hwnd)
            time.sleep(0.18)
        except win32gui.error:
            pass

        if not is_game_window_foreground(root_hwnd):
            try:
                win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                win32api.keybd_event(
                    win32con.VK_MENU,
                    0,
                    win32con.KEYEVENTF_KEYUP,
                    0,
                )
                win32gui.BringWindowToTop(root_hwnd)
                win32gui.SetForegroundWindow(root_hwnd)
                time.sleep(0.18)
            except win32gui.error:
                pass

        if not is_game_window_foreground(root_hwnd):
            foreground = int(user32.GetForegroundWindow() or 0)
            current_tid = int(kernel32.GetCurrentThreadId())
            target_tid = _thread_id(root_hwnd)
            foreground_tid = _thread_id(foreground)
            attached: list[tuple[int, int]] = []
            try:
                for source_tid in {current_tid, foreground_tid}:
                    if source_tid and target_tid and source_tid != target_tid:
                        if user32.AttachThreadInput(source_tid, target_tid, True):
                            attached.append((source_tid, target_tid))
                win32gui.ShowWindow(root_hwnd, win32con.SW_RESTORE)
                win32gui.BringWindowToTop(root_hwnd)
                win32gui.SetActiveWindow(root_hwnd)
                win32gui.SetForegroundWindow(root_hwnd)
                time.sleep(0.22)
            finally:
                for source_tid, target_tid in reversed(attached):
                    user32.AttachThreadInput(source_tid, target_tid, False)

        confirmed = is_game_window_foreground(root_hwnd)
        return ForegroundResult(
            ok=confirmed,
            window_found=True,
            restored=restored,
            brought_to_front=confirmed,
            foreground_confirmed=confirmed,
            hwnd=root_hwnd,
            error=None if confirmed else "FOREGROUND_FAILED",
        )
    except Exception as error:
        return ForegroundResult(
            ok=False,
            window_found=True,
            restored=restored,
            brought_to_front=False,
            foreground_confirmed=False,
            hwnd=root_hwnd,
            error=f"FOREGROUND_FAILED: {error}",
        )


def process_top_windows(pid: int) -> list[int]:
    windows: list[int] = []

    def callback(hwnd: int, _: object) -> bool:
        try:
            _, candidate_pid = win32process.GetWindowThreadProcessId(hwnd)
            if candidate_pid == pid:
                windows.append(hwnd)
        except win32gui.error:
            pass
        return True

    win32gui.EnumWindows(callback, None)
    return windows


def _detector_candidate_score(hwnd: int, title_fragment: str) -> int:
    """Reproduces the ordering used by the Shinobi-only detect.py scan.

    The user's ``002_hwnd-...`` reference is a zero-based global index across
    scored top-level windows and each top window's children; it is not the
    second Edit control. Keeping this ordering lets candidate 002 remain a
    useful initial reference while geometry becomes the permanent identity
    after calibration.
    """

    try:
        title = win32gui.GetWindowText(hwnd).casefold()
        class_name = win32gui.GetClassName(hwnd).casefold()
        classes = _child_class_names(hwnd)
        hint = title_fragment.casefold().strip()

        score = 0
        if hint and hint in title:
            score += 100_000
        if "shinobi" in title:
            score += 60_000
        if "dream seeker" in title:
            score += 35_000
        if "byond" in title:
            score += 20_000
        if "byond" in class_name:
            score += 10_000

        has_chat = DEFAULT_CHAT_CLASS.casefold() in classes
        has_input = DEFAULT_INPUT_CLASS.casefold() in classes
        if has_chat:
            score += 60_000
        if has_input:
            score += 20_000
        if has_chat and has_input:
            score += 120_000
        if win32gui.IsWindowVisible(hwnd):
            score += 1_000
        return score
    except Exception:
        return 0


def ordered_process_handles(
    game_hwnd: int,
    title_fragment: str,
) -> list[tuple[int, int]]:
    """Returns ``(detect_index, hwnd)`` in the prior detector's global order."""

    _, pid = win32process.GetWindowThreadProcessId(game_hwnd)
    top_windows = process_top_windows(pid)
    top_windows.sort(
        key=lambda hwnd: (
            _detector_candidate_score(hwnd, title_fragment),
            window_area(hwnd),
            hwnd,
        ),
        reverse=True,
    )

    ordered: list[tuple[int, int]] = []
    seen: set[int] = set()
    global_index = 0
    for top_hwnd in top_windows:
        for hwnd in (top_hwnd, *descendants(top_hwnd)):
            if hwnd in seen:
                continue
            seen.add(hwnd)
            ordered.append((global_index, hwnd))
            global_index += 1
    return ordered


def all_process_handles(game_hwnd: int, title_fragment: str = "") -> list[int]:
    return [hwnd for _, hwnd in ordered_process_handles(game_hwnd, title_fragment)]


def find_controls(title_fragment: str, class_name: str) -> tuple[int | None, list[WindowCandidate]]:
    game_hwnd = find_game_window(title_fragment)
    if game_hwnd is None:
        return None, []

    controls: list[WindowCandidate] = []
    for detect_index, hwnd in ordered_process_handles(game_hwnd, title_fragment):
        try:
            if win32gui.GetClassName(hwnd).casefold() != class_name.casefold():
                continue
        except win32gui.error:
            continue
        info = describe_window(hwnd)
        if info:
            info.index = detect_index
            controls.append(info)
    return game_hwnd, controls


def select_chat_control(title_fragment: str, chat_class: str) -> WindowCandidate | None:
    _, controls = find_controls(title_fragment, chat_class)
    visible = [
        item
        for item in controls
        if item.visible and item.width > 20 and item.height > 20
    ]
    return max(visible, key=lambda item: item.area) if visible else None


def input_candidates(title_fragment: str, input_class: str) -> tuple[int | None, list[WindowCandidate]]:
    game_hwnd, controls = find_controls(title_fragment, input_class)
    candidates = [
        item
        for item in controls
        if item.visible
        and item.enabled
        and item.width > 100
        and 15 <= item.height <= 150
    ]
    # Keep the zero-based global discovery index from detect.py. Candidate
    # numbers may have gaps because non-Edit windows are intentionally omitted.
    return game_hwnd, candidates


def choose_input_candidate(
    candidates: list[WindowCandidate],
    preferred_width: int,
    preferred_height: int,
    relative_left: int | None = None,
    relative_top: int | None = None,
    candidate_index: int | None = None,
    parent_class: str = "",
) -> WindowCandidate | None:
    if not candidates:
        return None

    has_dimensions = preferred_width > 0 and preferred_height > 0
    has_position = relative_left is not None and relative_top is not None
    has_parent = bool(parent_class)

    # Candidate 002 is the safe initial IC reference. Once calibrated, the
    # saved geometry becomes the stronger identifier.
    if candidate_index is not None and not has_dimensions and not has_position and not has_parent:
        return next((item for item in candidates if item.index == candidate_index), None)

    def score(item: WindowCandidate) -> tuple[int, int, int, int]:
        dimension_distance = (
            abs(item.width - preferred_width) + abs(item.height - preferred_height)
            if has_dimensions
            else 0
        )
        position_distance = (
            abs(item.relative_left - int(relative_left))
            + abs(item.relative_top - int(relative_top))
            if has_position
            else 0
        )
        parent_penalty = (
            0 if not has_parent or item.parent_class.casefold() == parent_class.casefold() else 600
        )
        index_penalty = 0 if candidate_index is None or item.index == candidate_index else 120
        total = dimension_distance * 4 + position_distance + parent_penalty + index_penalty
        return total, dimension_distance, position_distance, -item.area

    selected = min(candidates, key=score)

    if has_dimensions:
        width_tolerance = max(80, int(preferred_width * 0.30))
        height_tolerance = max(20, int(preferred_height * 0.60))
        if (
            abs(selected.width - preferred_width) > width_tolerance
            or abs(selected.height - preferred_height) > height_tolerance
        ):
            return None
    if has_position:
        if (
            abs(selected.relative_left - int(relative_left)) > 420
            or abs(selected.relative_top - int(relative_top)) > 260
        ):
            return None
    if has_parent and selected.parent_class.casefold() != parent_class.casefold():
        return None

    return selected


def select_input_control(
    title_fragment: str,
    input_class: str,
    preferred_width: int,
    preferred_height: int,
    relative_left: int | None = None,
    relative_top: int | None = None,
    candidate_index: int | None = None,
    parent_class: str = "",
) -> tuple[int | None, WindowCandidate | None]:
    game_hwnd, candidates = input_candidates(title_fragment, input_class)
    return game_hwnd, choose_input_candidate(
        candidates,
        preferred_width,
        preferred_height,
        relative_left,
        relative_top,
        candidate_index,
        parent_class,
    )
