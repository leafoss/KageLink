from __future__ import annotations

import argparse
import json
from pathlib import Path

from .replay import CombatReplay
from .runner import STRATEGIES, run_all_scenarios


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pc_agent.kage_pilot.combat_lab",
        description="Deterministic offline Kage Combat Lab. Never sends game input.",
    )
    parser.add_argument(
        "--strategy",
        action="append",
        choices=STRATEGIES,
        help="Strategy to execute. Repeat for more than one; defaults to all.",
    )
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--text", dest="text_path", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--repeat", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    strategies = tuple(args.strategy or STRATEGIES)
    if args.replay is not None:
        replay = CombatReplay.read(args.replay)
        payload = {
            strategy: replay.assert_deterministic(
                strategy,
                repeats=max(2, int(args.repeat)),
            )
            for strategy in strategies
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    report = run_all_scenarios(strategies=strategies)
    if args.json_path is not None:
        report.write_json(args.json_path)
    if args.text_path is not None:
        report.write_text(args.text_path)
    print(json.dumps(report.summary(), indent=2, sort_keys=True))

    grid_results = report.by_strategy("grid_focus_v2")
    grid_gate = all(result.outcome == "PASS" for result in grid_results)
    return 0 if not grid_results or grid_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
