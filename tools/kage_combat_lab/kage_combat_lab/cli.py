from __future__ import annotations

import argparse
import os
import sys
import time

from .domain import CELL_SIZE_PX, GRID_CONTRACT_VERSION, GridCell
from .scenarios import Scenario, built_in_scenarios
from .strategy import GridFocusStrategy


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _render_grid(player: GridCell, target: GridCell | None, predicted: GridCell | None) -> str:
    lines: list[str] = []
    for y in range(-2, 3):
        row: list[str] = []
        for x in range(-2, 3):
            cell = GridCell(x, y)
            symbol = "."
            if cell == predicted:
                symbol = "?"
            if cell == target:
                symbol = "E"
            if cell == player:
                symbol = "P"
            row.append(symbol)
        lines.append(" ".join(row))
    return "\n".join(lines)


def run_scenario(scenario: Scenario, *, interactive: bool, delay: float) -> bool:
    strategy = GridFocusStrategy()
    last = None
    for frame in scenario.frames:
        last = strategy.update(frame)
        if interactive:
            _clear()
            print("KAGE COMBAT LAB")
            print(f"Grid contract: {GRID_CONTRACT_VERSION} ({CELL_SIZE_PX}x{CELL_SIZE_PX}px immutable)")
            print(f"Scenario: {scenario.name}")
            print(scenario.description)
            print()
            print(_render_grid(frame.player_cell, last.confirmed_cell, last.predicted_cell))
            print()
            print(f"Frame: {frame.frame_index}")
            print(f"State: {last.target_state.value}")
            print(f"Combat target: {last.combat_target_id or '-'}")
            print(f"Confirmed cell: {last.confirmed_cell or '-'}")
            print(f"Predicted cell: {last.predicted_cell or '-'}")
            print(f"Face: {last.face or '-'}")
            print(f"Move: {last.move or '-'}")
            print(f"Primary attack: {last.attack_primary}")
            print(f"Reason: {last.reason}")
            if delay > 0:
                time.sleep(delay)
            else:
                input("Enter para avançar...")
    assert last is not None
    if scenario.name == "multi_cell_effect":
        return last.combat_target_id is None
    if scenario.name == "ko_disables_combat":
        return last.combat_target_id is None and last.target_state.value == "ENDED"
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kage Combat Lab — deterministic 64px grid")
    parser.add_argument("--scenario", default="enemy_right")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--delay", type=float, default=0.4)
    args = parser.parse_args(argv)

    scenarios = built_in_scenarios()
    selected = scenarios if args.run_all else tuple(s for s in scenarios if s.name == args.scenario)
    if not selected:
        print(f"Unknown scenario: {args.scenario}", file=sys.stderr)
        return 2

    failures = 0
    print(f"KAGE COMBAT LAB — {GRID_CONTRACT_VERSION}")
    print(f"Canonical grid: {CELL_SIZE_PX}x{CELL_SIZE_PX} pixels")
    for scenario in selected:
        passed = run_scenario(scenario, interactive=args.interactive, delay=args.delay)
        print(f"[{'PASS' if passed else 'FAIL'}] {scenario.name}: {scenario.description}")
        failures += 0 if passed else 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
