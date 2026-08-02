from __future__ import annotations

import os
import sys
import time
from collections import deque
from pathlib import Path

from .pr27_native_grid import KnownSpriteRegistry, PR27CombatSystem
from .pr27_overlay import PR27DebugOverlay
from .pr27_post_ko import configure_post_engine, run_post_ko
from .pr27_pre_trainer_baseline import TRAINER_BBOX_ENV, baseline_path
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


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    return max(minimum, int(os.environ.get(name, str(default))))


def _float_env(name: str, default: float, minimum: float = 0.0) -> float:
    return max(minimum, float(os.environ.get(name, str(default))))


def _stage(name: str, **values: object) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in values.items())
    print(f"PR27_STAGE stage={name}{(' ' + suffix) if suffix else ''}", flush=True)


def _parse_bbox(value: str | None) -> tuple[int, int, int, int] | None:
    if not value:
        return None
    try:
        values = tuple(int(part.strip()) for part in value.split(","))
    except (TypeError, ValueError):
        return None
    if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
        return None
    return values


def _trainer_exclusion_local(
    combat: PR27CombatSystem,
    native_frame,
    trainer_bbox: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int] | None:
    if trainer_bbox is None:
        return None
    rect, arena = combat.cropper.crop(native_frame)
    x, y, width, height = trainer_bbox
    left_margin = _int_env("KAGE_PR27_TRAINER_MARGIN_LEFT", 48, 0)
    right_margin = _int_env("KAGE_PR27_TRAINER_MARGIN_RIGHT", 48, 0)
    top_margin = _int_env("KAGE_PR27_TRAINER_MARGIN_TOP", 96, 0)
    bottom_margin = _int_env("KAGE_PR27_TRAINER_MARGIN_BOTTOM", 20, 0)
    left = max(0, x - rect.x - left_margin)
    top = max(0, y - rect.y - top_margin)
    right = min(arena.shape[1], x + width - rect.x + right_margin)
    bottom = min(arena.shape[0], y + height - rect.y + bottom_margin)
    if right <= left or bottom <= top:
        return None
    return left, top, right - left, bottom - top


