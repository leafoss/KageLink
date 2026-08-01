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
) -> CandidateObservation:
    cell = GridCell(x, y)
    return CandidateObservation(
        track_id=track,
        anchor_cell=cell,
        kind=ObservationKind.CLEAN_BODY,
        confidence=confidence,
        cells_touched=frozenset({cell}),
        face_hint=face_hint,
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


def built_in_scenarios() -> tuple[Scenario, ...]:
    player = GridCell(0, 0)
    return (
        Scenario(
            "distance_0_overlap",
            "D=0 uses a fresh same-cell direction hint, aims, and fires H when ready.",
            (
                CombatFrame.from_iterable(0, player, [body(1, 0, 0, face_hint="LEFT")]),
                CombatFrame.from_iterable(1, player, [body(1, 0, 0, face_hint="LEFT")]),
            ),
            expected(TargetState.LOCKED, True, 0, None, None, True),
        ),
        Scenario(
            "distance_1_adjacent",
            "D=1 aims from the current clean frame and fires H when ready.",
            (
                CombatFrame.from_iterable(0, player, [body(2, 1, 0)]),
                CombatFrame.from_iterable(1, player, [body(2, 1, 0)]),
            ),
            expected(TargetState.LOCKED, True, 1, None, None, True),
        ),
        Scenario(
            "distance_2_hold_h",
            "D=2 holds position, freshly aims, and taps H for 50ms.",
            (
                CombatFrame.from_iterable(0, player, [body(3, 2, 0)]),
                CombatFrame.from_iterable(1, player, [body(3, 2, 0)]),
            ),
            expected(TargetState.LOCKED, True, 2, None, None, True),
        ),
        Scenario(
            "distance_3_h_approach",
            "D=3 freshly aims, taps H, and approaches toward D=2.",
            (
                CombatFrame.from_iterable(0, player, [body(4, 3, 0)]),
                CombatFrame.from_iterable(1, player, [body(4, 3, 0)]),
            ),
            expected(TargetState.LOCKED, True, 3, "right", MovementPulseProfile.APPROACH, True),
        ),
        Scenario(
            "distance_4_h_approach",
            "D=4 remains in H range, freshly aims, and approaches toward D=2.",
            (
                CombatFrame.from_iterable(0, player, [body(5, 4, 0)]),
                CombatFrame.from_iterable(1, player, [body(5, 4, 0)]),
            ),
            expected(TargetState.LOCKED, True, 4, "right", MovementPulseProfile.APPROACH, True),
        ),
        Scenario(
            "distance_50_h_approach",
            "D=50 is the last valid H range cell.",
            (
                CombatFrame.from_iterable(0, player, [body(50, 50, 0)]),
                CombatFrame.from_iterable(1, player, [body(50, 50, 0)]),
            ),
            expected(TargetState.LOCKED, True, 50, "right", MovementPulseProfile.APPROACH, True),
        ),
        Scenario(
            "distance_51_approach_only",
            "D=51 is outside H range and approaches without firing.",
            (
                CombatFrame.from_iterable(0, player, [body(51, 51, 0)]),
                CombatFrame.from_iterable(1, player, [body(51, 51, 0)]),
            ),
            expected(TargetState.LOCKED, True, 51, "right", MovementPulseProfile.APPROACH, False),
        ),
        Scenario(
            "h_cooldown_blocks_repeat",
            "A second clean frame before five seconds cannot fire H again.",
            (
                CombatFrame.from_iterable(0, player, [body(60, 2, 0)], timestamp_seconds=0.0),
                CombatFrame.from_iterable(1, player, [body(60, 2, 0)], timestamp_seconds=0.5),
                CombatFrame.from_iterable(2, player, [body(60, 2, 0)], timestamp_seconds=1.0),
            ),
            expected(TargetState.LOCKED, True, 2, None, None, False),
        ),
        Scenario(
            "enemy_diagonal",
            "Diagonal D=1 uses Chebyshev distance, fresh cardinal aim, and H.",
            (
                CombatFrame.from_iterable(0, player, [body(6, -1, -1)]),
                CombatFrame.from_iterable(1, player, [body(6, -1, -1)]),
            ),
            expected(TargetState.LOCKED, True, 1, None, None, True),
        ),
        Scenario(
            "track_switch_same_cell",
            "A visual track ID change in the same cell preserves logical identity.",
            (
                CombatFrame.from_iterable(0, player, [body(10, 1, 0)]),
                CombatFrame.from_iterable(1, player, [body(10, 1, 0)]),
                CombatFrame.from_iterable(2, player, [body(77, 1, 0)]),
            ),
            expected(TargetState.LOCKED, True, 1, "right", MovementPulseProfile.VERY_SHORT, False),
        ),
        Scenario(
            "multi_cell_effect",
            "A multicell effect cannot acquire or rebind a target.",
            (
                CombatFrame.from_iterable(0, player, [multi_blob(20, {(0, 0), (1, 0), (2, 0)})]),
                CombatFrame.from_iterable(1, player, [multi_blob(21, {(0, 0), (1, 0), (2, 0)})]),
            ),
            expected(TargetState.SEARCH, False, None, None, None, False),
        ),
        Scenario(
            "short_occlusion",
            "A confirmed identity survives a short absence without movement or H authority.",
            (
                CombatFrame.from_iterable(0, player, [body(30, 2, 0)], timestamp_seconds=0.0),
                CombatFrame.from_iterable(1, player, [body(30, 2, 0)], timestamp_seconds=0.5),
                CombatFrame.from_iterable(2, player, [], timestamp_seconds=1.0),
            ),
            expected(TargetState.SUSPENDED, True, 2, None, None, False),
        ),
        Scenario(
            "ko_disables_combat",
            "KO releases R, removes combat authority, and ignores later blobs.",
            (
                CombatFrame.from_iterable(0, player, [body(40, 2, 0)]),
                CombatFrame.from_iterable(1, player, [body(40, 2, 0)]),
                CombatFrame.from_iterable(2, player, [], ko_confirmed=True),
                CombatFrame.from_iterable(3, player, [body(41, -1, 0)]),
            ),
            expected(TargetState.ENDED, False, None, None, None, False, hold_r=False),
        ),
    )
