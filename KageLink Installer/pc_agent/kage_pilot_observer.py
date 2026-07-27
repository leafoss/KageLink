from __future__ import annotations

import argparse
import time

import cv2

from pc_agent.kage_pilot.entity_observer import (
    EntityObserver,
    ObserverConfig,
    decode_jpeg,
    render_overlay,
)
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Kage Pilot v0.3 read-only entity observer / "
            "observador de entidades somente leitura"
        )
    )
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--player-x", type=float, default=0.50)
    parser.add_argument("--player-y", type=float, default=0.55)
    parser.add_argument("--player-radius", type=float, default=26.0)
    parser.add_argument("--enemy-threshold", type=float, default=55.0)
    parser.add_argument("--arena-left", type=float, default=0.04)
    parser.add_argument("--arena-top", type=float, default=0.04)
    parser.add_argument("--arena-right", type=float, default=0.96)
    parser.add_argument("--arena-bottom", type=float, default=0.86)
    parser.add_argument("--window-name", default="Kage Pilot v0.3 - Entity Observer")
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

    observer = EntityObserver(config)
    source = WindowsGameFrameSource()
    interval = 1.0 / max(1.0, min(30.0, float(args.fps)))
    started = time.monotonic()
    frames = 0

    print("Kage Pilot v0.3 ENTITY OBSERVER")
    print("READ ONLY / SOMENTE OBSERVACAO")
    print("Nenhuma tecla sera enviada ao jogo / No key will be sent to the game")
    print("F10, Q ou ESC = sair / exit")

    try:
        while args.seconds is None or time.monotonic() - started < float(args.seconds):
            loop_started = time.monotonic()
            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            state = observer.process(frame)
            preview = render_overlay(frame, state, config)
            cv2.imshow(str(args.window_name), preview)
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
        source.close()
        cv2.destroyAllWindows()

    duration = max(1e-6, time.monotonic() - started)
    print(f"Observer stopped / Observador encerrado: frames={frames} fps={frames / duration:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