def _mask_trainer_with_baseline(
    combat: PR27CombatSystem,
    native_frame,
    exclusion: tuple[int, int, int, int] | None,
):
    if exclusion is None:
        return native_frame
    sanitized = native_frame.copy()
    rect, arena = combat.cropper.crop(sanitized)
    left, top, width, height = exclusion
    right, bottom = left + width, top + height
    cells = combat.grid.build(arena.shape)
    for cell in cells:
        overlap_left = max(left, cell.x)
        overlap_top = max(top, cell.y)
        overlap_right = min(right, cell.x + cell.width)
        overlap_bottom = min(bottom, cell.y + cell.height)
        if overlap_right <= overlap_left or overlap_bottom <= overlap_top:
            continue
        baseline = combat.baselines.get(cell)
        if baseline is None or not baseline.valid:
            continue
        source_left = overlap_left - cell.x
        source_top = overlap_top - cell.y
        source_right = overlap_right - cell.x
        source_bottom = overlap_bottom - cell.y
        arena[overlap_top:overlap_bottom, overlap_left:overlap_right] = baseline.image[
            source_top:source_bottom,
            source_left:source_right,
        ]
    return sanitized


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
    physical_mode = mode in {"FACE_ONLY", "CONTROL_ENABLED"}
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
        recover_foreground=physical_mode,
        debug=bool(args.debug_input) or physical_mode,
        repeat_delay_seconds=0.35,
        repeat_interval_seconds=0.05,
    )
    physical = PR27PhysicalInput(controller, sleep_fn=interruptible_sleep)
    log_handle, report_root, round_stem = create_log(args, __file__)
    overlay = PR27DebugOverlay()
    debug_root = report_root / "pr27_debug" / round_stem
    overlay_requested = bool_env("KAGE_PR27_DEBUG_OVERLAY", False)
    overlay_enabled = overlay_requested and not physical_mode
    save_debug = bool_env("KAGE_PR27_SAVE_DEBUG_FRAMES", False)
    overlay_every_frames = _int_env("KAGE_PR27_OVERLAY_EVERY_FRAMES", 3)
    save_every_frames = _int_env("KAGE_PR27_SAVE_EVERY_FRAMES", 80)
    log_every_frames = _int_env("KAGE_PR27_LOG_EVERY_FRAMES", 2)
    target_fps = min(20.0, _float_env("KAGE_PR27_TARGET_FPS", 8.0, 1.0))

    interval = 1.0 / target_fps
    telemetry_interval = max(0.10, float(args.telemetry_seconds))
    chat_poll_interval = max(0.10, min(2.0, float(args.chat_poll_seconds)))
    combat_seconds = max(1.0, float(args.seconds))
    post_timeout = max(5.0, float(args.post_combat_timeout))
    move_pulse_seconds = max(0.03, min(0.14, float(args.move_pulse)))
    v_pulse_seconds = max(0.03, min(0.20, float(args.v_pulse)))

    print("KAGE COMBAT LAB - PR27 NATIVE GRID SPRITE COMBAT", flush=True)
    print("PR27 CONTRACT: native frame -> arena -> native 64px cells -> per-cell baseline", flush=True)
    print("PR27 CLUSTER: search addresses only; no identity, direction, hostility or target authority", flush=True)
    print("PR27 IDENTITY: SpriteFragment -> SpriteObservation -> TrackedSprite ID", flush=True)
    print(f"PR27 MODE={mode}; known_sprite_references={len(registry.sprites)}", flush=True)
    print(f"PR27 BASELINE={baseline_path()}", flush=True)
    print(
        f"PR27 PERFORMANCE target_fps={target_fps:.1f} overlay_every={overlay_every_frames} "
        f"save_every={save_every_frames} log_every={log_every_frames}",
        flush=True,
    )
    if not registry.sprites:
        print(
            "PR27_CONTEXT_ENEMY_SELECTION=COMPETITIVE_PERSISTENCE_SHAPE_SIZE_MOTION; "
            "first-track-wins disabled",
            flush=True,
        )
    if overlay_requested and physical_mode:
        print(
            "PR27_OVERLAY_DISABLED mode=PHYSICAL reason=prevent_foreground_theft_and_cv_wait_block; "
            "console_and_optional_png_debug_remain_active",
            flush=True,
        )

    frames = 0
    started = 0.0
    victory_signal = None
    post_ready = False
    emergency_stop = False
    failure: Exception | None = None
    last_state: str | None = None
    last_action: str | None = None
    last_actions: tuple[str, ...] | None = None
    rolling_durations: deque[float] = deque(maxlen=32)
    trainer_bbox = _parse_bbox(os.environ.get(TRAINER_BBOX_ENV))
    trainer_exclusion = None

    try:
        _stage("INPUT_ACTIVATE_BEGIN", mode=mode, recover_foreground=physical_mode)
        armed_actions = physical.activate(mode=mode)
        print(
            f"PR27_PHYSICAL_ARMED mode={mode} physical={','.join(armed_actions)}",
            flush=True,
        )
        _stage("INPUT_ACTIVATE_DONE")

        startup_delay = max(0.0, float(args.startup_delay))
        if startup_delay > 0.0:
            _stage("STARTUP_DELAY", seconds=f"{startup_delay:.2f}")
            interruptible_sleep(startup_delay)

        _stage("FIRST_CAPTURE_BEGIN")
        first_native = source.capture_native()
        _stage(
            "FIRST_CAPTURE_DONE",
            native=f"{first_native.source_width}x{first_native.source_height}",
        )
        _stage("BASELINE_LOAD_BEGIN", path=baseline_path())
        loaded = combat.load_baseline(baseline_path(), first_native.bgr)
        metadata = combat.baselines.metadata
        expected_size = (metadata.get("frame_width"), metadata.get("frame_height"))
        actual_size = (first_native.source_width, first_native.source_height)
        if all(value is not None for value in expected_size):
            if tuple(int(value) for value in expected_size) != actual_size:
                raise RuntimeError(f"PR27_NATIVE_FRAME_SIZE_CHANGED:baseline={expected_size} current={actual_size}")
        print(f"PR27_BASELINE_LOADED cells={loaded} native={actual_size[0]}x{actual_size[1]}", flush=True)
        _stage("BASELINE_LOAD_DONE", cells=loaded)

        if trainer_bbox is None:
            metadata_bbox = metadata.get("trainer_bbox")
            if isinstance(metadata_bbox, list) and len(metadata_bbox) == 4:
                trainer_bbox = tuple(int(value) for value in metadata_bbox)
        trainer_exclusion = _trainer_exclusion_local(combat, first_native.bgr, trainer_bbox)
        if trainer_exclusion is None:
            print("PR27_TRAINER_EXCLUSION_INACTIVE reason=bbox_unavailable_or_outside_arena", flush=True)
        else:
            print(
                f"PR27_TRAINER_EXCLUSION_ACTIVE frame_bbox={trainer_bbox} "
                f"arena_bbox={trainer_exclusion} top_and_nameplate_masked=true",
                flush=True,
            )

        victory_watcher.prime()
        started = time.monotonic()
        next_telemetry = started
        next_chat_poll = started
        _stage("COMBAT_LOOP_ACTIVE", target_fps=f"{target_fps:.1f}")
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
                    print(f"PR27_ROUND_FINISHED victory_chat={victory_signal.text}", flush=True)
                    write_log(
                        log_handle,
                        {"event": "PR27_ROUND_FINISHED", "text": victory_signal.text},
                        flush=True,
                    )
                    break

            if frames == 0:
                _stage("FRAME0_PROCESS_BEGIN")
            native = first_native if frames == 0 else source.capture_native()
            sanitized_bgr = _mask_trainer_with_baseline(combat, native.bgr, trainer_exclusion)
            result = combat.process(sanitized_bgr, timestamp=now)
            if frames == 0:
                _stage(
                    "FRAME0_PROCESS_DONE",
                    state=result.state.value,
                    action=result.action.value,
                    tracks=len(result.tracks),
                )

            state_changed = result.state.value != last_state
            action_changed = result.action.value != last_action
            overlay_due = overlay_enabled and (frames % overlay_every_frames == 0 or state_changed)
            save_due = save_debug and (frames % save_every_frames == 0 or state_changed)
            if overlay_due or save_due:
                rendered = overlay.render(result)
                if overlay_due and not overlay.show(rendered):
                    raise EmergencyStop("PR27_DEBUG_WINDOW_CLOSED")
                if save_due:
                    overlay.save(rendered, debug_root / f"frame_{frames:06d}_{result.state.value}.png")

            actions = physical.execute(result.action, mode=mode)
            physical_changed = actions != last_actions

            loop_elapsed = time.monotonic() - loop_started
            rolling_durations.append(max(1e-6, loop_elapsed))
            rolling_fps = len(rolling_durations) / sum(rolling_durations)
            if physical_changed or action_changed:
                print(
                    f"PR27_PHYSICAL frame={frames:05d} mode={mode} planned={result.action.value} "
                    f"physical={','.join(actions)} target={result.target.track_id if result.target else '-'}",
                    flush=True,
                )
            if now >= next_telemetry:
                target_id = result.target.track_id if result.target else "-"
                changed = sum(item.state.value == "CHANGED" for item in result.differences.values())
                print(
                    f"PR27_FRAME frame={frames:05d} state={result.state.value} changed_cells={changed} "
                    f"groups={len(result.groups)} fragments={len(result.fragments)} tracks={len(result.tracks)} "
                    f"target={target_id} action={result.action.value} physical={','.join(actions)} "
                    f"rolling_fps={rolling_fps:.1f} loop_ms={loop_elapsed * 1000.0:.1f} reason={result.reason}",
                    flush=True,
                )
                next_telemetry = now + telemetry_interval
            if frames % log_every_frames == 0 or state_changed or action_changed or physical_changed:
                payload = frame_payload(
                    result=result,
                    native=native,
                    actions=actions,
                    frame=frames,
                    started=started,
                    now=now,
                )
                payload["trainer_exclusion_frame"] = None if trainer_bbox is None else list(trainer_bbox)
                payload["trainer_exclusion_arena"] = None if trainer_exclusion is None else list(trainer_exclusion)
                write_log(log_handle, payload)
            last_state = result.state.value
            last_action = result.action.value
            last_actions = actions
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
        print(f"PR27_STOP: {exc}", flush=True)
    except KeyboardInterrupt:
        emergency_stop = True
        print("PR27_STOP: KeyboardInterrupt", flush=True)
    except Exception as exc:
        failure = exc
        print(f"PR27_FAILURE {type(exc).__name__}: {exc}", flush=True)
        write_log(
            log_handle,
            {"event": "PR27_FAILURE", "type": type(exc).__name__, "error": str(exc)},
            flush=True,
        )
    finally:
        _stage("SHUTDOWN_BEGIN")
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
        log_handle.flush()
        log_handle.close()
        _stage("SHUTDOWN_DONE")

    duration = max(1e-6, time.monotonic() - started) if started else 0.0
    fps = frames / duration if duration else 0.0
    result_name = (
        "error" if failure is not None else
        "ready" if post_ready else
        "victory" if victory_signal else
        "stopped" if emergency_stop else
        "timeout"
    )
    performance_ready = fps >= 8.0
    print(
        f"PR27_FINISHED result={result_name} frames={frames} fps={fps:.1f} "
        f"performance_ready={str(performance_ready).lower()} required_fps=8.0",
        flush=True,
    )
    return 1 if failure is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
