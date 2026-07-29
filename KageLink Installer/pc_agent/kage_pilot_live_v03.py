from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
import time

from pc_agent.config import load_config
from pc_agent.kage_pilot.entity_observer import decode_jpeg
from pc_agent.kage_pilot.live_control_v03 import LiveCombatControlPlanner, MotionBurstGuard
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.particle_safe_grid_target_v03 import ParticleSafeGridTargetObserver
from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
    PersistentBackgroundWaterAwareEntityTracker,
)
from pc_agent.kage_pilot.pilot import WindowsGameController
from pc_agent.kage_pilot.post_combat_v03 import (
    ChatVictoryWatcher,
    DojoLeaderDetector,
    PostCombatRecoveryEngine,
)
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource
from pc_agent.kage_pilot.shadow_combat_v03 import ShadowCombatDecisionEngine


DEFAULT_PLAYER_X = 0.5181
DEFAULT_PLAYER_Y = 0.4706
DEFAULT_GRID_SIZE = 32.0
VK_F12 = 0x7B


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Kage Pilot v0.3 combat + authoritative chat victory + Dojo recovery / "
            "combate + vitoria pelo chat + recuperacao no Dojo"
        )
    )
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--fps", type=float, default=8.0)
    parser.add_argument("--telemetry-seconds", type=float, default=0.75)
    parser.add_argument("--startup-delay", type=float, default=3.0)
    parser.add_argument("--face-pulse", type=float, default=0.055)
    parser.add_argument("--move-pulse", type=float, default=0.09)
    parser.add_argument("--h-pulse", type=float, default=0.065)
    parser.add_argument("--h-settle", type=float, default=0.55)
    parser.add_argument("--disable-h", action="store_true")
    parser.add_argument("--face-refresh", type=float, default=0.45)
    parser.add_argument("--move-confirm-frames", type=int, default=2)
    parser.add_argument("--move-no-progress", type=float, default=1.15)
    parser.add_argument("--move-cooldown", type=float, default=0.55)
    parser.add_argument("--burst-hold", type=float, default=0.75)
    parser.add_argument("--burst-min-active-cells", type=int, default=18)
    parser.add_argument("--burst-min-entities", type=int, default=20)
    parser.add_argument("--player-x", type=float, default=DEFAULT_PLAYER_X)
    parser.add_argument("--player-y", type=float, default=DEFAULT_PLAYER_Y)
    parser.add_argument("--player-box-width", type=float, default=18.0)
    parser.add_argument("--player-box-height", type=float, default=38.0)
    parser.add_argument("--grid-size", type=float, default=DEFAULT_GRID_SIZE)
    parser.add_argument("--target-acquire", type=float, default=55.0)
    parser.add_argument("--target-keep", type=float, default=38.0)
    parser.add_argument("--track-ttl", type=float, default=2.0)
    parser.add_argument("--match-distance", type=float, default=105.0)
    parser.add_argument("--background-similarity", type=float, default=0.88)
    parser.add_argument("--background-min-hits", type=float, default=8.0)
    parser.add_argument("--background-min-age", type=float, default=0.8)
    parser.add_argument("--reacquire-ttl", type=float, default=5.0)
    parser.add_argument("--reacquire-distance", type=float, default=180.0)
    parser.add_argument("--reacquire-similarity", type=float, default=0.82)
    parser.add_argument("--contact-lock-seconds", type=float, default=2.8)
    parser.add_argument("--contact-confirm-frames", type=int, default=2)
    parser.add_argument("--h-stable-seconds", type=float, default=0.60)
    parser.add_argument("--h-cooldown", type=float, default=2.0)
    parser.add_argument("--h-min-score", type=float, default=55.0)
    parser.add_argument("--engagement-gap", type=float, default=0.75)

    # Authoritative victory + post-combat recovery.
    parser.add_argument("--chat-poll-seconds", type=float, default=0.25)
    parser.add_argument("--disable-post-combat", action="store_true")
    parser.add_argument("--post-combat-timeout", type=float, default=120.0)
    parser.add_argument("--leader-threshold", type=float, default=0.72)
    parser.add_argument("--leader-confirm-frames", type=int, default=2)
    parser.add_argument("--recovery-hp", type=float, default=0.90)
    parser.add_argument("--recovery-chakra", type=float, default=0.50)
    parser.add_argument("--recovery-confirm-frames", type=int, default=3)
    parser.add_argument("--v-pulse", type=float, default=0.08)

    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--debug-input", action="store_true")
    return parser


