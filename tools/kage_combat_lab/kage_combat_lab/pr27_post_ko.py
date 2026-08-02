from __future__ import annotations

import time

from .pr27_runtime_support import EmergencyStop, MIN_MEDITATION_SECONDS, write_log


def configure_post_engine(live_runtime, args):
    engine = live_runtime.PostCombatRecoveryEngine(
        leader_detector=live_runtime.DojoLeaderDetector(threshold=args.leader_threshold),
        leader_confirm_frames=args.leader_confirm_frames,
        health_target=args.recovery_hp,
        chakra_target=args.recovery_chakra,
        recovery_confirm_frames=args.recovery_confirm_frames,
    )
    engine.min_meditation_seconds = max(
        MIN_MEDITATION_SECONDS,
        float(getattr(engine, "min_meditation_seconds", 0.0) or 0.0),
    )
    return engine


def run_post_ko(
    *, args, live_runtime, controller, log_handle, post_engine, post_timeout: float,
    telemetry_interval: float, interval: float, move_pulse_seconds: float,
    v_pulse_seconds: float, f12_pressed, interruptible_sleep,
) -> bool:
    from pc_agent.kage_pilot.entity_observer import decode_jpeg
    from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
    from pc_agent.kage_pilot.persistent_water_tracker_v03 import PersistentBackgroundWaterAwareEntityTracker
    from pc_agent.kage_pilot.recorder import WindowsGameFrameSource

    observer_config = V03ObserverConfig(
        player_x=args.player_x,
        player_y=args.player_y,
        player_exclusion_radius=max(args.player_box_width, args.player_box_height) / 2.0,
        player_box_width=args.player_box_width,
        player_box_height=args.player_box_height,
    ).normalized()
    observer = live_runtime.ParticleSafeGridTargetObserver(observer_config, tile_size=64.0, show_grid=False)
    observer.tracker = PersistentBackgroundWaterAwareEntityTracker(observer_config)
    source = WindowsGameFrameSource()
    started = time.monotonic()
    next_telemetry = started
    try:
        while time.monotonic() - started < post_timeout:
            loop_started = time.monotonic()
            if f12_pressed():
                raise EmergencyStop("F12_STOP_POST_COMBAT")
            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            state = observer.process(frame, timestamp=loop_started)
            now = time.monotonic()
            post = post_engine.step(frame, state, observer, now=now)
            controller.apply_keys(())
            if post.move_pulse is not None:
                controller.apply_keys((post.move_pulse,))
                interruptible_sleep(move_pulse_seconds)
                controller.apply_keys(())
            if post.tap_v:
                controller.tap("v", v_pulse_seconds)
                print(f"PR27_MEDITATION V_TAP state={post.state} guard={post_engine.min_meditation_seconds:.2f}s")
            if now >= next_telemetry:
                print(live_runtime._post_line(post))
                next_telemetry = now + telemetry_interval
            write_log(log_handle, {
                "event": "PR27_POST_COMBAT",
                "state": post.state,
                "move_pulse": post.move_pulse,
                "tap_v": post.tap_v,
                "health": post.health,
                "chakra": post.chakra,
                "reason": post.reason,
            })
            if post.state == "READY":
                print("PR27_ROUND_RESTART READY")
                return True
            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                interruptible_sleep(interval - elapsed)
    finally:
        source.close()
    return False
