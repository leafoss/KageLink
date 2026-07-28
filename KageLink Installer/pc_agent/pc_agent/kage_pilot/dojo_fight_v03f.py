from __future__ import annotations

from dataclasses import dataclass
import math
import time

from .dojo_fight_v03e import (
    DojoFightRequestError,
    TrainerClickTarget,
    _close_owned_controller,
    _interruptible_wait,
    f12_pressed,
)
from .post_combat_v03e import ObstacleAwarePostCombatRecoveryEngine


LB_GETCOUNT = 0x018B
LB_GETCURSEL = 0x0188
LB_SETCURSEL = 0x0186
BM_CLICK = 0x00F5


@dataclass(frozen=True, slots=True)
class DojoDialogMatchV2:
    dialog_hwnd: int
    listbox_hwnd: int
    ok_button_hwnd: int
    selected_index: int
    item_count: int


def find_dojo_dialog_with_ok(game_title: str) -> DojoDialogMatchV2 | None:
    """Find the NPC #32770 dialog and its ListBox + visible Button 'OK'."""

    import win32gui
    import win32process

    from pc_agent.game_window import find_exact_game_window
    from pc_agent.windows import descendants, process_top_windows, window_area

    game_hwnd = find_exact_game_window(game_title)
    if game_hwnd is None:
        return None
    _, game_pid = win32process.GetWindowThreadProcessId(game_hwnd)

    candidates: list[tuple[int, DojoDialogMatchV2]] = []
    for top_hwnd in process_top_windows(game_pid):
        try:
            if top_hwnd == game_hwnd or not win32gui.IsWindowVisible(top_hwnd):
                continue
            if win32gui.GetClassName(top_hwnd).casefold() != "#32770":
                continue
            area = window_area(top_hwnd)
            if area < 20_000 or area > 500_000:
                continue

            listbox_hwnd = None
            ok_button_hwnd = None
            selected = -1
            item_count = 0
            for child in descendants(top_hwnd):
                try:
                    class_name = win32gui.GetClassName(child).casefold()
                    if class_name == "listbox":
                        if not win32gui.IsWindowVisible(child) or not win32gui.IsWindowEnabled(child):
                            continue
                        left, top, right, bottom = win32gui.GetWindowRect(child)
                        if max(0, right - left) < 180 or max(0, bottom - top) < 70:
                            continue
                        count = int(win32gui.SendMessage(child, LB_GETCOUNT, 0, 0))
                        if count >= 3:
                            listbox_hwnd = int(child)
                            item_count = count
                            selected = int(win32gui.SendMessage(child, LB_GETCURSEL, 0, 0))
                    elif class_name == "button":
                        text = win32gui.GetWindowText(child).strip().casefold()
                        if text == "ok" and win32gui.IsWindowVisible(child) and win32gui.IsWindowEnabled(child):
                            ok_button_hwnd = int(child)
                except (win32gui.error, OSError):
                    continue

            if listbox_hwnd is None or ok_button_hwnd is None:
                continue
            score = 10_000
            if selected == 0:
                score += 500
            if not win32gui.GetWindowText(top_hwnd).strip():
                score += 250
            candidates.append(
                (
                    score,
                    DojoDialogMatchV2(
                        dialog_hwnd=int(top_hwnd),
                        listbox_hwnd=listbox_hwnd,
                        ok_button_hwnd=ok_button_hwnd,
                        selected_index=selected,
                        item_count=item_count,
                    ),
                )
            )
        except (win32gui.error, OSError):
            continue

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def wait_for_dojo_dialog_with_ok(
    game_title: str,
    *,
    timeout_seconds: float = 4.0,
) -> DojoDialogMatchV2:
    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    while time.monotonic() < deadline:
        if f12_pressed():
            raise DojoFightRequestError("F12_STOP")
        match = find_dojo_dialog_with_ok(game_title)
        if match is not None:
            return match
        time.sleep(0.05)
    raise DojoFightRequestError("DOJO_DIALOG_NOT_FOUND")


