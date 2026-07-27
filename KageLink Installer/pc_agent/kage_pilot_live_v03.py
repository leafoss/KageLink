from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
import time

from pc_agent.kage_pilot.entity_observer import decode_jpeg
from pc_agent.kage_pilot.grid_target_observer_v03d import TileCalibratedGridTargetObserver
from pc_agent.kage_pilot.live_control_v03 import LiveCombatControlPlanner
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
    PersistentBackgroundWaterAwareEntityTracker,
)
from pc_agent.kage_pilot.pilot import WindowsGameController
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource
from pc_agent.kage_pilot.shadow_combat_v03 import ShadowCombatDecisionEngine


DEFAULT_PLAYER_X = 0.5181
DEFAULT_PLAYER_Y = 0.4706
DEFAULT_GRID_SIZE = 32.0
VK_F12 = 0x7B


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Kage Pilot v0.3 limited live combat control: R + movement only; H shadow-only / "
            "controle real limitado: R + movimento; H apenas sombra"
        )
    )
    parser.add_argument("--seconds", type=float, default=25.0)
    parser.add_argument("--fps", type=float, default=8.0)
    parser.add_argument("--telemetry-seconds", type=float, default=0.75)
    parser.add_argument("--startup-delay", type=float, default=3.0)
    parser.add_argument("--face-pulse", type=float, default=0.055)
    parser.add_argument("--face-refresh", type=float, default=0.45)
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
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--debug-input", action="store_true")
    return parser


def _f12_pressed() -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_F12) & 0x8000)
    except Exception:
        return False


def _decision_line(decision, command) -> str:
    target = f"#{decision.target_id:03d}" if decision.target_id is not None else "none"
    held = "+".join(command.held_keys) or "-"
    pulse = command.face_pulse or "-"
    h_text = "H_READY(SHADOW)" if command.h_shadow_ready else "H_WAIT"
    return (
        f"LIVE {decision.mode} target={target} nav={decision.navigation} "
        f"held={held} face_pulse={pulse} {h_text} "
        f"engaged={decision.engagement_stable_seconds:.1f}s"
    )


def main() -> int:
    args = build_parser().parse_args()
    config = V03ObserverConfig(
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

    observer = TileCalibratedGridTargetObserver(
        config,
        tile_size=args.grid_size,
        contact_lock_seconds=args.contact_lock_seconds,
        show_grid=False,
        contact_confirm_frames=args.contact_confirm_frames,
    )
    tracker = PersistentBackgroundWaterAwareEntityTracker(config)
    observer.tracker = tracker
    engine = ShadowCombatDecisionEngine(
        h_stable_seconds=args.h_stable_seconds,
        h_cooldown_seconds=args.h_cooldown,
        h_min_score=args.h_min_score,
        engagement_gap_seconds=args.engagement_gap,
        combat_active_on_start=True,
    )
    planner = LiveCombatControlPlanner(face_refresh_seconds=args.face_refresh)
    source = WindowsGameFrameSource()
    controller = WindowsGameController(recover_foreground=False, debug=bool(args.debug_input))
    controller.repeat_keys = {"r"}

    log_handle = None
    if args.log is not None:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.log.open("w", encoding="utf-8")

    interval = 1.0 / max(1.0, min(20.0, float(args.fps)))
    telemetry_interval = max(0.1, float(args.telemetry_seconds))
    startup_delay = max(0.0, float(args.startup_delay))
    face_pulse_seconds = max(0.02, min(0.12, float(args.face_pulse)))
    seconds = max(1.0, float(args.seconds))

    print("Kage Pilot v0.3 LIMITED LIVE CONTROL")
    print("REAL INPUT / CONTROLE REAL: R + ARROWS ONLY / SOMENTE R + SETAS")
    print("H remains SHADOW-ONLY / H continua APENAS SOMBRA")
    print("F12 = EMERGENCY STOP / PARADA IMEDIATA")
    print(
        f"GRID={observer.tile_size:.0f}px duration={seconds:.1f}s "
        f"PLAYER=({config.player_x:.4f},{config.player_y:.4f})"
    )

    frames = 0
    started = 0.0
    next_telemetry = 0.0
    try:
        controller.activate()
        controller.release_all()
        if startup_delay > 0:
            print(
                "Shinobi Story Online em foco / in foreground; "
                f"controle inicia em / control starts in {startup_delay:.1f}s"
            )
            time.sleep(startup_delay)

        started = time.monotonic()
        next_telemetry = started
        while time.monotonic() - started < seconds:
            loop_started = time.monotonic()
            if _f12_pressed():
                print("F12 STOP / PARADA F12")
                break

            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            state = observer.process(frame)
            now = time.monotonic()
            decision = engine.decide(state, observer, tracker, now=now)
            command = planner.plan(decision, now=now)

            if command.face_pulse is not None:
                pulse_keys = tuple(sorted(set(command.held_keys).union({command.face_pulse})))
                controller.apply_keys(pulse_keys)
                time.sleep(face_pulse_seconds)
                controller.apply_keys(command.held_keys)
            else:
                controller.apply_keys(command.held_keys)

            if now >= next_telemetry:
                print(_decision_line(decision, command) + f" reason={decision.reason}")
                next_telemetry = now + telemetry_interval

            if log_handle is not None:
                row = {
                    "t": round(now - started, 4),
                    "target_id": decision.target_id,
                    "mode": decision.mode,
                    "navigation": decision.navigation,
                    "face": decision.face,
                    "held_keys": list(command.held_keys),
                    "face_pulse": command.face_pulse,
                    "h_shadow_ready": command.h_shadow_ready,
                    "grid_distance": decision.grid_distance,
                    "engagement_stable_seconds": round(decision.engagement_stable_seconds, 4),
                    "reason": decision.reason,
                }
                log_handle.write(json.dumps(row, ensure_ascii=False) + "\n")

            frames += 1
            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                time.sleep(interval - elapsed)
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
    print(f"Live stopped / Controle encerrado: frames={frames} fps={fps:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
