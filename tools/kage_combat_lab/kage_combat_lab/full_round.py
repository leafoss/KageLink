from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any


MIN_MEDITATION_SECONDS = 5.25


class EmergencyStop(RuntimeError):
    pass


def enforce_min_meditation_seconds(engine: Any) -> float:
    """Prevent a second V before BYOND accepts the meditation exit toggle."""

    current = float(getattr(engine, "min_meditation_seconds", 0.0) or 0.0)
    protected = max(MIN_MEDITATION_SECONDS, current)
    setattr(engine, "min_meditation_seconds", protected)
    return protected


def _disable_h(decision):
    if not bool(getattr(decision, "press_h", False)):
        return decision
    sequence = tuple(
        action
        for action in tuple(getattr(decision, "action_sequence", ()))
        if "H_TAP" not in action and "AIM_" not in action
    )
    return replace(
        decision,
        press_h=False,
        h_pulse_ms=None,
        aim_requires_confirmation=False,
        action_sequence=sequence,
        reason=f"{decision.reason}; H disabled by command line",
    )


def _write_log(handle, payload: dict[str, Any]) -> None:
    if handle is None:
        return
    handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    handle.flush()


def _candidate_for_decision(combat_frame, decision):
    visual_track_id = getattr(decision, "visual_track_id", None)
    if visual_track_id is None:
        return None
    return next(
        (
            candidate
            for candidate in combat_frame.candidates
            if int(candidate.track_id) == int(visual_track_id)
        ),
        None,
    )


def _direction_event(previous: str | None, current: str | None) -> bool:
    if previous is None or current is None or previous == current:
        return False
    opposite = {
        ("LEFT", "RIGHT"),
        ("RIGHT", "LEFT"),
        ("UP", "DOWN"),
        ("DOWN", "UP"),
    }
    return (previous, current) in opposite or (
        previous in {"LEFT", "RIGHT"} and current in {"UP", "DOWN"}
    ) or (
        previous in {"UP", "DOWN"} and current in {"LEFT", "RIGHT"}
    )