def _f12_pressed() -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_F12) & 0x8000)
    except Exception:
        return False


def _decision_line(decision, command, burst_state) -> str:
    target = f"#{decision.target_id:03d}" if decision.target_id is not None else "none"
    held = "+".join(command.held_keys) or "-"
    face = command.face_pulse or "-"
    move = command.move_pulse or "-"
    if command.h_fire:
        h_text = "H_FIRE"
    elif command.h_shadow_ready:
        h_text = "H_READY"
    else:
        h_text = "H_WAIT"
    return (
        f"LIVE {decision.mode} target={target} nav={decision.navigation} "
        f"held={held} move_pulse={move} face_pulse={face} {h_text} "
        f"safety={command.safety_state} cells={burst_state.active_cells} entities={burst_state.entities} "
        f"engaged={decision.engagement_stable_seconds:.1f}s"
    )


def _post_line(decision) -> str:
    leader_score = "-" if decision.leader_score is None else f"{decision.leader_score:.3f}"
    leader_distance = "-" if decision.leader_distance is None else str(decision.leader_distance)
    hp = "-" if decision.health is None else f"{decision.health * 100:.0f}%"
    chakra = "-" if decision.chakra is None else f"{decision.chakra * 100:.0f}%"
    move = decision.move_pulse or "-"
    v_text = "V_TAP" if decision.tap_v else "V_WAIT"
    return (
        f"POST {decision.state} leader_score={leader_score} d={leader_distance} "
        f"move_pulse={move} {v_text} HP={hp} Chakra={chakra} reason={decision.reason}"
    )


