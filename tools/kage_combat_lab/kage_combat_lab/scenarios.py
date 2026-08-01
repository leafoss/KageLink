from __future__ import annotations

from dataclasses import dataclass

from .domain import (
    H_PULSE_MS,
    CandidateObservation,
    CombatFrame,
    GridCell,
    MovementPulseProfile,
    ObservationKind,
    TargetState,
)


@dataclass(frozen=True, slots=True)
class ScenarioExpectation:
    target_state: TargetState
    target_present: bool
    grid_distance: int | None
    move: str | None
    move_pulse_profile: MovementPulseProfile | None
    press_h: bool
    hold_r: bool = True
    h_pulse_ms: int | None = None


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    description: str
    frames: tuple[CombatFrame, ...]
    expected: ScenarioExpectation


def body(
    track: int,
    x: int,
    y: int,
    *,
    confidence: float = 0.9,
    face_hint: str | None = None,
    offset: tuple[float, float] | None = None,
) -> CandidateObservation:
    cell = GridCell(x, y)
    return CandidateObservation(
        track_id=track,
        anchor_cell=cell,
        kind=ObservationKind.CLEAN_BODY,
        confidence=confidence,
        cells_touched=frozenset({cell}),
        face_hint=face_hint,
        relative_offset_px=offset,
        motion_score=0.6,
    )


def reid_body(track: int, x: int, y: int) -> CandidateObservation:
    cell = GridCell(x, y)
    return CandidateObservation(
        track_id=track,
        anchor_cell=cell,
        kind=ObservationKind.REIDENTIFIED_BODY,
        confidence=0.45,
        body_like=True,
        cells_touched=frozenset({cell}),
        relative_offset_px=(64.0, 0.0),
        identity_score=0.82,
        appearance_score=0.76,
        position_score=0.85,
        shape_similarity=0.80,
        motion_score=0.60,
        background_probability=0.05,
        reidentified=True,
    )


def multi_blob(track: int, cells: set[tuple[int, int]]) -> CandidateObservation:
    grid_cells = frozenset(GridCell(x, y) for x, y in cells)
    anchor = sorted(grid_cells)[0]
    return CandidateObservation(
        track_id=track,
        anchor_cell=anchor,
        kind=ObservationKind.MULTI_CELL_BLOB,
        confidence=1.0,
        cells_touched=grid_cells,
    )


def expected(
    state: TargetState,
    present: bool,
    distance: int | None,
    move: str | None,
    pulse: MovementPulseProfile | None,
    press_h: bool,
    *,
    hold_r: bool = True,
) -> ScenarioExpectation:
    return ScenarioExpectation(
        state,
        present,
        distance,
        move,
        pulse,
        press_h,
        hold_r,
        H_PULSE_MS if press_h else None,
    )


def _lock_frames(track: int, cell: GridCell, *, face_hint=None, offset=None):
    player = GridCell(0, 0)
    return (
        CombatFrame.from_iterable(
            0,
            player,
            [body(track, cell.x, cell.y, face_hint=face_hint, offset=offset)],
            timestamp_seconds=0.0,
        ),
        CombatFrame.from_iterable(
            1,
            player,
            [body(track, cell.x, cell.y, face_hint=face_hint, offset=offset)],
            timestamp_seconds=0.2,
        ),
    )