def click_first_option_ok(
    match: DojoDialogMatchV2,
    *,
    close_timeout_seconds: float = 3.0,
) -> None:
    """Select option zero and click the dialog's own OK button without keyboard focus."""

    import win32gui

    for hwnd in (match.dialog_hwnd, match.listbox_hwnd, match.ok_button_hwnd):
        if not win32gui.IsWindow(hwnd):
            raise DojoFightRequestError("DOJO_DIALOG_LOST")

    win32gui.SendMessage(match.listbox_hwnd, LB_SETCURSEL, 0, 0)
    selected = int(win32gui.SendMessage(match.listbox_hwnd, LB_GETCURSEL, 0, 0))
    if selected != 0:
        raise DojoFightRequestError(f"DOJO_OPTION_SELECTION_FAILED:{selected}")

    # BM_CLICK targets the Button control itself. It does not depend on the foreground window.
    win32gui.SendMessage(match.ok_button_hwnd, BM_CLICK, 0, 0)

    deadline = time.monotonic() + max(0.5, float(close_timeout_seconds))
    while time.monotonic() < deadline:
        if not win32gui.IsWindow(match.dialog_hwnd) or not win32gui.IsWindowVisible(match.dialog_hwnd):
            return
        if f12_pressed():
            raise DojoFightRequestError("F12_STOP")
        time.sleep(0.05)
    raise DojoFightRequestError("DOJO_DIALOG_DID_NOT_CLOSE")


def _click_target_from_match(match, frame, state, observer) -> TrainerClickTarget:
    """Build a click target from any authoritative visual match; distance is telemetry only."""

    from .grid_target_observer_v03 import _grid_distance

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


def search_trainer_until_visible(
    controller,
    *,
    timeout_seconds: float = 90.0,
    leader_threshold: float = 0.88,
    fps: float = 8.0,
    move_pulse_seconds: float = 0.09,
    telemetry_seconds: float = 0.50,
    confirm_frames: int = 2,
) -> TrainerClickTarget:
    """Obstacle-aware concentric search that stops on a confirmed visual trainer match."""

    from .entity_observer import decode_jpeg
    from .observer_runtime_v03 import V03ObserverConfig
    from .particle_safe_grid_target_v03 import ParticleSafeGridTargetObserver
    from .persistent_water_tracker_v03 import PersistentBackgroundWaterAwareEntityTracker
    from .post_combat_v03c import PersistentDojoLeaderDetector
    from .recorder import WindowsGameFrameSource

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
    observer.tracker = PersistentBackgroundWaterAwareEntityTracker(config)
    detector = PersistentDojoLeaderDetector(threshold=leader_threshold)
    engine = ObstacleAwarePostCombatRecoveryEngine(
        leader_detector=detector,
        search_delay_seconds=0.25,
        search_timeout_seconds=timeout_seconds,
        search_pulses_per_tile=4,
    )
    source = WindowsGameFrameSource()

    interval = 1.0 / max(1.0, min(20.0, float(fps)))
    pulse = max(0.03, min(0.14, float(move_pulse_seconds)))
    deadline = time.monotonic() + max(5.0, float(timeout_seconds))
    next_telemetry = 0.0
    visual_hits = 0
    previous_center: tuple[float, float] | None = None
    required_hits = max(1, int(confirm_frames))

    try:
        while time.monotonic() < deadline:
            loop_started = time.monotonic()
            if f12_pressed():
                raise DojoFightRequestError("F12_STOP")

            frame = decode_jpeg(bytes(source.capture().jpeg))
            state = observer.process(frame)
            now = time.monotonic()
            engine.observe_movement_frame(frame, state, now=now)
            match = detector.find(
                frame,
                arena_rect=state.arena_rect,
                flow=getattr(state, "global_flow", None),
                now=now,
            )

            if match is not None and match.source == "visual":
                left, top, width, height = match.bbox
                center = (left + width * 0.5, top + height * 0.5)
                if previous_center is not None and math.hypot(
                    center[0] - previous_center[0], center[1] - previous_center[1]
                ) <= 48.0:
                    visual_hits += 1
                else:
                    visual_hits = 1
                previous_center = center
                controller.apply_keys(())
                if visual_hits >= required_hits:
                    target = _click_target_from_match(match, frame, state, observer)
                    print(
                        f"TRAINER_VISUAL_CONFIRMED score={target.score:.3f} "
                        f"d={target.grid_distance} bbox={target.bbox}"
                    )
                    return target

                # Once a valid visual appears, freeze the route until the next frame confirms or
                # rejects it. Never walk past a trainer that was just seen.
                if now >= next_telemetry:
                    print(
                        f"TRAINER_VISUAL_CONFIRM hits={visual_hits}/{required_hits} "
                        f"score={match.score:.3f}"
                    )
                    next_telemetry = now + max(0.10, float(telemetry_seconds))
                elapsed = time.monotonic() - loop_started
                if elapsed < interval:
                    time.sleep(interval - elapsed)
                continue
            else:
                visual_hits = 0
                previous_center = None

            decision = engine._search_decision(now=now)
            controller.apply_keys(())
            if decision.move_pulse is not None:
                engine.arm_movement_probe(decision.move_pulse, now=now)
                controller.apply_keys((decision.move_pulse,))
                time.sleep(pulse)
                controller.apply_keys(())

            if now >= next_telemetry:
                motion = engine.last_movement_detected
                motion_text = "-" if motion is None else ("yes" if motion else "no")
                print(
                    f"TRAINER_SEARCH state={decision.state} move={decision.move_pulse or '-'} "
                    f"motion={motion_text} reason={decision.reason}"
                )
                next_telemetry = now + max(0.10, float(telemetry_seconds))

            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                time.sleep(interval - elapsed)
    finally:
        try:
            controller.apply_keys(())
        except Exception:
            pass
        source.close()

    raise DojoFightRequestError("TRAINER_SEARCH_TIMEOUT")