def main() -> int:
    args = build_parser().parse_args()
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
        reacquire_ttl=args.reacquire_ttl,
        reacquire_distance=args.reacquire_distance,
        reacquire_similarity=args.reacquire_similarity,
    ).normalized()

    observer = ParticleSafeGridTargetObserver(
        observer_config,
        tile_size=args.grid_size,
        contact_lock_seconds=args.contact_lock_seconds,
        show_grid=False,
        contact_confirm_frames=args.contact_confirm_frames,
    )
    tracker = PersistentBackgroundWaterAwareEntityTracker(observer_config)
    observer.tracker = tracker
    engine = ShadowCombatDecisionEngine(
        h_stable_seconds=args.h_stable_seconds,
        h_cooldown_seconds=args.h_cooldown,
        h_min_score=args.h_min_score,
        engagement_gap_seconds=args.engagement_gap,
        combat_active_on_start=True,
    )
    planner = LiveCombatControlPlanner(
        face_refresh_seconds=args.face_refresh,
        move_confirm_frames=args.move_confirm_frames,
        max_no_progress_seconds=args.move_no_progress,
        no_progress_cooldown_seconds=args.move_cooldown,
        h_enabled=not bool(args.disable_h),
    )
    burst_guard = MotionBurstGuard(
        hold_seconds=args.burst_hold,
        min_active_cells=args.burst_min_active_cells,
        min_entities=args.burst_min_entities,
    )

    app_config = load_config()
    victory_watcher = ChatVictoryWatcher(app_config.game_title, app_config.chat_class)
    post_engine = PostCombatRecoveryEngine(
        leader_detector=DojoLeaderDetector(threshold=args.leader_threshold),
        leader_confirm_frames=args.leader_confirm_frames,
        health_target=args.recovery_hp,
        chakra_target=args.recovery_chakra,
        recovery_confirm_frames=args.recovery_confirm_frames,
    )

    source = WindowsGameFrameSource()
    controller = WindowsGameController(recover_foreground=False, debug=bool(args.debug_input))
    controller.repeat_keys = {"r"}

    log_handle = None
    if args.log is not None:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.log.open("w", encoding="utf-8")

    interval = 1.0 / max(1.0, min(20.0, float(args.fps)))
    telemetry_interval = max(0.1, float(args.telemetry_seconds))
    chat_poll_interval = max(0.10, min(2.0, float(args.chat_poll_seconds)))
    startup_delay = max(0.0, float(args.startup_delay))
    face_pulse_seconds = max(0.02, min(0.12, float(args.face_pulse)))
    move_pulse_seconds = max(0.03, min(0.14, float(args.move_pulse)))
    h_pulse_seconds = max(0.03, min(0.12, float(args.h_pulse)))
    h_settle_seconds = max(0.20, min(1.50, float(args.h_settle)))
    v_pulse_seconds = max(0.03, min(0.20, float(args.v_pulse)))
    combat_seconds = max(1.0, float(args.seconds))
    post_timeout = max(5.0, float(args.post_combat_timeout))

    print("Kage Pilot v0.3 LIVE CONTROL - FULL DOJO RECOVERY GATE")
    print("VICTORY: authoritative chat phrase / frase autoritativa: 'has been Knocked-Out'")
    print("REAL INPUT: R + dead-man arrows + guarded H; POST: arrows + V toggle")
    print("F12 = EMERGENCY STOP / PARADA IMEDIATA")
    print(
        f"GRID={observer.tile_size:.0f}px combat_timeout={combat_seconds:.1f}s "
        f"PLAYER=({observer_config.player_x:.4f},{observer_config.player_y:.4f}) "
        f"recovery=HP>={args.recovery_hp*100:.0f}% Chakra>={args.recovery_chakra*100:.0f}% "
        f"leader_threshold={args.leader_threshold:.2f}"
    )

    frames = 0
    started = 0.0
    next_telemetry = 0.0
    next_chat_poll = 0.0
    h_settle_until = -1e9
    victory_signal = None
    emergency_stop = False
    post_ready = False

    try:
        controller.activate()
        controller.release_all()
        if startup_delay > 0:
            print(
                "Shinobi Story Online em foco / in foreground; "
                f"controle inicia em / control starts in {startup_delay:.1f}s"
            )
            time.sleep(startup_delay)

        # Everything already in chat before this point is historical and cannot end this fight.
        victory_watcher.prime()

        started = time.monotonic()
        next_telemetry = started
        next_chat_poll = started

        while time.monotonic() - started < combat_seconds:
            loop_started = time.monotonic()
            if _f12_pressed():
                print("F12 STOP / PARADA F12")
                emergency_stop = True
                break

            now = time.monotonic()
            if now >= next_chat_poll:
                victory_signal = victory_watcher.poll()
                next_chat_poll = now + chat_poll_interval
                if victory_signal is not None:
                    # Authoritative KO: stop every combat key before doing anything else.
                    controller.release_all()
                    print(f"VICTORY_CHAT / VITORIA_CHAT: {victory_signal.text}")
                    if log_handle is not None:
                        log_handle.write(json.dumps({
                            "t": round(now - started, 4),
                            "event": "victory_chat",
                            "text": victory_signal.text,
                        }, ensure_ascii=False) + "\n")
                    break

            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            state = observer.process(frame)
            now = time.monotonic()

            burst_state = burst_guard.update(
                active_cells=observer.active_grid_cells,
                entities=len(state.tracks),
                now=now,
            )
            h_settling = now < h_settle_until
            action_allowed = not burst_state.blocked and not h_settling
            if h_settling:
                block_reason = f"h_settle_remaining={max(0.0, h_settle_until - now):.2f}s"
            else:
                block_reason = burst_state.reason

            decision = engine.decide(
                state,
                observer,
                tracker,
                now=now,
                skills_allowed=action_allowed,
            )
            command = planner.plan(
                decision,
                now=now,
                movement_allowed=action_allowed,
                block_reason=block_reason,
            )

            # Dead-man invariant: every loop returns to base state before a pulse.
            controller.apply_keys(command.held_keys)

            if command.move_pulse is not None:
                pulse_keys = tuple(sorted(set(command.held_keys).union({command.move_pulse})))
                controller.apply_keys(pulse_keys)
                time.sleep(move_pulse_seconds)
                controller.apply_keys(command.held_keys)
            else:
                if command.face_pulse is not None:
                    pulse_keys = tuple(sorted(set(command.held_keys).union({command.face_pulse})))
                    controller.apply_keys(pulse_keys)
                    time.sleep(face_pulse_seconds)
                    controller.apply_keys(command.held_keys)

                if command.h_fire:
                    h_keys = tuple(sorted(set(command.held_keys).union({"h"})))
                    controller.apply_keys(h_keys)
                    time.sleep(h_pulse_seconds)
                    controller.apply_keys(command.held_keys)
                    h_settle_until = time.monotonic() + h_settle_seconds

            if now >= next_telemetry:
                print(_decision_line(decision, command, burst_state) + f" reason={command.reason}")
                next_telemetry = now + telemetry_interval

            if log_handle is not None:
                row = {
                    "t": round(now - started, 4),
                    "phase": "combat",
                    "target_id": decision.target_id,
                    "mode": decision.mode,
                    "navigation": decision.navigation,
                    "face": decision.face,
                    "held_keys": list(command.held_keys),
                    "move_pulse": command.move_pulse,
                    "face_pulse": command.face_pulse,
                    "h_ready": command.h_shadow_ready,
                    "h_fire": command.h_fire,
                    "h_settling": h_settling,
                    "grid_distance": decision.grid_distance,
                    "engagement_stable_seconds": round(decision.engagement_stable_seconds, 4),
                    "safety_state": command.safety_state,
                    "active_grid_cells": burst_state.active_cells,
                    "entities": len(state.tracks),
                    "burst_blocked": burst_state.blocked,
                    "burst_reason": burst_state.reason,
                    "reason": command.reason,
                }
                log_handle.write(json.dumps(row, ensure_ascii=False) + "\n")

            frames += 1
            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                time.sleep(interval - elapsed)

        if (
            victory_signal is not None
            and not emergency_stop
            and not bool(args.disable_post_combat)
        ):
            # R/H/arrows are already released by the victory transition. Post-combat never
            # re-enables R; it owns only dead-man arrows and the V toggle.
            controller.release_all()
            print("POST_COMBAT / POS-COMBATE: SEEK_DOJO_LEADER")
            post_started = time.monotonic()
            next_post_telemetry = post_started

            while time.monotonic() - post_started < post_timeout:
                loop_started = time.monotonic()
                if _f12_pressed():
                    print("F12 STOP during post-combat / PARADA F12 no pos-combate")
                    emergency_stop = True
                    break

                captured = source.capture()
                frame = decode_jpeg(bytes(captured.jpeg))
                state = observer.process(frame)
                now = time.monotonic()
                post = post_engine.step(frame, state, observer, now=now)

                # Post-combat has no persistent key state at all.
                controller.apply_keys(())

                if post.move_pulse is not None:
                    controller.apply_keys((post.move_pulse,))
                    time.sleep(move_pulse_seconds)
                    controller.apply_keys(())

                if post.tap_v:
                    controller.tap("v", v_pulse_seconds)

                if now >= next_post_telemetry:
                    print(_post_line(post))
                    next_post_telemetry = now + telemetry_interval

                if log_handle is not None:
                    log_handle.write(json.dumps({
                        "t": round(now - post_started, 4),
                        "phase": "post_combat",
                        "state": post.state,
                        "move_pulse": post.move_pulse,
                        "tap_v": post.tap_v,
                        "leader_score": post.leader_score,
                        "leader_distance": post.leader_distance,
                        "health": post.health,
                        "chakra": post.chakra,
                        "reason": post.reason,
                    }, ensure_ascii=False) + "\n")

                frames += 1
                if post.state == "READY":
                    post_ready = True
                    print("READY / PRONTO: HP and Chakra recovery thresholds reached")
                    break

                elapsed = time.monotonic() - loop_started
                if elapsed < interval:
                    time.sleep(interval - elapsed)

            if not post_ready and not emergency_stop:
                print(
                    f"POST_COMBAT_TIMEOUT state={post_engine.state} / "
                    f"TIMEOUT_POS_COMBATE estado={post_engine.state}"
                )
                # Timeout is not an emergency stop. If this runtime itself started meditation,
                # toggle V off so it does not leave the game in an ambiguous persistent state.
                if post_engine.state == "MEDITATING":
                    controller.tap("v", v_pulse_seconds)
                    print("V OFF after post-combat timeout / V OFF apos timeout")

    except KeyboardInterrupt:
        print("Keyboard interrupt / interrupcao de teclado")
    except Exception as exc:
        print(f"LIVE CONTROL STOPPED / CONTROLE INTERROMPIDO: {type(exc).__name__}: {exc}")
    finally:
        controller.release_all()
        source.close()
        if log_handle is not None:
            log_handle.close()

    duration = max(1e-6, time.monotonic() - started) if started else 0.0
    fps = frames / duration if duration > 0 else 0.0
    result = (
        "ready" if post_ready else
        "victory" if victory_signal is not None else
        "stopped" if emergency_stop else
        "timeout"
    )
    print(f"Live stopped / Controle encerrado: result={result} frames={frames} fps={fps:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
