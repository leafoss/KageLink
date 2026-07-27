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
from pc_agent.kage_pilot.entity_tracker_v03 import MeleeAwareEntityTracker
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
    # Calibrated from the first real v0.3 Observer screenshot. The previous
    # 0.50/0.55 anchor was visibly below Leafos and allowed the player sprite to
    # become an ENTITY candidate. Runtime click calibration can refine this.
    parser.add_argument("--player-x", type=float, default=0.51)
    parser.add_argument("--player-y", type=float, default=0.48)
    parser.add_argument("--player-radius", type=float, default=26.0)
    parser.add_argument("--enemy-threshold", type=float, default=55.0)
    parser.add_argument("--arena-left", type=float, default=0.04)
    parser.add_argument("--arena-top", type=float, default=0.04)
    parser.add_argument("--arena-right", type=float, default=0.96)
    parser.add_argument("--arena-bottom", type=float, default=0.86)
    parser.add_argument("--window-name", default="Kage Pilot v0.3 - Entity Observer")
    return parser


def _calibrate_player_from_click(
    click_x: int,
    click_y: int,
    arena_rect: tuple[int, int, int, int],
) -> tuple[float, float] | None:
    """Convert a preview click inside the arena to normalized player coords."""
    x0, y0, x1, y1 = arena_rect
    if not (x0 <= click_x < x1 and y0 <= click_y < y1):
        return None
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    player_x = max(0.0, min(1.0, (float(click_x) - x0) / width))
    player_y = max(0.0, min(1.0, (float(click_y) - y0) / height))
    return player_x, player_y


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
    observer.tracker = MeleeAwareEntityTracker(config)
    source = WindowsGameFrameSource()
    interval = 1.0 / max(1.0, min(30.0, float(args.fps)))
    started = time.monotonic()
    frames = 0
    window_name = str(args.window_name)

    # Updated every frame so the mouse callback can map preview coordinates back
    # to the current arena. The panel lives to the right of frame_width and is
    # intentionally not clickable for calibration.
    mouse_context: dict[str, object] = {
        "arena_rect": None,
        "frame_width": 0,
    }

    def on_mouse(event: int, x: int, y: int, flags: int, userdata: object) -> None:
        del flags, userdata
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        frame_width = int(mouse_context.get("frame_width", 0) or 0)
        arena_rect = mouse_context.get("arena_rect")
        if frame_width <= 0 or x >= frame_width or not isinstance(arena_rect, tuple):
            return
        calibrated = _calibrate_player_from_click(x, y, arena_rect)
        if calibrated is None:
            return
        config.player_x, config.player_y = calibrated
        config.normalized()

        # A wrong anchor may already have created the player itself as an ENTITY.
        # Reset temporal state so tracking restarts cleanly around the new anchor.
        observer.reset()
        print(
            "PLAYER calibrated / calibrado: "
            f"x={config.player_x:.4f} y={config.player_y:.4f} "
            f"radius={config.player_exclusion_radius:.1f}"
        )
        print(
            "Reuse / reutilizar: "
            f"--player-x {config.player_x:.4f} --player-y {config.player_y:.4f}"
        )

    print("Kage Pilot v0.3 ENTITY OBSERVER")
    print("READ ONLY / SOMENTE OBSERVACAO")
    print("Nenhuma tecla sera enviada ao jogo / No key will be sent to the game")
    print(
        "PLAYER inicial / initial: "
        f"x={config.player_x:.2f} y={config.player_y:.2f} "
        f"radius={config.player_exclusion_radius:.0f}"
    )
    print("Clique ESQUERDO em Leafos = calibrar PLAYER / LEFT CLICK Leafos = calibrate PLAYER")
    print("F10, Q ou ESC = sair / exit")

    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(window_name, on_mouse)

    try:
        while args.seconds is None or time.monotonic() - started < float(args.seconds):
            loop_started = time.monotonic()
            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            state = observer.process(frame)
            mouse_context["arena_rect"] = state.arena_rect
            mouse_context["frame_width"] = int(frame.shape[1])

            preview = render_overlay(frame, state, config)
            # Keep calibration discoverable inside the visual tool itself.
            cv2.putText(
                preview,
                "LEFT CLICK Leafos = PLAYER calibration / calibrar PLAYER",
                (12, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.43,
                (235, 235, 235),
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
        source.close()
        cv2.destroyAllWindows()

    duration = max(1e-6, time.monotonic() - started)
    print(f"Observer stopped / Observador encerrado: frames={frames} fps={frames / duration:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
