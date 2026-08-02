from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from .pr27_native_grid import KnownSpriteRegistry, PR27CombatSystem
from .pr27_overlay import PR27DebugOverlay
from .pr27_post_ko import configure_post_engine, run_post_ko
from .pr27_pre_trainer_baseline import baseline_path
from .pr27_runtime_logging import frame_payload
from .pr27_runtime_support import (
    EmergencyStop,
    PR27PhysicalInput,
    bool_env,
    config_from_env,
    control_mode,
    create_log,
    write_log,
)


def main() -> int:
    import kage_pilot_live_v03 as live_runtime
    import kage_pilot_live_v03k_round as validated_round
    from pc_agent.game_capture import GameCapture

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

    mode = control_mode()
    config = config_from_env()
    registry = KnownSpriteRegistry.from_directory(
        Path(os.environ.get("KAGE_PR27_SPRITE_ROOT", "data/pr27_sprites"))
    )
    combat = PR27CombatSystem(config=config, registry=registry)
    app_config = live_runtime.load_config()
    victory_watcher = live_runtime.ChatVictoryWatcher(app_config.game_title, app_config.chat_class)
    post_engine = configure_post_engine(live_runtime, args)
    source = GameCapture()
    controller = live_runtime.WindowsGameController(
        recover_foreground=False,
        debug=bool(args.debug_input),
        repeat_delay_seconds=0.25,
        repeat_interval_seconds=0.25,
    )
    physical = PR27PhysicalInput(controller, sleep_fn=interruptible_sleep)
    log_handle, report_root, round_stem = create_log(args, __file__)
    overlay = PR27DebugOverlay()
    debug_root = report_root / "pr27_debug" / round_stem
    overlay_enabled = bool_env("KAGE_PR27_DEBUG_OVERLAY", False)
    save_debug = bool_env("KAGE_PR27_SAVE_DEBUG_FRAMES", True)

    interval = 1.0 / max(1.0, min(20.0, float(args.fps)))
    telemetry_interval = max(0.10, float(args.telemetry_seconds))
    chat_poll_interval = max(0.10, min(2.0, float(args.chat_poll_seconds)))
    combat_seconds = max(1.0, float(args.seconds))
    post_timeout = max(5.0, float(args.post_combat_timeout))
    move_pulse_seconds = max(0.03, min(0.14, float(args.move_pulse)))
    v_pulse_seconds = max(0.03, min(0.20, float(args.v_pulse)))

    print("KAGE COMBAT LAB - PR27 NATIVE GRID SPRITE COMBAT")
    print("PR27 CONTRACT: native frame -> arena -> native 64px cells -> per-cell baseline")
    print("PR27 CLUSTER: search addresses only; no identity, direction, hostility or target authority")
    print("PR27 IDENTITY: SpriteFragment -> SpriteObservation -> TrackedSprite ID")
    print(f"PR27 MODE={mode}; known_sprite_references={len(registry.sprites)}")
    print(f"PR27 BASELINE={baseline_path()}")

    frames = 0
    started = 0.0
    victory_signal = None
    post_ready = False
    emergency_stop = False
    failure: Exception | None = None
    last_saved_state = None

    try:
        physical.activate()
        interruptible_sleep(max(0.0, float(args.startup_delay)))
        first_native = source.capture_native()
        loaded = combat.load_baseline(baseline_path(), first_native.bgr)
        metadata = combat.baselines.metadata
        expected_size = (metadata.get("frame_width"), metadata.get("frame_height"))
        actual_size = (first_native.source_width, first_native.source_height)
        if all(value is not None for value in expected_size):
            if tuple(int(value) for value in expected_size) != actual_size:
                raise RuntimeError(f"PR27_NATIVE_FRAME_SIZE_CHANGED:baseline={expected_size} current={actual_size}")
        print(f"PR27_BASELINE_LOADED cells={loaded} native={actual_size[0]}x{actual_size[1]}")

        victory_watcher.prime()
        started = time.monotonic()
        next_telemetry = started
        next_chat_poll = started
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
                    print(f"PR27_ROUND_FINISHED victory_chat={victory_signal.text}")
                    write_log(log_handle, {"event": "PR27_ROUND_FINISHED", "text": victory_signal.text})
                    break

            native = first_native if frames == 0 else source.capture_native()
            result = combat.process(native.bgr, timestamp=now)
            actions = physical.execute(result.action, mode=mode)
            rendered = overlay.render(result)
            if overlay_enabled and not overlay.show(rendered):
                raise EmergencyStop("PR27_DEBUG_WINDOW_CLOSED")
            if save_debug and (frames % 20 == 0 or last_saved_state != result.state.value):
                overlay.save(rendered, debug_root / f"frame_{frames:06d}_{result.state.value}.png")
                last_saved_state = result.state.value

            if now >= next_telemetry:
                target_id = result.target.track_id if result.target else "-"
                changed = sum(item.state.value == "CHANGED" for item in result.differences.values())
                print(
                    f"PR27_FRAME frame={frames:05d} state={result.state.value} changed_cells={changed} "
                    f"groups={len(result.groups)} fragments={len(result.fragments)} tracks={len(result.tracks)} "
                    f"target={target_id} action={result.action.value} reason={result.reason}"
                )
                next_telemetry = now + telemetry_interval
            write_log(log_handle, frame_payload(
                result=result,
                native=native,
                actions=actions,
                frame=frames,
                started=started,
                now=now,
            ))
            frames += 1
            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                interruptible_sleep(interval - elapsed)

        if victory_signal is not None and not bool(args.disable_post_combat):
            controller.release_all()
            source.close()
            post_ready = run_post_ko(
                args=args,
                live_runtime=live_runtime,
                controller=controller,
                log_handle=log_handle,
                post_engine=post_engine,
                post_timeout=post_timeout,
                telemetry_interval=telemetry_interval,
                interval=interval,
                move_pulse_seconds=move_pulse_seconds,
                v_pulse_seconds=v_pulse_seconds,
                f12_pressed=f12_pressed,
                interruptible_sleep=interruptible_sleep,
            )
    except EmergencyStop as exc:
        emergency_stop = True
        print(f"PR27_STOP: {exc}")
    except KeyboardInterrupt:
        emergency_stop = True
        print("PR27_STOP: KeyboardInterrupt")
    except Exception as exc:
        failure = exc
        print(f"PR27_FAILURE {type(exc).__name__}: {exc}")
        write_log(log_handle, {"event": "PR27_FAILURE", "type": type(exc).__name__, "error": str(exc)})
    finally:
        try:
            physical.close()
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
        overlay.close()
        log_handle.close()

    duration = max(1e-6, time.monotonic() - started) if started else 0.0
    fps = frames / duration if duration else 0.0
    result_name = (
        "error" if failure is not None else
        "ready" if post_ready else
        "victory" if victory_signal else
        "stopped" if emergency_stop else
        "timeout"
    )
    print(f"PR27_FINISHED result={result_name} frames={frames} fps={fps:.1f}")
    return 1 if failure is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
