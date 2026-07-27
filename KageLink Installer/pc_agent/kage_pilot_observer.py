from __future__ import annotations

import argparse
import time

import cv2

from pc_agent.kage_pilot.entity_observer import decode_jpeg
from pc_agent.kage_pilot.grid_target_observer_v03d import TileCalibratedGridTargetObserver as GridTargetObserver
from pc_agent.kage_pilot.observer_runtime_v03 import (
    V03ObserverConfig,
    render_overlay_v03,
)
from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
    PersistentBackgroundWaterAwareEntityTracker as WaterAwareEntityTracker,
)
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource


DEFAULT_PLAYER_X = 0.5181
DEFAULT_PLAYER_Y = 0.4706
DEFAULT_GRID_SIZE = 64.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Kage Pilot v0.3 read-only entity observer / "
            "observador de entidades somente leitura"
        )
    )
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--telemetry-seconds", type=float, default=2.0)

    # Calibrated from the latest validated combat run. Left-click remains available
    # for refinement, but this should put PLAYER #000 on Leafos by default.
    parser.add_argument("--player-x", type=float, default=DEFAULT_PLAYER_X)
    parser.add_argument("--player-y", type=float, default=DEFAULT_PLAYER_Y)
    parser.add_argument("--player-box-width", type=float, default=18.0)
    parser.add_argument("--player-box-height", type=float, default=38.0)

    parser.add_argument("--target-acquire", type=float, default=55.0)
    parser.add_argument("--target-keep", type=float, default=38.0)
    parser.add_argument("--track-ttl", type=float, default=2.0)
    parser.add_argument("--match-distance", type=float, default=105.0)

    parser.add_argument("--background-similarity", type=float, default=0.88)
    parser.add_argument("--background-min-hits", type=float, default=8.0)
    parser.add_argument("--background-min-age", type=float, default=0.8)
    parser.add_argument("--no-dynamic-background", action="store_true")

    parser.add_argument("--reacquire-ttl", type=float, default=5.0)
    parser.add_argument("--reacquire-distance", type=float, default=180.0)
    parser.add_argument("--reacquire-similarity", type=float, default=0.82)

    # The NPC/player references show one complete character occupying roughly a 64px
    # vertical band. The grid is therefore 64x64 by default and is automatically offset
    # so PLAYER is centred inside one cell. Manual origins remain available for tests.
    parser.add_argument("--grid-size", type=float, default=DEFAULT_GRID_SIZE)
    parser.add_argument("--grid-origin-x", type=float, default=None)
    parser.add_argument("--grid-origin-y", type=float, default=None)
    parser.add_argument("--contact-lock-seconds", type=float, default=2.8)
    parser.add_argument("--contact-confirm-frames", type=int, default=2)
    parser.add_argument("--no-grid-overlay", action="store_true")

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


