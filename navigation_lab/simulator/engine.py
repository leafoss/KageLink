from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

from ..mapping import OccupancyGrid
from ..models import CellState, Decision, NavigationState, Point, Pose
from ..planning import PathNotFound, astar
from ..state_machine import NavigationStateMachine
from .scenarios import Scenario


@dataclass(slots=True)
class SimulationSnapshot:
    step: int
    pose: Pose
    actual_position: Point
    goal: Point
    path: list[Point]
    decision: Decision
    state: NavigationState
    events: list[str] = field(default_factory=list)
    arrived: bool = False
    aborted: bool = False
    recoveries: int = 0


@dataclass(slots=True)
class SimulationResult:
    scenario_id: str
    outcome: str
    steps: int
    recoveries: int
    replans: int
    snapshots: list[SimulationSnapshot]
    message: str


class SimulatorEngine:
    def __init__(self, scenario: Scenario, max_recoveries: int = 5) -> None:
        self.scenario = scenario
        self.grid = OccupancyGrid(scenario.width, scenario.height, default=CellState.WALKABLE)
        for y, row in enumerate(scenario.rows):
            for x, char in enumerate(row):
                point = Point(x, y)
                if char == "#":
                    self.grid.set(point, CellState.BLOCKED)
                elif char == "L":
                    self.grid.set(point, CellState.LANDMARK, label="landmark")
                elif char == "T":
                    self.grid.set(point, CellState.TRANSITION, label="transition")
                elif char == "D":
                    self.grid.set(point, CellState.DESTINATION, label="destination_marker")
                else:
                    self.grid.set(point, CellState.WALKABLE)
        self.grid.set(scenario.goal, CellState.DESTINATION, label="goal")
        self.position = scenario.start
        self.pose = Pose("simulated_region", float(self.position.x), float(self.position.y), 1.0, "simulator")
        self.machine = NavigationStateMachine()
        self.current_path: list[Point] = []
        self.recoveries = 0
        self.replans = 0
        self.max_recoveries = max_recoveries
        self._temporary_blocks: set[Point] = set()

    def _apply_dynamic_blocks(self, step: int) -> list[str]:
        events: list[str] = []
        if step not in self.scenario.dynamic_blocks:
            return events
        new_blocks = set(self.scenario.dynamic_blocks[step])
        for point in self._temporary_blocks - new_blocks:
            if self.grid.in_bounds(point):
                self.grid.set(point, CellState.WALKABLE)
                events.append(f"temporary obstacle cleared at {point.x},{point.y}")
        for point in new_blocks:
            if self.grid.in_bounds(point) and point not in {self.position, self.scenario.goal}:
                self.grid.set(point, CellState.TEMPORARY_BLOCK, confidence=0.9)
                events.append(f"temporary obstacle detected at {point.x},{point.y}")
        self._temporary_blocks = new_blocks
        return events

    def _plan(self) -> None:
        if self.machine.state in {NavigationState.IDLE, NavigationState.RECOVERING, NavigationState.RELOCALIZING, NavigationState.PAUSED}:
            self.machine.transition(NavigationState.PLANNING, "calculate local path")
        try:
            self.current_path = astar(self.grid, self.position, self.scenario.goal, allow_unknown=True)
        except PathNotFound:
            self.machine.transition(NavigationState.ERROR, "no route available")
            self.current_path = []
            return
        self.replans += 1
        if len(self.current_path) <= 1:
            self.machine.transition(NavigationState.ARRIVED, "already at destination")
        else:
            self.machine.transition(NavigationState.NAVIGATING, "path available")

    def _decision(self, action: str, reason: str, next_point: Point | None = None) -> Decision:
        route_confidence = 0.0 if not self.current_path else min(1.0, 0.75 + len(self.current_path) / 100.0)
        return Decision(
            action=action,
            reason=reason,
            state=self.machine.state,
            current_region=self.pose.region_id,
            destination="goal",
            localization_confidence=self.pose.confidence,
            route_confidence=route_confidence,
            next_point=next_point,
        )

    def run(self, on_snapshot: Callable[[SimulationSnapshot], None] | None = None) -> SimulationResult:
        self._plan()
        snapshots: list[SimulationSnapshot] = []
        for step in range(self.scenario.max_steps + 1):
            events = self._apply_dynamic_blocks(step)
            if self.position == self.scenario.goal:
                if self.machine.state != NavigationState.ARRIVED:
                    if self.machine.state == NavigationState.VERIFYING_PROGRESS:
                        self.machine.transition(NavigationState.ARRIVED, "destination confirmed")
                    elif self.machine.state == NavigationState.NAVIGATING:
                        self.machine.transition(NavigationState.ARRIVED, "destination confirmed")
                snapshot = SimulationSnapshot(step, replace(self.pose), self.position, self.scenario.goal, list(self.current_path), self._decision("STOP", "destination reached"), self.machine.state, events, arrived=True, recoveries=self.recoveries)
                snapshots.append(snapshot)
                if on_snapshot:
                    on_snapshot(snapshot)
                return SimulationResult(self.scenario.id, "arrived", step, self.recoveries, self.replans, snapshots, "Destination reached")
            if self.machine.state == NavigationState.ERROR:
                break
            if not self.current_path or self.current_path[0] != self.position:
                self._plan()
                events.append("route replanned")
                if self.machine.state == NavigationState.ERROR:
                    break
            next_point = self.current_path[1] if len(self.current_path) > 1 else self.position
            if not self.grid.is_walkable(next_point, allow_unknown=True):
                self.machine.transition(NavigationState.STUCK, "next path cell is blocked")
                events.append(f"movement blocked at {next_point.x},{next_point.y}")
                self.recoveries += 1
                if self.recoveries > self.max_recoveries:
                    self.machine.transition(NavigationState.PAUSED, "recovery limit exceeded")
                    snapshot = SimulationSnapshot(step, replace(self.pose), self.position, self.scenario.goal, list(self.current_path), self._decision("RELEASE_ALL_INPUTS", "recovery limit exceeded"), self.machine.state, events, aborted=True, recoveries=self.recoveries)
                    snapshots.append(snapshot)
                    if on_snapshot:
                        on_snapshot(snapshot)
                    return SimulationResult(self.scenario.id, "paused", step, self.recoveries, self.replans, snapshots, "Recovery limit exceeded")
                self.machine.transition(NavigationState.RECOVERING, "release inputs and replan")
                self._plan()
                snapshot = SimulationSnapshot(step, replace(self.pose), self.position, self.scenario.goal, list(self.current_path), self._decision("REPLAN", "obstacle detected"), self.machine.state, events, recoveries=self.recoveries)
                snapshots.append(snapshot)
                if on_snapshot:
                    on_snapshot(snapshot)
                continue
            self.machine.transition(NavigationState.VERIFYING_PROGRESS, "movement command simulated")
            previous = self.position
            self.position = next_point
            self.current_path = self.current_path[1:]
            self.pose.x = float(self.position.x)
            self.pose.y = float(self.position.y)
            self.pose.confidence = max(0.45, self.pose.confidence - 0.005)
            if self.scenario.localization_noise_step == step:
                self.pose.confidence = 0.35
                events.append("localization confidence intentionally degraded")
            if self.grid.get(self.position).state == CellState.LANDMARK:
                self.pose.confidence = 0.98
                self.pose.source = "landmark_relocalization"
                events.append("landmark confirmed; pose corrected")
            self.grid.observe(previous, CellState.VISITED, confidence=1.0)
            if self.pose.confidence < 0.4:
                self.machine.transition(NavigationState.RELOCALIZING, "localization confidence below threshold")
                self.pose.confidence = 0.72
                self.pose.source = "simulated_relocalization"
                events.append("relocalization completed")
                self.machine.transition(NavigationState.PLANNING, "replan after relocalization")
                self.current_path = astar(self.grid, self.position, self.scenario.goal, allow_unknown=True)
                self.replans += 1
                self.machine.transition(NavigationState.NAVIGATING, "path restored")
            else:
                if self.position == self.scenario.goal:
                    self.machine.transition(NavigationState.ARRIVED, "destination confirmed")
                else:
                    self.machine.transition(NavigationState.NAVIGATING, "progress verified")
            action = _direction(previous, self.position)
            snapshot = SimulationSnapshot(step, replace(self.pose), self.position, self.scenario.goal, list(self.current_path), self._decision(action, "next path cell", self.current_path[1] if len(self.current_path) > 1 else None), self.machine.state, events, arrived=self.position == self.scenario.goal, recoveries=self.recoveries)
            snapshots.append(snapshot)
            if on_snapshot:
                on_snapshot(snapshot)
        return SimulationResult(self.scenario.id, "error", len(snapshots), self.recoveries, self.replans, snapshots, "Maximum steps exceeded or no route")


def _direction(previous: Point, current: Point) -> str:
    dx = current.x - previous.x
    dy = current.y - previous.y
    return {(1, 0): "MOVE_RIGHT", (-1, 0): "MOVE_LEFT", (0, 1): "MOVE_DOWN", (0, -1): "MOVE_UP"}.get((dx, dy), "STOP")