def _direction_toward_target(target: TrainerClickTarget) -> str:
    dx = float(target.normalized_x) - 0.5181
    dy = float(target.normalized_y) - 0.4706
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "down" if dy > 0 else "up"


def request_taijutsu_dojo_spar(
    game_title: str,
    *,
    dialog_delay_seconds: float = 10.0,
    dialog_find_timeout_seconds: float = 4.0,
    spawn_delay_seconds: float = 5.0,
    leader_threshold: float = 0.88,
    trainer_search_timeout_seconds: float = 90.0,
    interaction_attempts: int = 6,
    controller=None,
) -> TrainerClickTarget:
    """Find trainer from anywhere, click it, then click the dialog's own OK button."""

    from .pilot import WindowsGameController
    from pc_agent.windows import ensure_game_window_foreground

    owns_controller = controller is None
    controller = controller or WindowsGameController(recover_foreground=False)
    controller.repeat_keys = set()
    try:
        controller.activate()
        controller.release_all()

        dialog = None
        successful_target = None
        clicked_at = None
        attempts = max(1, min(12, int(interaction_attempts)))
        for attempt in range(1, attempts + 1):
            target = search_trainer_until_visible(
                controller,
                timeout_seconds=trainer_search_timeout_seconds if attempt == 1 else 8.0,
                leader_threshold=leader_threshold,
            )
            controller.release_all()
            clicked_at = time.monotonic()
            controller.click_normalized(target.normalized_x, target.normalized_y)
            controller.release_all()
            print(
                f"TRAINER_CLICK attempt={attempt}/{attempts} score={target.score:.3f} "
                f"d={target.grid_distance}"
            )
            try:
                dialog = wait_for_dojo_dialog_with_ok(
                    game_title,
                    timeout_seconds=dialog_find_timeout_seconds,
                )
                successful_target = target
                break
            except DojoFightRequestError as error:
                if str(error) != "DOJO_DIALOG_NOT_FOUND" or attempt >= attempts:
                    raise
                direction = _direction_toward_target(target)
                print(
                    f"DIALOG_NOT_OPEN: approach one pulse {direction} and retry / "
                    f"aproximar {direction} e tentar novamente"
                )
                controller.apply_keys((direction,))
                time.sleep(0.09)
                controller.apply_keys(())
                time.sleep(0.20)

        if dialog is None or successful_target is None or clicked_at is None:
            raise DojoFightRequestError("DOJO_DIALOG_NOT_FOUND")

        elapsed = time.monotonic() - clicked_at
        _interruptible_wait(max(0.0, float(dialog_delay_seconds) - elapsed))
        refreshed = find_dojo_dialog_with_ok(game_title)
        click_first_option_ok(refreshed or dialog)

        focus = ensure_game_window_foreground(game_title)
        if not focus.ok:
            raise DojoFightRequestError(focus.error or "GAME_REFOCUS_FAILED")
        _interruptible_wait(spawn_delay_seconds)
        return successful_target
    finally:
        controller.release_all()
        if owns_controller:
            _close_owned_controller(controller)


__all__ = [
    "DojoDialogMatchV2",
    "click_first_option_ok",
    "find_dojo_dialog_with_ok",
    "request_taijutsu_dojo_spar",
    "search_trainer_until_visible",
    "wait_for_dojo_dialog_with_ok",
]
