from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

from ..combat_strategy_v351 import (
    CombatStrategyConfig,
    CombatTargetSnapshotV2,
    create_combat_target_strategy,
)
from .scenarios import CombatLabScenario, all_scenarios


STRATEGIES = ("legacy_safe", "persistent_hardened", "grid_focus_v2")


@dataclass(frozen=True, slots=True)
class StrategyScenarioResult:
    scenario: str
    strategy: str
    outcome: str
    failures: tuple[str, ...]
    metrics: dict[str, float | int]
    decisions: tuple[CombatTargetSnapshotV2, ...]

    def compact(self) -> dict[str, object]:
        return {
            "scenario": self.scenario,
            "strategy": self.strategy,
            "outcome": self.outcome,
            "failures": list(self.failures),
            "metrics": dict(self.metrics),
            "final": asdict(self.decisions[-1]) if self.decisions else None,
        }


@dataclass(frozen=True, slots=True)
class CombatLabReport:
    results: tuple[StrategyScenarioResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.outcome == "PASS" for result in self.results)

    def by_strategy(self, strategy: str) -> tuple[StrategyScenarioResult, ...]:
        return tuple(result for result in self.results if result.strategy == strategy)

    def summary(self) -> dict[str, object]:
        strategies: dict[str, dict[str, object]] = {}
        for strategy in STRATEGIES:
            selected = self.by_strategy(strategy)
            totals: dict[str, float] = {}
            for result in selected:
                for key, value in result.metrics.items():
                    if isinstance(value, (int, float)):
                        totals[key] = totals.get(key, 0.0) + float(value)
            strategies[strategy] = {
                "passed": sum(item.outcome == "PASS" for item in selected),
                "failed": sum(item.outcome != "PASS" for item in selected),
                "metrics": {
                    key: int(value) if value.is_integer() else round(value, 6)
                    for key, value in sorted(totals.items())
                },
            }
        return {
            "scenario_count": len({result.scenario for result in self.results}),
            "result_count": len(self.results),
            "all_results_pass": self.passed,
            "strategies": strategies,
        }

    def write_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "summary": self.summary(),
                    "results": [result.compact() for result in self.results],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return destination

    def write_text(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        for scenario in sorted({item.scenario for item in self.results}):
            lines.append(f"Scenario: {scenario}")
            for result in (item for item in self.results if item.scenario == scenario):
                lines.append("")
                lines.append(f"{result.strategy}:")
                for key, value in sorted(result.metrics.items()):
                    lines.append(f"  {key}={value}")
                if result.failures:
                    lines.append("  failures=" + ", ".join(result.failures))
                lines.append(f"  outcome={result.outcome}")
            lines.append("")
        destination.write_text("\n".join(lines), encoding="utf-8")
        return destination


def _evaluate(
    scenario: CombatLabScenario,
    decisions: tuple[CombatTargetSnapshotV2, ...],
    metrics: dict[str, float | int],
) -> tuple[str, ...]:
    failures: list[str] = []
    false_targets = 0
    post_ko_targets = 0
    multi_cell_promotions = int(metrics.get("multi_cell_blobs_promoted", 0) or 0)
    direction_errors = 0
    prediction_jumps = 0
    previous_prediction = None
    previous_combat_target_id = None

    for decision in decisions:
        visual_id = decision.current_visual_track_id
        if (
            decision.active
            and visual_id is not None
            and visual_id not in scenario.valid_enemy_track_ids
        ):
            false_targets += 1
        if decision.combat_phase == "POST_COMBAT" and (
            decision.active or decision.combat_target_id is not None
        ):
            post_ko_targets += 1
        if decision.confirmed_target_cell is not None:
            expected = decision.last_contact_direction
            dx = decision.confirmed_target_cell[0] - decision.player_cell[0]
            dy = decision.confirmed_target_cell[1] - decision.player_cell[1]
            if expected in {"LEFT", "RIGHT", "UP", "DOWN"}:
                if expected == "LEFT" and dx > 0:
                    direction_errors += 1
                elif expected == "RIGHT" and dx < 0:
                    direction_errors += 1
                elif expected == "UP" and dy > 0 and abs(dy) > abs(dx):
                    direction_errors += 1
                elif expected == "DOWN" and dy < 0 and abs(dy) > abs(dx):
                    direction_errors += 1

        # Prediction continuity belongs to one logical opponent. A target that was
        # genuinely hard-lost and followed by a new combat_target_id starts a new
        # lifecycle and must not be counted as a multi-cell prediction jump.
        if decision.combat_target_id != previous_combat_target_id:
            previous_prediction = None
            previous_combat_target_id = decision.combat_target_id
        prediction = decision.predicted_target_cell
        if previous_prediction is not None and prediction is not None:
            jump = max(
                abs(prediction[0] - previous_prediction[0]),
                abs(prediction[1] - previous_prediction[1]),
            )
            if jump > 1:
                prediction_jumps += 1
        if prediction is not None:
            previous_prediction = prediction
        elif decision.combat_target_id is None:
            previous_prediction = None

    final = decisions[-1]
    target_present = final.combat_target_id is not None and final.active
    if scenario.expect_target and not target_present:
        failures.append("EXPECTED_TARGET_MISSING")
    if not scenario.expect_target and target_present:
        failures.append("UNEXPECTED_TARGET_ACTIVE")
    if scenario.expected_final_cell is not None and target_present:
        if final.confirmed_target_cell != scenario.expected_final_cell:
            failures.append(
                f"FINAL_CELL:{final.confirmed_target_cell}!={scenario.expected_final_cell}"
            )
    if scenario.expected_final_direction is not None and target_present:
        if final.last_contact_direction != scenario.expected_final_direction:
            failures.append(
                f"FINAL_DIRECTION:{final.last_contact_direction}!={scenario.expected_final_direction}"
            )
    if scenario.require_post_ko_disabled:
        if final.combat_phase != "POST_COMBAT":
            failures.append("POST_COMBAT_PHASE_MISSING")
        if final.track_creation_enabled:
            failures.append("TRACK_CREATION_ENABLED_AFTER_KO")
        if final.perception_scope != "COMBAT_DISABLED":
            failures.append("COMBAT_SCOPE_NOT_DISABLED")
    if false_targets:
        failures.append(f"FALSE_TARGETS:{false_targets}")
    if post_ko_targets:
        failures.append(f"POST_KO_TARGETS:{post_ko_targets}")
    if multi_cell_promotions:
        failures.append(f"MULTI_CELL_PROMOTIONS:{multi_cell_promotions}")
    if direction_errors:
        failures.append(f"DIRECTION_ERRORS:{direction_errors}")
    if prediction_jumps:
        failures.append(f"PREDICTION_JUMPS:{prediction_jumps}")
    return tuple(failures)


def run_scenario(
    scenario: CombatLabScenario,
    strategy_name: str,
    *,
    config: CombatStrategyConfig | None = None,
) -> StrategyScenarioResult:
    settings = config or CombatStrategyConfig(strategy=strategy_name)
    strategy = create_combat_target_strategy(strategy_name, settings)
    decisions = tuple(strategy.update(frame) for frame in scenario.frames)
    metrics = strategy.metrics_snapshot()

    # Add independently measured metrics so an unsafe strategy cannot hide a failure
    # by failing to increment its own counters.
    false_targets = sum(
        1
        for decision in decisions
        if decision.active
        and decision.current_visual_track_id is not None
        and decision.current_visual_track_id not in scenario.valid_enemy_track_ids
    )
    post_ko_targets = sum(
        1
        for decision in decisions
        if decision.combat_phase == "POST_COMBAT"
        and (decision.active or decision.combat_target_id is not None)
    )
    metrics = {
        **metrics,
        "false_target_acquisitions": max(
            int(metrics.get("false_target_acquisitions", 0) or 0), false_targets
        ),
        "post_ko_targets": max(int(metrics.get("post_ko_targets", 0) or 0), post_ko_targets),
    }
    failures = _evaluate(scenario, decisions, metrics)
    return StrategyScenarioResult(
        scenario=scenario.name,
        strategy=strategy_name,
        outcome="PASS" if not failures else "FAIL",
        failures=failures,
        metrics=metrics,
        decisions=decisions,
    )


def run_all_scenarios(
    scenarios: Iterable[CombatLabScenario] | None = None,
    *,
    strategies: Iterable[str] = STRATEGIES,
) -> CombatLabReport:
    selected = tuple(all_scenarios() if scenarios is None else scenarios)
    results = tuple(
        run_scenario(scenario, strategy)
        for scenario in selected
        for strategy in tuple(strategies)
    )
    return CombatLabReport(results)


__all__ = [
    "CombatLabReport",
    "STRATEGIES",
    "StrategyScenarioResult",
    "run_all_scenarios",
    "run_scenario",
]
