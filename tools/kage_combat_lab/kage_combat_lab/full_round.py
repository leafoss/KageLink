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
        if "H_TAP" not in action and "AIM_CURRENT" not in action
    )
    return replace(
        decision,
        press_h=False,
        h_pulse_ms=None,
        action_sequence=sequence,
        reason=f"{decision.reason}; H disabled by command line",
    )


def _write_log(handle, payload: dict[str, Any]) -> None:
    if handle is None:
        return
    handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    handle.flush()


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
    from .live_bridge import PhysicalCombatInput, combat_frame_from_observer_state
    from .strategy import GridFocusStrategy

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
        reacquire_ttl=args.reacquire_ttl,
        reacquire_distance=args.reacquire_distance,
        reacquire_similarity=args.reacquire_similarity,
    ).normalized()

    observer = live_runtime.ParticleSafeGridTargetObserver(
        observer_config,
        tile_size=float(CELL_SIZE_PX),
        contact_lock_seconds=args.contact_lock_seconds,
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

    interval = 1.0 / max(1.0, min(20.0, float(args.fps)))
    telemetry_interval = max(0.1, float(args.telemetry_seconds))
    chat_poll_interval = max(0.10, min(2.0, float(args.chat_poll_seconds)))
    startup_delay = max(0.0, float(args.startup_delay))
    move_pulse_seconds = max(0.03, min(0.14, float(args.move_pulse)))
    v_pulse_seconds = max(0.03, min(0.20, float(args.v_pulse)))
    combat_seconds = max(1.0, float(args.seconds))
    post_timeout = max(5.0, float(args.post_combat_timeout))

    print("KAGE COMBAT LAB - FULL ROUND CHASE_ALWAYS_ON")
    print(f"GRID={CELL_SIZE_PX}px immutable; H cooldown={H_COOLDOWN_SECONDS:.1f}s")
    print("COMBAT: clean target -> chase continuously toward D=0")
    print("KO: authoritative chat + different-opponent identity gate")
    print(
        f"POST: validated Trainer return + V/Y recovery; "
        f"minimum meditation={meditation_seconds:.2f}s"
    )
    print("F12 = EMERGENCY STOP / PARADA IMEDIATA")

    frames = 0
    started = 0.0
    next_telemetry = 0.0
    next_chat_poll = 0.0
    victory_signal = None
    emergency_stop = False
    post_ready = False
    failure: Exception | None = None

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
            )
            decision = strategy.update(combat_frame)
            if bool(args.disable_h):
                decision = _disable_h(decision)

            validated_round._GATE.observe_target(
                target_id=decision.combat_target_id,
                target_mode=getattr(observer, "target_mode", "NONE"),
            )
            actions = physical.execute(decision)

            if now >= next_telemetry:
                action_text = ",".join(actions) if actions else "HOLD_R"
                print(
                    f"FULL_COMBAT frame={frames:04d} "
                    f"state={decision.target_state.value} "
                    f"target={decision.combat_target_id or '-'} "
                    f"D={decision.grid_distance} face={decision.face or '-'} "
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
                    "grid_distance": decision.grid_distance,
                    "face": decision.face,
                    "move": decision.move,
                    "press_h": decision.press_h,
                    "h_cooldown": round(decision.h_cooldown_remaining_seconds, 4),
                    "actions": list(actions),
                    "visible_tracks": len(state.tracks),
                    "reason": decision.reason,
                },
            )

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
    return 1 if failure is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
