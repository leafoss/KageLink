from __future__ import annotations

import ctypes
from dataclasses import dataclass
import math
import time


VK_F12 = 0x7B
LB_GETCOUNT = 0x018B
LB_GETCURSEL = 0x0188
LB_SETCURSEL = 0x0186


@dataclass(frozen=True, slots=True)
class DojoDialogMatch:
    dialog_hwnd: int
    listbox_hwnd: int
    selected_index: int
    item_count: int


@dataclass(frozen=True, slots=True)
class TrainerClickTarget:
    normalized_x: float
    normalized_y: float
    score: float
    grid_distance: int
    bbox: tuple[int, int, int, int]


class DojoFightRequestError(RuntimeError):
    pass


def f12_pressed() -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_F12) & 0x8000)
    except Exception:
        return False


def _interruptible_wait(seconds: float, *, interval: float = 0.05) -> None:
    deadline = time.monotonic() + max(0.0, float(seconds))
    while time.monotonic() < deadline:
        if f12_pressed():
            raise DojoFightRequestError("F12_STOP")
        time.sleep(min(max(0.01, float(interval)), max(0.0, deadline - time.monotonic())))


def find_dojo_dialog(game_title: str) -> DojoDialogMatch | None:
    """Find the visible NPC choice dialog by process + #32770 + ListBox identity."""

    import win32gui
    import win32process

    from pc_agent.game_window import find_exact_game_window
    from pc_agent.windows import descendants, process_top_windows, window_area

    game_hwnd = find_exact_game_window(game_title)
    if game_hwnd is None:
        return None
    _, game_pid = win32process.GetWindowThreadProcessId(game_hwnd)

    candidates: list[tuple[int, DojoDialogMatch]] = []
    for top_hwnd in process_top_windows(game_pid):
        try:
            if top_hwnd == game_hwnd or not win32gui.IsWindowVisible(top_hwnd):
                continue
            top_class = win32gui.GetClassName(top_hwnd).casefold()
            if top_class != "#32770":
                continue
            area = window_area(top_hwnd)
            if area < 20_000 or area > 500_000:
                continue

            for child in descendants(top_hwnd):
                try:
                    if win32gui.GetClassName(child).casefold() != "listbox":
                        continue
                    if not win32gui.IsWindowVisible(child) or not win32gui.IsWindowEnabled(child):
                        continue
                    left, top, right, bottom = win32gui.GetWindowRect(child)
                    width = max(0, right - left)
                    height = max(0, bottom - top)
                    if width < 180 or height < 70:
                        continue
                    item_count = int(win32gui.SendMessage(child, LB_GETCOUNT, 0, 0))
                    selected = int(win32gui.SendMessage(child, LB_GETCURSEL, 0, 0))
                    # The supplied Taijutsu dialog has Spar, Advanced Match and Cancel.
                    if item_count < 3:
                        continue
                    score = 10_000
                    if not win32gui.GetWindowText(top_hwnd).strip():
                        score += 1_000
                    if selected == 0:
                        score += 500
                    score += min(500, area // 500)
                    candidates.append(
                        (
                            score,
                            DojoDialogMatch(
                                dialog_hwnd=int(top_hwnd),
                                listbox_hwnd=int(child),
                                selected_index=selected,
                                item_count=item_count,
                            ),
                        )
                    )
                except (win32gui.error, OSError):
                    continue
        except (win32gui.error, OSError):
            continue

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def wait_for_dojo_dialog(game_title: str, *, timeout_seconds: float = 10.0) -> DojoDialogMatch:
    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    while time.monotonic() < deadline:
        if f12_pressed():
            raise DojoFightRequestError("F12_STOP")
        match = find_dojo_dialog(game_title)
        if match is not None:
            return match
        time.sleep(0.05)
    raise DojoFightRequestError("DOJO_DIALOG_NOT_FOUND")


def confirm_first_dojo_option(match: DojoDialogMatch, *, close_timeout_seconds: float = 3.0) -> None:
    """Keep option zero selected and deliver the user's requested Enter key."""

    import win32api
    import win32con
    import win32gui

    if not win32gui.IsWindow(match.dialog_hwnd) or not win32gui.IsWindow(match.listbox_hwnd):
        raise DojoFightRequestError("DOJO_DIALOG_LOST")

    win32gui.SendMessage(match.listbox_hwnd, LB_SETCURSEL, 0, 0)
    selected = int(win32gui.SendMessage(match.listbox_hwnd, LB_GETCURSEL, 0, 0))
    if selected != 0:
        raise DojoFightRequestError(f"DOJO_OPTION_SELECTION_FAILED:{selected}")

    try:
        win32gui.BringWindowToTop(match.dialog_hwnd)
        win32gui.SetForegroundWindow(match.dialog_hwnd)
    except win32gui.error as error:
        raise DojoFightRequestError(f"DOJO_DIALOG_FOCUS_FAILED:{error}") from error

    time.sleep(0.10)
    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

    deadline = time.monotonic() + max(0.5, float(close_timeout_seconds))
    while time.monotonic() < deadline:
        if not win32gui.IsWindow(match.dialog_hwnd) or not win32gui.IsWindowVisible(match.dialog_hwnd):
            return
        if f12_pressed():
            raise DojoFightRequestError("F12_STOP")
        time.sleep(0.05)
    raise DojoFightRequestError("DOJO_DIALOG_DID_NOT_CLOSE")


def locate_adjacent_trainer(*, leader_threshold: float = 0.88) -> TrainerClickTarget:
    """Capture once, require an authoritative visual trainer match and verify adjacency."""

    from pc_agent.kage_pilot.entity_observer import decode_jpeg
    from pc_agent.kage_pilot.grid_target_observer_v03 import _grid_distance
    from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
    from pc_agent.kage_pilot.particle_safe_grid_target_v03 import ParticleSafeGridTargetObserver
    from pc_agent.kage_pilot.post_combat_v03c import PersistentDojoLeaderDetector
    from pc_agent.kage_pilot.recorder import WindowsGameFrameSource

    config = V03ObserverConfig(
        player_x=0.5181,
        player_y=0.4706,
        player_exclusion_radius=19.0,
        player_box_width=18.0,
        player_box_height=38.0,
        dynamic_background_enabled=True,
    ).normalized()
    observer = ParticleSafeGridTargetObserver(
        config,
        tile_size=32.0,
        contact_lock_seconds=2.8,
        show_grid=False,
        contact_confirm_frames=2,
    )
    detector = PersistentDojoLeaderDetector(threshold=leader_threshold)
    source = WindowsGameFrameSource()
    try:
        frame = decode_jpeg(bytes(source.capture().jpeg))
        state = observer.process(frame)
        match = detector.find(frame, arena_rect=state.arena_rect, now=time.monotonic())
        if match is None or match.source != "visual":
            raise DojoFightRequestError("TRAINER_NOT_VISUALLY_CONFIRMED")

        x0, y0, _, _ = state.arena_rect
        player_full = (
            float(x0) + float(state.player_center[0]),
            float(y0) + float(state.player_center[1]),
        )
        size = float(observer.tile_size)
        origin_x, origin_y = observer.grid_origin

        def cell(point):
            return (
                math.floor((float(point[0]) - origin_x) / size),
                math.floor((float(point[1]) - origin_y) / size),
            )

        distance = _grid_distance(cell(player_full), cell(match.foot))
        if distance > 1:
            raise DojoFightRequestError(f"TRAINER_NOT_ADJACENT:d={distance}")

        left, top, width, height = match.bbox
        click_x = float(left) + float(width) * 0.50
        click_y = float(top) + float(height) * 0.48
        normalized_x = max(0.0, min(1.0, click_x / max(1.0, frame.shape[1] - 1.0)))
        normalized_y = max(0.0, min(1.0, click_y / max(1.0, frame.shape[0] - 1.0)))
        return TrainerClickTarget(
            normalized_x=normalized_x,
            normalized_y=normalized_y,
            score=float(match.score),
            grid_distance=distance,
            bbox=match.bbox,
        )
    finally:
        source.close()


def _close_owned_controller(controller) -> None:
    try:
        controller.release_all()
    except Exception:
        pass
    stop = getattr(controller, "_repeat_stop", None)
    if stop is not None:
        stop.set()
    thread = getattr(controller, "_repeat_thread", None)
    if thread is not None and thread.is_alive():
        thread.join(timeout=0.25)
    core = getattr(controller, "_controller", None)
    if core is not None and hasattr(core, "deactivate"):
        try:
            core.deactivate()
        except Exception:
            pass


def request_taijutsu_dojo_spar(
    game_title: str,
    *,
    dialog_delay_seconds: float = 10.0,
    dialog_find_timeout_seconds: float = 4.0,
    spawn_delay_seconds: float = 5.0,
    leader_threshold: float = 0.88,
    controller=None,
) -> TrainerClickTarget:
    """Click trainer once, wait, confirm selected first option with Enter, then wait for spawn."""

    from pc_agent.kage_pilot.pilot import WindowsGameController
    from pc_agent.windows import ensure_game_window_foreground

    click_target = locate_adjacent_trainer(leader_threshold=leader_threshold)
    owns_controller = controller is None
    controller = controller or WindowsGameController(recover_foreground=False)
    controller.repeat_keys = set()
    try:
        controller.activate()
        controller.release_all()
        clicked_at = time.monotonic()
        controller.click_normalized(click_target.normalized_x, click_target.normalized_y)
        controller.release_all()

        # Discover the dialog early while measuring the requested delay from the actual click.
        dialog = wait_for_dojo_dialog(game_title, timeout_seconds=dialog_find_timeout_seconds)
        elapsed = time.monotonic() - clicked_at
        _interruptible_wait(max(0.0, float(dialog_delay_seconds) - elapsed))

        refreshed = find_dojo_dialog(game_title)
        confirm_first_dojo_option(refreshed or dialog)

        focus = ensure_game_window_foreground(game_title)
        if not focus.ok:
            raise DojoFightRequestError(focus.error or "GAME_REFOCUS_FAILED")
        _interruptible_wait(spawn_delay_seconds)
        return click_target
    finally:
        controller.release_all()
        if owns_controller:
            _close_owned_controller(controller)


__all__ = [
    "DojoDialogMatch",
    "DojoFightRequestError",
    "TrainerClickTarget",
    "confirm_first_dojo_option",
    "f12_pressed",
    "find_dojo_dialog",
    "locate_adjacent_trainer",
    "request_taijutsu_dojo_spar",
    "wait_for_dojo_dialog",
]
