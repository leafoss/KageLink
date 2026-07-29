from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2

from pc_agent.kage_pilot.entity_observer import (
    EntityObserver,
    ObserverConfig,
    decode_jpeg,
    render_overlay,
)
from pc_agent.kage_pilot.recorder import WindowsAsyncInputSource, WindowsGameFrameSource


WINDOW_TITLE = "Kage Pilot v0.3 - Entity Observer"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kage Pilot v0.3 read-only entity observer / observador de entidades somente leitura"
    )
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--enemy-threshold", type=float, default=55.0)
    parser.add_argument("--player-x", type=float, default=0.50, help="Player anchor X inside arena, normalized")
    parser.add_argument("--player-y", type=float, default=0.55, help="Player anchor Y inside arena, normalized")
    parser.add_argument("--player-radius", type=float, default=26.0)
    parser.add_argument("--arena-left", type=float, default=0.04)
    parser.add_argument("--arena-top", type=float, default=0.04)
    parser.add_argument("--arena-right", type=float, default=0.96)
    parser.add_argument("--arena-bottom", type=float, default=0.86)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--log", help="Optional JSONL entity log / Log JSONL opcional")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = ObserverConfig(
        arena_left=args.arena_left,
        arena_top=args.arena_top,
        arena_right=args.arena_right,
        arena_bottom=args.arena_bottom,
        player_x=args.player_x,
        player_y=args.player_y,
        player_exclusion_radius=args.player_radius,
        enemy_threshold=args.enemy_threshold,
    ).normalized()

    frame_source = WindowsGameFrameSource()
    input_source = WindowsAsyncInputSource(excluded_keys=())
    observer = EntityObserver(config)
    interval = 1.0 / max(1.0, min(30.0, float(args.fps)))

    log_handle = None
    if args.log:
        log_path = Path(args.log).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("a", encoding="utf-8")
        print(f"log={log_path}")

    print("Kage Pilot v0.3 ENTITY OBSERVER")
    print("READ ONLY / SOMENTE OBSERVACAO - nenhuma tecla de jogo sera enviada / no game keys will be sent")
    print("F10 = stop / parar | Q ou ESC na preview = stop / parar")
    print(
        "pipeline=CLAHE+contours+Lucas-Kanade+global-flow-compensation+tracking+temporal-memory+enemy-score"
    )

    if not args.no_preview:
        cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_TITLE, 1320, 720)

    next_tick = time.monotonic()
    last_console_at = 0.0
    last_console_signature = None
    try:
        while True:
            now = time.monotonic()
            if now < next_tick:
                time.sleep(min(0.01, next_tick - now))
                continue
            next_tick = now + interval

            frame = frame_source.capture()
            bgr = decode_jpeg(bytes(frame.jpeg))
            state = observer.process(bgr, timestamp=now)

            if log_handle is not None:
                payload = {
                    "timestamp": now,
                    "global_flow": {
                        "dx": round(state.global_flow.dx, 3),
                        "dy": round(state.global_flow.dy, 3),
                        "points": state.global_flow.points,
                        "residual_median": round(state.global_flow.residual_median, 3),
                    },
                    "player_center": [round(state.player_center[0], 2), round(state.player_center[1], 2)],
                    "target_id": state.target_id,
                    "entities": [track.to_dict(state.player_center, now=now) for track in state.tracks],
                }
                log_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                log_handle.flush()

            target = state.target
            signature = (
                state.target_id,
                round(target.enemy_score, 0) if target is not None else None,
                bool(target.approaching_player) if target is not None else None,
                len(state.tracks),
            )
            if signature != last_console_signature or now - last_console_at >= 1.0:
                if target is None:
                    print(
                        f"OBS entities={len(state.tracks)} target=- "
                        f"flow=({state.global_flow.dx:+.1f},{state.global_flow.dy:+.1f}) "
                        f"lk={state.global_flow.points}"
                    )
                else:
                    info = target.to_dict(state.player_center, now=now)
                    print(
                        f"OBS target=ENTITY#{target.track_id:03d} score={target.enemy_score:.0f}% "
                        f"pos=({target.center[0]:.0f},{target.center[1]:.0f}) "
                        f"dist={info['distance_to_player']:.0f}px speed={target.residual_speed:.1f}px/s "
                        f"dir={info['direction']} approach={'yes' if target.approaching_player else 'no'}"
                    )
                last_console_signature = signature
                last_console_at = now

            if not args.no_preview:
                overlay = render_overlay(bgr, state, config)
                cv2.imshow(WINDOW_TITLE, overlay)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    break

            if input_source.key_down("f10"):
                break
    except KeyboardInterrupt:
        pass
    finally:
        if log_handle is not None:
            log_handle.close()
        frame_source.close()
        if not args.no_preview:
            cv2.destroyAllWindows()

    print("STOP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
