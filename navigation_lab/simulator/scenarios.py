from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Point


@dataclass(slots=True)
class Scenario:
    id: str
    title: str
    rows: list[str]
    start: Point
    goal: Point
    dynamic_blocks: dict[int, list[Point]] = field(default_factory=dict)
    expected_result: str = "arrived"
    max_steps: int = 200
    localization_noise_step: int | None = None

    @property
    def width(self) -> int:
        return len(self.rows[0])

    @property
    def height(self) -> int:
        return len(self.rows)


def _scenario(sid: str, title: str, rows: list[str], **kwargs) -> Scenario:
    start = goal = None
    normalized: list[str] = []
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError(f"Scenario {sid} has inconsistent row widths")
    for y, row in enumerate(rows):
        chars = list(row)
        for x, char in enumerate(chars):
            if char == "S":
                start = Point(x, y)
                chars[x] = "."
            elif char == "G":
                goal = Point(x, y)
                chars[x] = "."
        normalized.append("".join(chars))
    if start is None or goal is None:
        raise ValueError(f"Scenario {sid} requires S and G")
    return Scenario(sid, title, normalized, start, goal, **kwargs)


SCENARIOS: dict[str, Scenario] = {
    "01_basic_corridor": _scenario("01_basic_corridor", "Basic corridor", [
        "###########",
        "#S.......G#",
        "###########",
    ]),
    "02_multiple_paths": _scenario("02_multiple_paths", "Multiple paths", [
        "#############",
        "#S....#....G#",
        "#.....#.....#",
        "#...........#",
        "#############",
    ]),
    "03_blocked_shortest_path": _scenario("03_blocked_shortest_path", "Blocked shortest path", [
        "#############",
        "#S..........#",
        "#...........#",
        "#..........G#",
        "#############",
    ], dynamic_blocks={3: [Point(4, 1), Point(4, 2)]}),
    "04_unknown_world": _scenario("04_unknown_world", "Unknown world", [
        "#############",
        "#S..........#",
        "#.#####.....#",
        "#.........G.#",
        "#############",
    ]),
    "05_landmark_relocalization": _scenario("05_landmark_relocalization", "Landmark relocalization", [
        "#############",
        "#S..L.......#",
        "#..###......#",
        "#.........G.#",
        "#############",
    ], localization_noise_step=1),
    "06_region_transition": _scenario("06_region_transition", "Region transition", [
        "###############",
        "#S......T....G#",
        "###############",
    ]),
    "07_false_transition": _scenario("07_false_transition", "False transition", [
        "###############",
        "#S..T..#.....G#",
        "#......#......#",
        "#.............#",
        "###############",
    ]),
    "08_stuck_in_corner": _scenario("08_stuck_in_corner", "Stuck in corner", [
        "#############",
        "#S..........#",
        "#...........#",
        "#..........G#",
        "#############",
    ], dynamic_blocks={1: [Point(2, 1)], 2: [Point(1, 2)]}),
    "09_input_without_movement": _scenario("09_input_without_movement", "Input without movement", [
        "###########",
        "#S.......G#",
        "###########",
    ], dynamic_blocks={1: [Point(2, 1)]}),
    "10_movement_without_expected_input": _scenario("10_movement_without_expected_input", "Movement without expected input", [
        "#############",
        "#S.........G#",
        "#...........#",
        "#############",
    ]),
    "11_lost_position": _scenario("11_lost_position", "Lost position", [
        "#############",
        "#S....L....G#",
        "#...........#",
        "#############",
    ], localization_noise_step=3),
    "12_route_replanning": _scenario("12_route_replanning", "Route replanning", [
        "###############",
        "#S............#",
        "#.............#",
        "#............G#",
        "###############",
    ], dynamic_blocks={2: [Point(4, 1), Point(4, 2)]}),
    "13_loop_prevention": _scenario("13_loop_prevention", "Loop prevention", [
        "#############",
        "#S..#......G#",
        "#...#.......#",
        "#...........#",
        "#############",
    ]),
    "14_destination_confirmation": _scenario("14_destination_confirmation", "Destination confirmation", [
        "###########",
        "#S......DG#",
        "###########",
    ]),
    "15_partial_map": _scenario("15_partial_map", "Partial map", [
        "#############",
        "#S..........#",
        "#..#####....#",
        "#.........G.#",
        "#############",
    ]),
    "16_dynamic_temporary_obstacle": _scenario("16_dynamic_temporary_obstacle", "Dynamic temporary obstacle", [
        "###############",
        "#S............#",
        "#.............#",
        "#............G#",
        "###############",
    ], dynamic_blocks={2: [Point(3, 1)], 5: []}),
}

# Friendly alias required by the prompt examples.
SCENARIOS["basic_world"] = SCENARIOS["02_multiple_paths"]


def get_scenario(scenario_id: str) -> Scenario:
    try:
        return SCENARIOS[scenario_id]
    except KeyError as exc:
        raise KeyError(f"Unknown scenario: {scenario_id}. Available: {', '.join(sorted(SCENARIOS))}") from exc
