from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .domain import CELL_SIZE_PX, FIRST_LIVE_TEST_MAX_SECONDS, GRID_CONTRACT_VERSION
from .event_recorder import CombatEventVideoRecorder
from .live_bridge import PhysicalCombatInput, combat_frame_from_observer_state
from .strategy import GridFocusStrategy
from .target_memory import TargetCapsuleMemory


VK_F12 = 0x7B
_user32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
if _user32 is not None:
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short


class EmergencyStop(RuntimeError):
    pass


def f12_pressed() -> bool:
    return bool(_user32 is not None and (_user32.GetAsyncKeyState(VK_F12) & 0x8000))


def _interruptible_sleep(seconds: float) -> None:
    deadline = time.monotonic() + max(0.0, float(seconds))
    while True:
        if f12_pressed():
            raise EmergencyStop("F12_STOP")
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return
        time.sleep(min(0.01, remaining))


def _close_controller(controller: Any) -> None:
    try:
        controller.release_all()
    except Exception:
        pass
    stop = getattr(controller, "_repeat_stop", None)
    if stop is not None:
        stop.set()
    thread = getattr(controller, "_repeat_thread", None)
    if thread is not None and thread.is_alive():
        thread.join(timeout=0.5)
    try:
        controller.release_all()
    except Exception:
        pass
    core = getattr(controller, "_controller", None)
    if core is not None and hasattr(core, "deactivate"):
        try:
            core.deactivate()
        except Exception:
            pass


def _build_runtime():
    try:
        import cv2
        from pc_agent.kage_pilot.chat_victory_v03g import RobustChatVictoryWatcher
        from pc_agent.kage_pilot.entity_observer import decode_jpeg
        from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig, render_overlay_v03
        from pc_agent.kage_pilot.particle_safe_grid_target_v03 import ParticleSafeGridTargetObserver
        from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
            PersistentBackgroundWaterAwareEntityTracker,
        )
        from pc_agent.kage_pilot.pilot import WindowsGameController
        from pc_agent.kage_pilot.recorder import WindowsGameFrameSource
    except ImportError as error:
        raise RuntimeError(
            "LIVE_INPUT_DEPENDENCY_MISSING: use the full KageLink checkout and its "
            f"Python environment ({error})"
        ) from error

    config = V03ObserverConfig(
        player_x=0.5181,
        player_y=0.4706,
        player_exclusion_radius=19.0,
        player_box_width=18.0,
        player_box_height=38.0,
        dynamic_background_enabled=True,
        background_cell_size=float(CELL_SIZE_PX),
        reacquire_ttl=6.0,
        reacquire_distance=160.0,
    ).normalized()
    observer = ParticleSafeGridTargetObserver(
        config,
        tile_size=float(CELL_SIZE_PX),
        contact_lock_seconds=4.0,
        show_grid=True,
        contact_confirm_frames=2,
    )
    observer.tracker = PersistentBackgroundWaterAwareEntityTracker(config)
    source = WindowsGameFrameSource()
    controller = WindowsGameController(
        recover_foreground=False,
        debug=False,
        repeat_delay_seconds=0.25,
        repeat_interval_seconds=0.25,
    )
    controller.repeat_keys = {"r"}
    watcher = RobustChatVictoryWatcher("Shinobi Story Online", "RICHEDIT50W")
    return cv2, decode_jpeg, render_overlay_v03, config, observer, source, controller, watcher


