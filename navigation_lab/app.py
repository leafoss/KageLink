from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .simulator import SCENARIOS, SimulatorEngine, get_scenario
from .storage import JsonRepository
from .visualization import DebugWindow, render_ascii


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Independent Kage navigation laboratory")
    parser.add_argument("--mode", choices=["simulator", "observer", "teaching", "assisted", "autonomous", "replay"], default="simulator")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_scenarios:
        for scenario_id in sorted(SCENARIOS):
            if scenario_id != "basic_world":
                print(scenario_id)
        return 0
    if args.mode != "simulator":
        message = {
            "pt-BR": "Este modo está arquitetado, mas bloqueado nesta primeira entrega até validação física Windows/BYOND. Use --mode simulator.",
            "en-US": "This mode is architected but blocked in the first delivery until Windows/BYOND physical validation. Use --mode simulator.",
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
        print(f"scenario={result.scenario_id} outcome={result.outcome} steps={result.steps} recoveries={result.recoveries} replans={result.replans}")
        if final:
            print(render_ascii(engine.grid, final.actual_position, final.goal, final.path))
            print(f"state={final.state.value} confidence={final.pose.confidence:.2f} action={final.decision.action}")
    return 0 if result.outcome == scenario.expected_result else 2