def main() -> int:
    # Import the validated patch chain before resolving concrete runtime classes.
    import kage_pilot_live_v03 as live_runtime
    import kage_pilot_live_v03k_round as validated_round

    from pc_agent.kage_pilot.entity_observer import decode_jpeg
    from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
    from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
        PersistentBackgroundWaterAwareEntityTracker,
    )
    from pc_agent.kage_pilot.recorder import WindowsGameFrameSource

    from .domain import CELL_SIZE_PX, H_COOLDOWN_SECONDS, TargetState
    from .event_recorder import CombatEventVideoRecorder
    from .live_bridge import PhysicalCombatInput, combat_frame_from_observer_state
    from .strategy import GridFocusStrategy
    from .target_memory import TargetCapsuleMemory

    previous_name, remaining = validated_round._extract_internal_args(sys.argv[1:])
    validated_round._configure_round(previous_name)
    args = live_runtime.build_parser().parse_args(remaining)

    def f12_pressed() -> bool:
        return bool(live_runtime._f12_pressed())

    def interruptible_sleep(seconds: float) -> None:
        deadline = time.monotonic() + max(0.0, float(seconds))
        while True:
            if f12_pressed():
                raise EmergencyStop("F12_STOP")
            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0.0:
                return
            time.sleep(min(0.01, remaining_seconds))

    observer_config = V03ObserverConfig(
        player_x=args.player_x,
        player_y=args.player_y,
        player_exclusion_radius=max(args.player_box_width, args.player_box_height) / 2.0,
        player_box_width=args.player_box_width,
        player_box_height=args.player_box_height,
        enemy_threshold=args.target_acquire,
        target_acquire_threshold=args.target_acquire,
        target_keep_threshold=args.target_keep,
        track_ttl_seconds=max(0.5, float(args.track_ttl)),
        track_match_distance=max(20.0, float(args.match_distance)),
        dynamic_background_enabled=True,
        background_similarity=args.background_similarity,
        background_min_dense_hits=args.background_min_hits,
        background_min_age=args.background_min_age,
        background_cell_size=float(CELL_SIZE_PX),
        reacquire_ttl=max(6.0, float(args.reacquire_ttl)),
        reacquire_distance=max(128.0, float(args.reacquire_distance)),
        reacquire_similarity=args.reacquire_similarity,
    ).normalized()

    observer = live_runtime.ParticleSafeGridTargetObserver(
        observer_config,
        tile_size=float(CELL_SIZE_PX),
        contact_lock_seconds=max(4.0, float(args.contact_lock_seconds)),
        show_grid=False,
        contact_confirm_frames=max(2, int(args.contact_confirm_frames)),
    )
    tracker = PersistentBackgroundWaterAwareEntityTracker(observer_config)
    observer.tracker = tracker

    strategy = GridFocusStrategy(h_cooldown_seconds=H_COOLDOWN_SECONDS)
    rejection_generation = int(validated_round._REJECTION_GENERATION)

    app_config = live_runtime.load_config()
    victory_watcher = live_runtime.ChatVictoryWatcher(
        app_config.game_title,
        app_config.chat_class,
    )
    post_engine = live_runtime.PostCombatRecoveryEngine(
        leader_detector=live_runtime.DojoLeaderDetector(threshold=args.leader_threshold),
        leader_confirm_frames=args.leader_confirm_frames,
        health_target=args.recovery_hp,
        chakra_target=args.recovery_chakra,
        recovery_confirm_frames=args.recovery_confirm_frames,
    )
    meditation_seconds = enforce_min_meditation_seconds(post_engine)

    source = WindowsGameFrameSource()
    controller = live_runtime.WindowsGameController(
        recover_foreground=False,
        debug=bool(args.debug_input),
        repeat_delay_seconds=0.25,
        repeat_interval_seconds=0.25,
    )
    controller.repeat_keys = {"r"}
    physical = PhysicalCombatInput(controller, sleep_fn=interruptible_sleep)

    log_handle = None
    if args.log is not None:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.log.open("w", encoding="utf-8")
        report_root = args.log.parent
        round_stem = args.log.stem
    else:
        report_root = Path(__file__).resolve().parents[1] / "reports"
        report_root.mkdir(parents=True, exist_ok=True)
        round_stem = f"round_{time.strftime('%Y%m%d_%H%M%S')}"

    target_cache_root = report_root / "target_cache" / round_stem
    event_video_root = report_root / "event_videos" / round_stem
    target_memory = TargetCapsuleMemory(root=target_cache_root)

    interval = 1.0 / max(1.0, min(20.0, float(args.fps)))
    telemetry_interval = max(0.1, float(args.telemetry_seconds))
    chat_poll_interval = max(0.10, min(2.0, float(args.chat_poll_seconds)))
    startup_delay = max(0.0, float(args.startup_delay))
    move_pulse_seconds = max(0.03, min(0.14, float(args.move_pulse)))
    v_pulse_seconds = max(0.03, min(0.20, float(args.v_pulse)))
    combat_seconds = max(1.0, float(args.seconds))
    post_timeout = max(5.0, float(args.post_combat_timeout))
    event_recorder = CombatEventVideoRecorder(
        event_video_root,
        fps=max(2.0, min(20.0, float(args.fps))),
        pre_seconds=5.0,
        post_seconds=5.0,
    )

    print("KAGE COMBAT LAB - FULL ROUND CHASE_ALWAYS_ON + TARGET CAPSULE")
    print(f"GRID={CELL_SIZE_PX}px immutable; H cooldown={H_COOLDOWN_SECONDS:.1f}s")
    print("TARGET: persistent logical identity + local ReID + negative background memory")
    print("AIM: direction pulse -> fresh capture -> correction if needed -> H")
    print("D0: 12px deadzone + two-frame direction hysteresis")
    print("EVENT VIDEO: 5s before + 5s after hard loss, ReID, direction flip or aim failure")
    print("KO: authoritative chat + different-opponent identity gate")
    print(
        f"POST: validated Trainer return + V/Y recovery; "
        f"minimum meditation={meditation_seconds:.2f}s"
    )
    print(f"TARGET CACHE: {target_cache_root}")
    print(f"EVENT VIDEOS: {event_video_root}")
    print("F12 = EMERGENCY STOP / PARADA IMEDIATA")

    frames = 0
    started = 0.0
    next_telemetry = 0.0
    next_chat_poll = 0.0
    victory_signal = None
    emergency_stop = False
    post_ready = False
    failure: Exception | None = None
    previous_state = TargetState.SEARCH
    previous_visual_track_id: int | None = None
    previous_face: str | None = None

    try:
        physical.activate()
        if startup_delay > 0:
            print(f"FULL ROUND ARMING IN {startup_delay:.1f}s")
            interruptible_sleep(startup_delay)

        victory_watcher.prime()
        physical.start_combat_hold()
        started = time.monotonic()
        next_telemetry = started
        next_chat_poll = started
        print("FULL ROUND COMBAT ARMED")

        while time.monotonic() - started < combat_seconds:
            loop_started = time.monotonic()
            if f12_pressed():
                raise EmergencyStop("F12_STOP")

            now = loop_started
            if now >= next_chat_poll:
                victory_signal = victory_watcher.poll()
                next_chat_poll = now + chat_poll_interval
                if victory_signal is not None:
                    controller.release_all()
                    print(f"VICTORY_CHAT / VITORIA_CHAT: {victory_signal.text}")
                    _write_log(
                        log_handle,
                        {
                            "t": round(now - started, 4),
                            "event": "victory_chat",
                            "text": victory_signal.text,
                        },
                    )
                    break

            current_generation = int(validated_round._REJECTION_GENERATION)
            if current_generation != rejection_generation:
                rejection_generation = current_generation
                strategy.reset_round()
                target_memory.close()
                target_memory = TargetCapsuleMemory(
                    root=target_cache_root / f"generation_{rejection_generation:03d}"
                )
                previous_state = TargetState.SEARCH
                previous_visual_track_id = None
                previous_face = None
                print(
                    f"PR25_TARGET_RESET generation={rejection_generation} "
                    "reason=KO_IDENTITY_REJECTED"
                )

            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            state = observer.process(frame, timestamp=now)
            combat_frame = combat_frame_from_observer_state(
                observer=observer,
                state=state,
                frame_index=frames,
                timestamp_seconds=now,
                frame_bgr=frame,
                target_memory=target_memory,
            )
            raw_decision = strategy.update(combat_frame)
            decision = _disable_h(raw_decision) if bool(args.disable_h) else raw_decision

            validated_round._GATE.observe_target(
                target_id=decision.combat_target_id,
                target_mode=getattr(observer, "target_mode", "NONE"),
            )

            aim_probe_details: dict[str, Any] = {}

            def confirm_aim(attempted_face: str) -> str | None:
                probe_now = time.monotonic()
                probe_capture = source.capture()
                probe_image = decode_jpeg(bytes(probe_capture.jpeg))
                probe_state = observer.process(probe_image, timestamp=probe_now)
                probe_frame = combat_frame_from_observer_state(
                    observer=observer,
                    state=probe_state,
                    frame_index=frames,
                    timestamp_seconds=probe_now,
                    frame_bgr=probe_image,
                    target_memory=target_memory,
                )
                probe_candidate = target_memory.best_current_candidate(
                    probe_frame,
                    confirmed_cell=raw_decision.confirmed_cell,
                )
                confirmed_face = (
                    target_memory.face_for_candidate(
                        probe_frame,
                        probe_candidate,
                        previous=attempted_face,
                    )
                    if probe_candidate is not None
                    else None
                )
                aim_probe_details.update(
                    {
                        "attempted_face": attempted_face,
                        "confirmed_face": confirmed_face,
                        "visual_track_id": (
                            probe_candidate.track_id if probe_candidate is not None else None
                        ),
                        "identity_score": (
                            probe_candidate.identity_score
                            if probe_candidate is not None
                            else 0.0
                        ),
                        "appearance_score": (
                            probe_candidate.appearance_score
                            if probe_candidate is not None
                            else 0.0
                        ),
                    }
                )
                return confirmed_face

            actions = physical.execute(
                decision,
                confirm_aim=confirm_aim if decision.press_h else None,
            )
            h_fired = physical.h_fired(actions)
            if raw_decision.press_h:
                strategy.resolve_h_request(fired=h_fired)

            selected = _candidate_for_decision(combat_frame, decision)
            if (
                selected is not None
                and decision.combat_target_id is not None
                and decision.target_state is TargetState.LOCKED
            ):
                target_memory.observe_selected(
                    frame_bgr=frame,
                    state=state,
                    candidate=selected,
                    timestamp=now,
                    face=decision.face,
                    grid_distance=decision.grid_distance,
                )

            events: list[str] = []
            if (
                previous_state is not TargetState.SEARCH
                and decision.target_state is TargetState.SEARCH
                and "hard lost" in decision.reason
            ):
                events.append("TARGET_HARD_LOST")
            if (
                decision.reidentified
                and decision.visual_track_id is not None
                and decision.visual_track_id != previous_visual_track_id
            ):
                events.append("REID_SUCCESS")
            if _direction_event(previous_face, decision.face):
                events.append("DIRECTION_FLIP")
            if raw_decision.press_h and not h_fired:
                events.append("AIM_UNCONFIRMED")

            event_recorder.push(
                frame,
                decision=decision,
                candidate=selected,
                actions=actions,
                events=events,
                timestamp=now,
                arena_rect=tuple(int(value) for value in state.arena_rect),
            )

            if now >= next_telemetry:
                action_text = ",".join(actions) if actions else "HOLD_R"
                print(
                    f"FULL_COMBAT frame={frames:04d} "
                    f"state={decision.target_state.value} "
                    f"logical={decision.combat_target_id or '-'} "
                    f"visual={decision.visual_track_id or '-'} "
                    f"D={decision.grid_distance} face={decision.face or '-'} "
                    f"id={decision.identity_score:.2f} "
                    f"app={decision.appearance_score:.2f} "
                    f"bg={decision.background_probability:.2f} "
                    f"reid={decision.reidentified} "
                    f"actions={action_text} reason={decision.reason}"
                )
                next_telemetry = now + telemetry_interval

            _write_log(
                log_handle,
                {
                    "t": round(now - started, 4),
                    "phase": "combat",
                    "frame": frames,
                    "state": decision.target_state.value,
                    "target_id": decision.combat_target_id,
                    "logical_target_id": decision.combat_target_id,
                    "visual_track_id": decision.visual_track_id,
                    "grid_distance": decision.grid_distance,
                    "face": decision.face,
                    "move": decision.move,
                    "press_h": decision.press_h,
                    "h_fired": h_fired,
                    "h_cooldown": round(decision.h_cooldown_remaining_seconds, 4),
                    "identity_score": round(decision.identity_score, 4),
                    "appearance_score": round(decision.appearance_score, 4),
                    "background_probability": round(
                        decision.background_probability, 4
                    ),
                    "reidentified": decision.reidentified,
                    "aim_probe": aim_probe_details or None,
                    "actions": list(actions),
                    "visible_tracks": len(state.tracks),
                    "capsule_exemplars": len(target_memory.exemplars),
                    "background_cells": target_memory.background_cell_count,
                    "events": events,
                    "reason": decision.reason,
                },
            )

            previous_state = decision.target_state
            previous_visual_track_id = decision.visual_track_id
            previous_face = decision.face
            frames += 1
            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                interruptible_sleep(interval - elapsed)

        if (
            victory_signal is not None
            and not emergency_stop
            and not bool(args.disable_post_combat)
        ):
            controller.release_all()
            print("POST_COMBAT / POS-COMBATE: SEEK_DOJO_LEADER")
            post_started = time.monotonic()
            next_post_telemetry = post_started

            while time.monotonic() - post_started < post_timeout:
                loop_started = time.monotonic()
                if f12_pressed():
                    raise EmergencyStop("F12_STOP_POST_COMBAT")

                captured = source.capture()
                frame = decode_jpeg(bytes(captured.jpeg))
                state = observer.process(frame, timestamp=loop_started)
                now = time.monotonic()
                post = post_engine.step(frame, state, observer, now=now)

                # No persistent key survives the combat -> recovery transition.
                controller.apply_keys(())

                if post.move_pulse is not None:
                    controller.apply_keys((post.move_pulse,))
                    interruptible_sleep(move_pulse_seconds)
                    controller.apply_keys(())

                if post.tap_v:
                    controller.tap("v", v_pulse_seconds)
                    print(
                        f"POST V_TAP state={post.state} "
                        f"meditation_guard={meditation_seconds:.2f}s"
                    )

                if now >= next_post_telemetry:
                    print(live_runtime._post_line(post))
                    next_post_telemetry = now + telemetry_interval

                _write_log(
                    log_handle,
                    {
                        "t": round(now - post_started, 4),
                        "phase": "post_combat",
                        "state": post.state,
                        "move_pulse": post.move_pulse,
                        "tap_v": post.tap_v,
                        "leader_score": post.leader_score,
                        "leader_distance": post.leader_distance,
                        "health": post.health,
                        "chakra": post.chakra,
                        "meditation_guard_seconds": meditation_seconds,
                        "reason": post.reason,
                    },
                )

                frames += 1
                if post.state == "READY":
                    post_ready = True
                    print("READY / PRONTO: HP and Chakra recovery thresholds reached")
                    break

                elapsed = time.monotonic() - loop_started
                if elapsed < interval:
                    interruptible_sleep(interval - elapsed)

            if not post_ready and not emergency_stop:
                print(
                    f"POST_COMBAT_TIMEOUT state={post_engine.state} / "
                    f"TIMEOUT_POS_COMBATE estado={post_engine.state}"
                )
                if post_engine.state == "MEDITATING":
                    meditation_started_at = getattr(
                        post_engine,
                        "_meditation_started_at",
                        None,
                    )
                    if meditation_started_at is not None:
                        remaining_guard = meditation_seconds - (
                            time.monotonic() - float(meditation_started_at)
                        )
                        if remaining_guard > 0.0:
                            print(
                                f"MEDITATION_EXIT_WAIT remaining={remaining_guard:.2f}s"
                            )
                            interruptible_sleep(remaining_guard)
                    controller.tap("v", v_pulse_seconds)
                    print("V OFF after protected post-combat timeout")

    except EmergencyStop as exc:
        emergency_stop = True
        print(f"F12 STOP / PARADA F12: {exc}")
    except KeyboardInterrupt:
        emergency_stop = True
        print("Keyboard interrupt / interrupcao de teclado")
    except Exception as exc:
        failure = exc
        print(
            f"FULL ROUND STOPPED / RODADA INTERROMPIDA: "
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        try:
            controller.release_all()
        except Exception:
            pass
        try:
            source.close()
        except Exception:
            pass
        close = getattr(controller, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        try:
            target_memory.close()
        except Exception:
            pass
        try:
            event_recorder.close()
        except Exception:
            pass
        if log_handle is not None:
            log_handle.close()

    duration = max(1e-6, time.monotonic() - started) if started else 0.0
    fps = frames / duration if duration > 0.0 else 0.0
    result = (
        "error"
        if failure is not None
        else "ready"
        if post_ready
        else "victory"
        if victory_signal is not None
        else "stopped"
        if emergency_stop
        else "timeout"
    )
    print(f"Live stopped / Controle encerrado: result={result} frames={frames} fps={fps:.1f}")
    print(f"Target capsule: {target_cache_root}")
    print(f"Event videos: {event_video_root}")
    return 1 if failure is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