def built_in_scenarios() -> tuple[Scenario, ...]:
    player = GridCell(0, 0)
    scenarios: list[Scenario] = []

    for distance, track in ((1, 2), (2, 3), (3, 4), (4, 5), (50, 50)):
        scenarios.append(
            Scenario(
                f"distance_{distance}_chase_h",
                f"D={distance} chases toward D=0 and requests H with closed-loop aim.",
                _lock_frames(track, GridCell(distance, 0)),
                expected(
                    TargetState.LOCKED,
                    True,
                    distance,
                    "right",
                    MovementPulseProfile.APPROACH,
                    True,
                ),
            )
        )

    scenarios.insert(
        0,
        Scenario(
            "distance_0_overlap",
            "D=0 uses a confirmed sub-cell direction and a 50ms microchase.",
            _lock_frames(
                1,
                GridCell(0, 0),
                face_hint="LEFT",
                offset=(-24.0, 0.0),
            ),
            expected(
                TargetState.LOCKED,
                True,
                0,
                "left",
                MovementPulseProfile.VERY_SHORT,
                True,
            ),
        ),
    )

    scenarios.extend(
        (
            Scenario(
                "distance_51_chase_only",
                "D=51 remains chase-only because H is out of range.",
                _lock_frames(51, GridCell(51, 0)),
                expected(
                    TargetState.LOCKED,
                    True,
                    51,
                    "right",
                    MovementPulseProfile.APPROACH,
                    False,
                ),
            ),
            Scenario(
                "h_cooldown_does_not_stop_chase",
                "The reserved/fired H cooldown blocks only H; chase remains active.",
                (
                    *_lock_frames(60, GridCell(2, 0)),
                    CombatFrame.from_iterable(
                        2,
                        player,
                        [body(60, 2, 0)],
                        timestamp_seconds=1.0,
                    ),
                ),
                expected(
                    TargetState.LOCKED,
                    True,
                    2,
                    "right",
                    MovementPulseProfile.APPROACH,
                    False,
                ),
            ),
            Scenario(
                "enemy_diagonal_chase",
                "Diagonal D=1 uses Chebyshev distance and stable cardinal aim.",
                _lock_frames(6, GridCell(-1, -1)),
                expected(
                    TargetState.LOCKED,
                    True,
                    1,
                    "left",
                    MovementPulseProfile.APPROACH,
                    True,
                ),
            ),
            Scenario(
                "track_switch_same_cell",
                "A raw track-ID change in the same cell preserves logical identity.",
                (
                    *_lock_frames(10, GridCell(1, 0)),
                    CombatFrame.from_iterable(
                        2,
                        player,
                        [body(77, 1, 0)],
                        timestamp_seconds=1.0,
                    ),
                ),
                expected(
                    TargetState.LOCKED,
                    True,
                    1,
                    "right",
                    MovementPulseProfile.APPROACH,
                    False,
                ),
            ),
            Scenario(
                "appearance_reid_same_logical_target",
                "A contaminated new track with strong capsule score rebinds the same target.",
                (
                    *_lock_frames(11, GridCell(1, 0)),
                    CombatFrame.from_iterable(2, player, [], timestamp_seconds=1.0),
                    CombatFrame.from_iterable(
                        3,
                        player,
                        [reid_body(99, 1, 0)],
                        timestamp_seconds=1.2,
                    ),
                ),
                expected(
                    TargetState.LOCKED,
                    True,
                    1,
                    "right",
                    MovementPulseProfile.APPROACH,
                    False,
                ),
            ),
            Scenario(
                "multi_cell_effect",
                "A multi-cell effect cannot acquire or rebind a target.",
                (
                    CombatFrame.from_iterable(
                        0,
                        player,
                        [multi_blob(20, {(0, 0), (1, 0), (2, 0)})],
                    ),
                    CombatFrame.from_iterable(
                        1,
                        player,
                        [multi_blob(21, {(0, 0), (1, 0), (2, 0)})],
                    ),
                ),
                expected(TargetState.SEARCH, False, None, None, None, False),
            ),
            Scenario(
                "occluded_coast",
                "A sub-450ms loss keeps identity and only microchases the prediction.",
                (
                    *_lock_frames(30, GridCell(2, 0)),
                    CombatFrame.from_iterable(2, player, [], timestamp_seconds=0.50),
                ),
                expected(
                    TargetState.OCCLUDED_COAST,
                    True,
                    2,
                    "right",
                    MovementPulseProfile.VERY_SHORT,
                    False,
                ),
            ),
            Scenario(
                "local_reid_hold",
                "After coast, the target stays logically retained for local ReID without blind H.",
                (
                    *_lock_frames(31, GridCell(2, 0)),
                    CombatFrame.from_iterable(2, player, [], timestamp_seconds=1.0),
                ),
                expected(
                    TargetState.REID_LOCAL,
                    True,
                    2,
                    None,
                    None,
                    False,
                ),
            ),
            Scenario(
                "ko_disables_combat",
                "KO releases R, removes target authority and ignores later blobs.",
                (
                    *_lock_frames(40, GridCell(2, 0)),
                    CombatFrame.from_iterable(
                        2,
                        player,
                        [],
                        ko_confirmed=True,
                        timestamp_seconds=1.0,
                    ),
                    CombatFrame.from_iterable(
                        3,
                        player,
                        [body(41, -1, 0)],
                        timestamp_seconds=1.2,
                    ),
                ),
                expected(
                    TargetState.ENDED,
                    False,
                    None,
                    None,
                    None,
                    False,
                    hold_r=False,
                ),
            ),
        )
    )
    return tuple(scenarios)
