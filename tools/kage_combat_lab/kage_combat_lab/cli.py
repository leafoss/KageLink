from __future__ import annotations

import argparse
import os
import sys
import time

from .domain import CELL_SIZE_PX, GRID_CONTRACT_VERSION, GridCell
from .live_contract import checklist_lines
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
                symbol = "P" if cell != target else "P/E"
            row.append(symbol)
        lines.append(" ".join(row))
    return "\n".join(lines)


def _matches_expectation(scenario: Scenario, decision) -> bool:
    expected = scenario.expected
    return all(
        (
            decision.target_state is expected.target_state,
            (decision.combat_target_id is not None) is expected.target_present,
            decision.grid_distance == expected.grid_distance,
            decision.move == expected.move,
            decision.move_pulse_profile is expected.move_pulse_profile,
            decision.press_h is expected.press_h,
            decision.hold_r is expected.hold_r,
            decision.h_pulse_ms == expected.h_pulse_ms,
        )
    )


def run_scenario(scenario: Scenario, *, interactive: bool, delay: float) -> bool:
    strategy = GridFocusStrategy()
    last = None
    for frame in scenario.frames:
        last = strategy.update(frame)
        if interactive:
            _clear()
            print("KAGE COMBAT LAB")
            print(
                f"Grid contract: {GRID_CONTRACT_VERSION} "
                f"({CELL_SIZE_PX}x{CELL_SIZE_PX}px immutable)"
            )
            print(f"Scenario: {scenario.name}")
            print(scenario.description)
            print()
            print(_render_grid(frame.player_cell, last.confirmed_cell, last.predicted_cell))
            print()
            print(f"Frame: {frame.frame_index}")
            print(f"Time: {frame.effective_time_seconds:.2f}s")
            print(f"State: {last.target_state.value}")
            print(f"Combat target: {last.combat_target_id or '-'}")
            print(f"Confirmed cell: {last.confirmed_cell or '-'}")
            print(f"Predicted cell: {last.predicted_cell or '-'}")
            print(
                f"Grid distance: "
                f"{last.grid_distance if last.grid_distance is not None else '-'}"
            )
            print(f"Face: {last.face or '-'}")
            print(f"R held: {last.hold_r}")
            print(f"R key-down heartbeat: {last.r_keydown_heartbeat_ms or '-'} ms")
            print(f"Direction pulse: {last.move or '-'}")
            print(
                f"Pulse profile: "
                f"{last.move_pulse_profile.value if last.move_pulse_profile else '-'}"
            )
            print(f"Pulse duration: {last.move_pulse_ms or '-'} ms")
            print(f"Press H: {last.press_h}")
            print(f"H pulse: {last.h_pulse_ms or '-'} ms")
            print(f"H cooldown remaining: {last.h_cooldown_remaining_seconds:.2f}s")
            print(
                "Action sequence: "
                + (" -> ".join(last.action_sequence) if last.action_sequence else "-")
            )
            print(f"Reason: {last.reason}")
            if delay > 0:
                time.sleep(delay)
            else:
                input("Enter para avançar...")
    assert last is not None
    return _matches_expectation(scenario, last)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kage Combat Lab — deterministic 64px grid"
    )
    parser.add_argument("--scenario", default="distance_1_adjacent")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--live-checklist", action="store_true")
    parser.add_argument("--delay", type=float, default=0.4)
    args = parser.parse_args(argv)

    if args.live_checklist:
        print("\n".join(checklist_lines()))
        return 0

    scenarios = built_in_scenarios()
    selected = (
        scenarios
        if args.run_all
        else tuple(s for s in scenarios if s.name == args.scenario)
    )
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
