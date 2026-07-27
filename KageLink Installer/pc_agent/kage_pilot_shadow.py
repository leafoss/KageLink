from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import cv2

from pc_agent.kage_pilot.entity_observer import decode_jpeg
from pc_agent.kage_pilot.grid_target_observer_v03d import TileCalibratedGridTargetObserver
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig, render_overlay_v03
from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
    PersistentBackgroundWaterAwareEntityTracker,
)
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource
from pc_agent.kage_pilot.shadow_combat_v03 import ShadowCombatDecisionEngine


DEFAULT_PLAYER_X = 0.5181
DEFAULT_PLAYER_Y = 0.4706
DEFAULT_GRID_SIZE = 32.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Kage Pilot v0.3 read-only shadow combat controller / "
            "controlador sombra de combate somente leitura"
        )
    )
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--telemetry-seconds", type=float, default=1.0)
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
    parser.add_argument("--no-grid-overlay", action="store_true")
    parser.add_argument("--arena-left", type=float, default=0.04)
    parser.add_argument("--arena-top", type=float, default=0.04)
    parser.add_argument("--arena-right", type=float, default=0.96)
    parser.add_argument("--arena-bottom", type=float, default=0.86)
    parser.add_argument("--window-name", default="Kage Pilot v0.3 - Shadow Combat")
    return parser


def _decision_text(decision) -> str:
    h_text = "H_READY" if decision.h_opportunity else "H_WAIT"
    r_text = "R_ON" if decision.base_r else "R_OFF"
    target = f"#{decision.target_id:03d}" if decision.target_id is not None else "none"
    return (
        f"SHADOW {decision.mode} target={target} "
        f"nav={decision.navigation} face={decision.face} {r_text} {h_text} "
        f"engaged={decision.engagement_stable_seconds:.1f}s"
    )


def main() -> int:
    args = build_parser().parse_args()
    config = V03ObserverConfig(
        arena_left=args.arena_left,
        arena_top=args.arena_top,
        arena_right=args.arena_right,
        arena_bottom=args.arena_bottom,
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
        show_grid=not bool(args.no_grid_overlay),
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
    source = WindowsGameFrameSource()

    interval = 1.0 / max(1.0, min(30.0, float(args.fps)))
    telemetry_interval = max(0.1, float(args.telemetry_seconds))
    started = time.monotonic()
    next_telemetry = started
    window_name = str(args.window_name)
    frames = 0
    log_handle = None

    if args.log is not None:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.log.open("w", encoding="utf-8")

    print("Kage Pilot v0.3 SHADOW COMBAT")
    print("READ ONLY / SOMENTE OBSERVACAO - NO KEYS / NENHUMA TECLA")
    print(
        f"GRID={observer.tile_size:.0f}px PLAYER=({config.player_x:.4f},{config.player_y:.4f}) "
        f"R session=ON H stable={engine.h_stable_seconds:.2f}s "
        f"cooldown={engine.h_cooldown_seconds:.1f}s gap={engine.engagement_gap_seconds:.2f}s"
    )
    print("Jogue manualmente / Fight manually. Q ou ESC = sair / exit")

    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    try:
        while args.seconds is None or time.monotonic() - started < float(args.seconds):
            loop_started = time.monotonic()
            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            state = observer.process(frame)
            now = time.monotonic()
            decision = engine.decide(state, observer, tracker, now=now)

            if now >= next_telemetry:
                print(_decision_text(decision) + f" reason={decision.reason}")
                next_telemetry = now + telemetry_interval

            if log_handle is not None:
                target = state.target
                metrics = observer.metrics_for(target.track_id) if target is not None else None
                row = {
                    "t": round(now - started, 4),
                    "target_id": decision.target_id,
                    "target_mode": observer.target_mode,
                    "decision_mode": decision.mode,
                    "navigation": decision.navigation,
                    "face": decision.face,
                    "base_r": decision.base_r,
                    "h_opportunity": decision.h_opportunity,
                    "engagement_active": decision.engagement_active,
                    "engagement_stable_seconds": round(decision.engagement_stable_seconds, 4),
                    "grid_distance": decision.grid_distance,
                    "target_score": None if target is None else round(float(target.enemy_score), 2),
                    "target_cell": None if metrics is None else list(metrics.cell),
                    "player_cell": None if metrics is None else list(metrics.player_cell),
                    "reason": decision.reason,
                }
                log_handle.write(json.dumps(row, ensure_ascii=False) + "\n")

            preview = render_overlay_v03(frame, state, config, tracker)
            preview = observer.draw_grid_overlay(preview, state)
            cv2.rectangle(preview, (8, 28), (min(preview.shape[1] - 8, 760), 58), (0, 0, 0), -1)
            cv2.putText(
                preview,
                _decision_text(decision),
                (14, 49),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (245, 245, 245),
                1,
                cv2.LINE_AA,
            )
            cv2.imshow(window_name, preview)
            frames += 1

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break

            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                time.sleep(interval - elapsed)
    except KeyboardInterrupt:
        pass
    finally:
        if log_handle is not None:
            log_handle.close()
        source.close()
        cv2.destroyAllWindows()

    duration = max(1e-6, time.monotonic() - started)
    print(f"Shadow stopped / Sombra encerrada: frames={frames} fps={frames / duration:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