def _render_live_preview(
    *,
    cv2,
    render_overlay_v03,
    frame,
    state,
    observer,
    config,
    decision,
    actions: tuple[str, ...],
) -> None:
    preview = render_overlay_v03(frame, state, config, observer.tracker)
    preview = observer.draw_grid_overlay(preview, state)
    lines = (
        f"PR25 LIVE INPUT | {GRID_CONTRACT_VERSION}",
        f"state={decision.target_state.value} logical={decision.combat_target_id or '-'} visual={decision.visual_track_id or '-'} D={decision.grid_distance}",
        f"face={decision.face or '-'} H={decision.press_h} move={decision.move or '-'}",
        f"id={decision.identity_score:.2f} app={decision.appearance_score:.2f} bg={decision.background_probability:.2f} reid={decision.reidentified}",
        f"actions={','.join(actions) if actions else 'HOLD_R'}",
        "F12 = EMERGENCY STOP",
    )
    y = 24
    for line in lines:
        cv2.putText(
            preview,
            line,
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        y += 24
    cv2.imshow("Kage Combat Lab - LIVE INPUT", preview)
    cv2.waitKey(1)


def _write_log(handle, payload: dict[str, Any]) -> None:
    handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    handle.flush()


def _candidate_for_decision(combat_frame, decision):
    if decision.visual_track_id is None:
        return None
    return next(
        (
            candidate
            for candidate in combat_frame.candidates
            if candidate.track_id == decision.visual_track_id
        ),
        None,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PR25 direct live combat input using the immutable 64px grid"
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=FIRST_LIVE_TEST_MAX_SECONDS,
        help="Maximum armed duration",
    )
    parser.add_argument("--fps", type=float, default=8.0)
    parser.add_argument("--countdown", type=float, default=3.0)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--log-path", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    if os.name != "nt":
        print("LIVE_INPUT_WINDOWS_ONLY", file=sys.stderr)
        return 2

    args = build_parser().parse_args(argv)
    max_seconds = max(5.0, min(FIRST_LIVE_TEST_MAX_SECONDS, float(args.max_seconds)))
    fps = max(2.0, min(12.0, float(args.fps)))
    countdown = max(0.0, min(10.0, float(args.countdown)))
    interval = 1.0 / fps

    (
        cv2,
        decode_jpeg,
        render_overlay_v03,
        config,
        observer,
        source,
        controller,
        watcher,
    ) = _build_runtime()

    strategy = GridFocusStrategy()
    physical = PhysicalCombatInput(controller, sleep_fn=_interruptible_sleep)
    reports = Path(__file__).resolve().parents[1] / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    log_path = (
        Path(args.log_path).expanduser().resolve()
        if str(args.log_path).strip()
        else reports / f"live_input_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    session_stem = log_path.stem
    memory = TargetCapsuleMemory(root=reports / "target_cache" / session_stem)
    recorder = CombatEventVideoRecorder(
        reports / "event_videos" / session_stem,
        fps=fps,
        pre_seconds=5.0,
        post_seconds=5.0,
    )

    print("KAGE COMBAT LAB - DIRECT LIVE INPUT")
    print(f"Grid: {CELL_SIZE_PX}x{CELL_SIZE_PX}px immutable")
    print("Target: persistent visual capsule + local ReID + background negatives")
    print("Aim: fresh capture required before every H")
    print("Window: Shinobi Story Online")
    print(f"Armed limit: {max_seconds:.0f}s")
    print("F12 stops immediately and releases every key.")
    print("This mode sends real R, direction and H inputs.")

    frame_index = 0
    started = 0.0
    exit_reason = "PROCESS_EXIT"
    log_handle = log_path.open("w", encoding="utf-8")
    previous_state = "SEARCH"
    previous_visual_track = None
    previous_face = None

    try:
        physical.activate()
        watcher.prime()

        remaining = int(countdown)
        while remaining > 0:
            print(f"LIVE INPUT ARMING IN {remaining}...")
            _interruptible_sleep(1.0)
            remaining -= 1

        physical.start_combat_hold()
        started = time.monotonic()
        print("LIVE INPUT ARMED")

        while True:
            loop_started = time.monotonic()
            now = loop_started
            if f12_pressed():
                raise EmergencyStop("F12_STOP")
            if now - started >= max_seconds:
                exit_reason = "TIMEOUT"
                break

            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            state = observer.process(frame, timestamp=now)
            victory = watcher.poll()
            ko_confirmed = victory is not None

            combat_frame = combat_frame_from_observer_state(
                observer=observer,
                state=state,
                frame_index=frame_index,
                timestamp_seconds=now,
                ko_confirmed=ko_confirmed,
                frame_bgr=frame,
                target_memory=memory,
            )
            decision = strategy.update(combat_frame)

            def confirm_aim(attempted_face: str) -> str | None:
                probe_now = time.monotonic()
                probe_capture = source.capture()
                probe_image = decode_jpeg(bytes(probe_capture.jpeg))
                probe_state = observer.process(probe_image, timestamp=probe_now)
                probe_frame = combat_frame_from_observer_state(
                    observer=observer,
                    state=probe_state,
                    frame_index=frame_index,
                    timestamp_seconds=probe_now,
                    frame_bgr=probe_image,
                    target_memory=memory,
                )
                candidate = memory.best_current_candidate(
                    probe_frame,
                    confirmed_cell=decision.confirmed_cell,
                )
                if candidate is None:
                    return None
                return memory.face_for_candidate(
                    probe_frame,
                    candidate,
                    previous=attempted_face,
                )

            actions = physical.execute(
                decision,
                confirm_aim=confirm_aim if decision.press_h else None,
            )
            h_fired = physical.h_fired(actions)
            if decision.press_h:
                strategy.resolve_h_request(fired=h_fired)

            selected = _candidate_for_decision(combat_frame, decision)
            if (
                selected is not None
                and decision.combat_target_id is not None
                and decision.target_state.value == "LOCKED"
            ):
                memory.observe_selected(
                    frame_bgr=frame,
                    state=state,
                    candidate=selected,
                    timestamp=now,
                    face=decision.face,
                    grid_distance=decision.grid_distance,
                )

            events = []
            if previous_state != "SEARCH" and decision.target_state.value == "SEARCH":
                events.append("TARGET_HARD_LOST")
            if (
                decision.reidentified
                and decision.visual_track_id is not None
                and decision.visual_track_id != previous_visual_track
            ):
                events.append("REID_SUCCESS")
            if (
                previous_face is not None
                and decision.face is not None
                and previous_face != decision.face
            ):
                events.append("DIRECTION_FLIP")
            if decision.press_h and not h_fired:
                events.append("AIM_UNCONFIRMED")

            recorder.push(
                frame,
                decision=decision,
                candidate=selected,
                actions=actions,
                events=events,
                timestamp=now,
                arena_rect=tuple(int(value) for value in state.arena_rect),
            )

            payload = {
                "frame": frame_index,
                "time": round(now - started, 3),
                "state": decision.target_state.value,
                "target": decision.combat_target_id,
                "logical_target_id": decision.combat_target_id,
                "visual_track_id": decision.visual_track_id,
                "distance": decision.grid_distance,
                "face": decision.face,
                "move": decision.move,
                "press_h": decision.press_h,
                "h_fired": h_fired,
                "cooldown": round(decision.h_cooldown_remaining_seconds, 3),
                "identity_score": round(decision.identity_score, 4),
                "appearance_score": round(decision.appearance_score, 4),
                "background_probability": round(
                    decision.background_probability, 4
                ),
                "reidentified": decision.reidentified,
                "actions": list(actions),
                "reason": decision.reason,
                "visible_tracks": len(state.tracks),
                "capsule_exemplars": len(memory.exemplars),
                "events": events,
                "ko": ko_confirmed,
            }
            _write_log(log_handle, payload)
            print(
                f"LIVE frame={frame_index:04d} state={payload['state']} "
                f"logical={payload['target'] or '-'} visual={payload['visual_track_id'] or '-'} "
                f"D={payload['distance']} face={payload['face'] or '-'} "
                f"id={payload['identity_score']:.2f} bg={payload['background_probability']:.2f} "
                f"actions={','.join(actions) or 'HOLD_R'}"
            )

            if not args.no_preview:
                _render_live_preview(
                    cv2=cv2,
                    render_overlay_v03=render_overlay_v03,
                    frame=frame,
                    state=state,
                    observer=observer,
                    config=config,
                    decision=decision,
                    actions=actions,
                )

            if ko_confirmed or decision.target_state.value == "ENDED":
                exit_reason = "KO_CONFIRMED"
                break

            previous_state = decision.target_state.value
            previous_visual_track = decision.visual_track_id
            previous_face = decision.face
            frame_index += 1
            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                _interruptible_sleep(interval - elapsed)

        return 0
    except EmergencyStop:
        exit_reason = "F12_STOP"
        return 130
    except KeyboardInterrupt:
        exit_reason = "CTRL_C"
        return 130
    except Exception as error:
        exit_reason = f"ERROR:{type(error).__name__}:{error}"
        print(exit_reason, file=sys.stderr)
        return 1
    finally:
        try:
            physical.shutdown()
        except Exception:
            _close_controller(controller)
        try:
            source.close()
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        try:
            memory.close()
        except Exception:
            pass
        try:
            recorder.close()
        except Exception:
            pass
        _write_log(log_handle, {"event": "EXIT", "reason": exit_reason})
        log_handle.close()
        print(f"LIVE INPUT STOPPED: {exit_reason}")
        print(f"Diagnostic log: {log_path}")
        print(f"Target capsule: {reports / 'target_cache' / session_stem}")
        print(f"Event videos: {reports / 'event_videos' / session_stem}")


if __name__ == "__main__":
    raise SystemExit(main())
