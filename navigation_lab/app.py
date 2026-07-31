from __future__ import annotations

import argparse
import json
import sys

from .simulator import SCENARIOS, SimulatorEngine, get_scenario
from .storage import JsonRepository
from .visualization import DebugWindow, render_ascii


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Independent Kage mapping and navigation laboratory")
    parser.add_argument(
        "--mode",
        choices=["simulator", "observer", "grid-calibration", "teaching", "assisted", "autonomous", "replay"],
        default="simulator",
    )
    parser.add_argument("--scenario", default="basic_world")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--language", choices=["pt-BR", "en-US"], default="pt-BR")
    parser.add_argument("--debug-window", action="store_true")
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--record-session", action="store_true")
    parser.add_argument("--session-name")
    parser.add_argument("--window-title", default="Shinobi Story Online")
    parser.add_argument("--destination")
    parser.add_argument("--arm-input", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--region-id", default="mapping_calibration")
    parser.add_argument("--tile-size", type=int, default=64)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--camera-mode", choices=["following", "hybrid", "fixed"], default="following")
    parser.add_argument("--mapping-strategy", choices=["input", "continuous"], default="input")
    parser.add_argument("--map-radius", type=int, default=10)
    parser.add_argument("--motion-confidence", type=float, default=0.18)
    parser.add_argument("--command-timeout", type=float, default=0.70)
    parser.add_argument("--min-command-shift", type=float, default=2.0)
    parser.add_argument("--invert-x", action="store_true")
    parser.add_argument("--invert-y", action="store_true")
    parser.add_argument("--new-map", action="store_true")
    parser.add_argument("--no-auto-start", action="store_true")
    parser.add_argument("--keep-window-visible", action="store_true")
    parser.add_argument("--ignore-grid-calibration", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_scenarios:
        for scenario_id in sorted(SCENARIOS):
            if scenario_id != "basic_world":
                print(scenario_id)
        return 0
    if args.mode == "grid-calibration":
        return _run_grid_calibration(args)
    if args.mode == "observer":
        return _run_observer(args)
    if args.mode != "simulator":
        message = {
            "pt-BR": "Este modo permanece bloqueado até o mapeamento ao vivo ser validado. Use --mode grid-calibration, observer ou simulator.",
            "en-US": "This mode remains blocked until live mapping is validated. Use --mode grid-calibration, observer or simulator.",
        }[args.language]
        print(message, file=sys.stderr)
        return 3
    scenario = get_scenario(args.scenario)
    engine = SimulatorEngine(scenario)
    if args.debug_window:
        DebugWindow(engine, language=args.language).run()
        return 0
    result = engine.run()
    if args.record_session:
        repository = JsonRepository(profile=args.profile)
        path = repository.save_simulation(result)
        print(f"session={path}")
    if args.json_output:
        print(json.dumps({
            "scenario": result.scenario_id,
            "outcome": result.outcome,
            "steps": result.steps,
            "recoveries": result.recoveries,
            "replans": result.replans,
            "message": result.message,
        }, ensure_ascii=False))
    else:
        final = result.snapshots[-1] if result.snapshots else None
        print(
            f"scenario={result.scenario_id} outcome={result.outcome} steps={result.steps} "
            f"recoveries={result.recoveries} replans={result.replans}"
        )
        if final:
            print(render_ascii(engine.grid, final.actual_position, final.goal, final.path))
            print(f"state={final.state.value} confidence={final.pose.confidence:.2f} action={final.decision.action}")
    return 0 if result.outcome == scenario.expected_result else 2


def _run_grid_calibration(args: argparse.Namespace) -> int:
    try:
        from .observer.grid_calibration_window import GridCalibrationWindow
        from .observer.window_capture import WindowsClientCapture

        repository = JsonRepository(profile=args.profile)
        capture = WindowsClientCapture(args.window_title)
        GridCalibrationWindow(
            capture=capture,
            repository=repository,
            region_id=args.region_id,
            language=args.language,
        ).run()
        return 0
    except Exception as exc:
        print(f"Grid calibration startup failed: {exc}", file=sys.stderr)
        return 4


def _run_observer(args: argparse.Namespace) -> int:
    if args.tile_size <= 0:
        print("--tile-size must be positive", file=sys.stderr)
        return 2
    if args.command_timeout <= 0 or args.min_command_shift <= 0:
        print("--command-timeout and --min-command-shift must be positive", file=sys.stderr)
        return 2
    try:
        from .observer import GridCalibration, MappingObserverEngine
        from .observer.debug_window import MappingObserverDebugWindow
        from .observer.window_capture import WindowsClientCapture

        repository = JsonRepository(profile=args.profile)
        calibration = GridCalibration(tile_size_px=args.tile_size)
        if not args.ignore_grid_calibration and repository.has_grid_calibration(args.region_id):
            calibration = GridCalibration.from_dict(repository.load_grid_calibration(args.region_id))

        engine = MappingObserverEngine(
            region_id=args.region_id,
            tile_size_px=calibration.tile_size_px,
            camera_mode=args.camera_mode,
            map_radius=args.map_radius,
            min_motion_response=args.motion_confidence,
            invert_x=args.invert_x,
            invert_y=args.invert_y,
            mapping_strategy=args.mapping_strategy,
            command_timeout_seconds=args.command_timeout,
            min_command_shift_px=args.min_command_shift,
            grid_offset_x_px=calibration.offset_x_px,
            grid_offset_y_px=calibration.offset_y_px,
            grid_line_thickness=calibration.line_thickness,
            grid_line_opacity=calibration.line_opacity,
        )
        if not args.new_map and repository.has_mapping_state(args.region_id):
            engine.restore_state(repository.load_mapping_state(args.region_id))
        capture = WindowsClientCapture(args.window_title)
        MappingObserverDebugWindow(
            engine=engine,
            capture=capture,
            repository=repository,
            fps=args.fps,
            language=args.language,
            auto_start=not args.no_auto_start,
            minimize_on_start=not args.keep_window_visible,
        ).run()
        return 0
    except Exception as exc:
        print(f"Observer startup failed: {exc}", file=sys.stderr)
        return 4