def _telemetry_line(state, tracker, observer: GridTargetObserver, *, started: float) -> str:
    target = state.target
    if target is None:
        target_text = "none"
        grid_text = "-"
    else:
        context = tracker.context_for(target.track_id)
        metrics = observer.metrics_for(target.track_id)
        state_name = observer.target_mode if observer.target_mode != "NONE" else context.state
        target_text = (
            f"#{target.track_id:03d}/{state_name}/{context.relative_side}/"
            f"{target.enemy_score:.1f}%"
        )
        if metrics is None:
            grid_text = "-"
        else:
            grid_text = (
                f"cell={metrics.cell[0]},{metrics.cell[1]} "
                f"d={metrics.grid_distance} toward={metrics.toward_steps} "
                f"away={metrics.away_steps} net={metrics.net_closer} "
                f"bg={metrics.background_strength:.2f}"
            )
    origin_x, origin_y = observer.grid_origin
    return (
        f"OBS t={time.monotonic() - started:6.1f}s "
        f"entities={len(state.tracks):3d} "
        f"bg_mature={tracker.background.mature_cells:3d} "
        f"bg_strong={tracker.background.strong_cells:3d} "
        f"suppressed={tracker.background.suppressed_last_frame:3d} "
        f"pruned={getattr(tracker, 'background_pruned_last_frame', 0):3d} "
        f"dormant={tracker.dormant_count:3d} "
        f"grid_active={observer.active_grid_cells:3d} "
        f"origin={origin_x:.1f},{origin_y:.1f} "
        f"target={target_text} grid[{grid_text}]"
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
        dynamic_background_enabled=not bool(args.no_dynamic_background),
        background_similarity=args.background_similarity,
        background_min_dense_hits=args.background_min_hits,
        background_min_age=args.background_min_age,
        reacquire_ttl=args.reacquire_ttl,
        reacquire_distance=args.reacquire_distance,
        reacquire_similarity=args.reacquire_similarity,
    ).normalized()

    manual_origin = args.grid_origin_x is not None or args.grid_origin_y is not None
    if manual_origin and (args.grid_origin_x is None or args.grid_origin_y is None):
        raise SystemExit(
            "GRID origin requires both --grid-origin-x and --grid-origin-y / "
            "origem da GRID requer os dois parametros"
        )

    observer = GridTargetObserver(
        config,
        tile_size=args.grid_size,
        contact_lock_seconds=args.contact_lock_seconds,
        show_grid=not bool(args.no_grid_overlay),
        auto_align_grid=not manual_origin,
        grid_origin_x=args.grid_origin_x,
        grid_origin_y=args.grid_origin_y,
        contact_confirm_frames=args.contact_confirm_frames,
    )
    tracker = WaterAwareEntityTracker(config)
    observer.tracker = tracker
    source = WindowsGameFrameSource()
    interval = 1.0 / max(1.0, min(30.0, float(args.fps)))
    telemetry_interval = max(0.0, float(args.telemetry_seconds))
    started = time.monotonic()
    next_telemetry = started + telemetry_interval if telemetry_interval > 0 else float("inf")
    frames = 0
    window_name = str(args.window_name)

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
        observer.reset()
        observer.request_grid_realign()
        print(
            "PLAYER calibrated / calibrado: "
            f"x={config.player_x:.4f} y={config.player_y:.4f} "
            f"box={config.player_box_width:.0f}x{config.player_box_height:.0f}px"
        )
        print(
            "Reuse / reutilizar: "
            f"--player-x {config.player_x:.4f} --player-y {config.player_y:.4f}"
        )
        print(
            "GRID will realign to PLAYER centre / "
            "GRID sera realinhada ao centro do PLAYER"
        )
        print(
            "BACKGROUND memory preserved / memoria de fundo preservada: "
            f"cells={tracker.background.mature_cells} strong={tracker.background.strong_cells}"
        )

    print("Kage Pilot v0.3 ENTITY OBSERVER")
    print("READ ONLY / SOMENTE OBSERVACAO")
    print("Nenhuma tecla sera enviada ao jogo / No key will be sent to the game")
    print(
        "PLAYER inicial / initial: "
        f"x={config.player_x:.4f} y={config.player_y:.4f} "
        f"box={config.player_box_width:.0f}x{config.player_box_height:.0f}px"
    )
    print(
        "TRACK lock: "
        f"match={config.track_match_distance:.0f}px ttl={config.track_ttl_seconds:.1f}s "
        f"acquire={config.target_acquire_threshold:.0f}% keep={config.target_keep_threshold:.0f}%"
    )
    print(
        "BACKGROUND_DYNAMIC v3 temporal recurrence: "
        f"enabled={'yes' if config.dynamic_background_enabled else 'no'} "
        f"similarity={config.background_similarity:.2f} "
        f"hits={config.background_min_dense_hits:.0f} age={config.background_min_age:.1f}s"
    )
    print(
        "TARGET GUARD v4: 64px tile trajectory + confirmed CONTACT MEMORY; "
        "LOST cannot create contact"
    )
    alignment = "PLAYER-centred auto" if not manual_origin else "manual"
    print(
        "GRID: "
        f"size={observer.tile_size:.0f}px alignment={alignment} "
        f"contact_lock={observer.contact_lock_seconds:.1f}s "
        f"contact_confirm={observer.contact_confirm_frames} frames "
        f"overlay={'yes' if observer.show_grid else 'no'}"
    )
    print(
        "REACQUIRE: "
        f"ttl={config.reacquire_ttl:.1f}s distance={config.reacquire_distance:.0f}px "
        f"similarity={config.reacquire_similarity:.2f}"
    )
    print(f"TELEMETRY: every / a cada {telemetry_interval:.1f}s" if telemetry_interval > 0 else "TELEMETRY: off")
    print("Clique ESQUERDO em Leafos = calibrar PLAYER / LEFT CLICK Leafos = calibrate PLAYER")
    print("Q ou ESC = sair / exit")

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

            now = time.monotonic()
            if now >= next_telemetry:
                print(_telemetry_line(state, tracker, observer, started=started))
                next_telemetry = now + telemetry_interval

            preview = render_overlay_v03(frame, state, config, tracker)
            preview = observer.draw_grid_overlay(preview, state)
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
