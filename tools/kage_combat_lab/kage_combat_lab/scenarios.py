from __future__ import annotations

from dataclasses import dataclass

from .domain import CandidateObservation, CombatFrame, GridCell, ObservationKind


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    description: str
    frames: tuple[CombatFrame, ...]


def body(track: int, x: int, y: int, *, confidence: float = 0.9) -> CandidateObservation:
    cell = GridCell(x, y)
    return CandidateObservation(
        track_id=track,
        anchor_cell=cell,
        kind=ObservationKind.CLEAN_BODY,
        confidence=confidence,
        cells_touched=frozenset({cell}),
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


def built_in_scenarios() -> tuple[Scenario, ...]:
    player = GridCell(0, 0)
    return (
        Scenario(
            "enemy_right",
            "Acquire and attack a clean body in the adjacent right cell.",
            (
                CombatFrame.from_iterable(0, player, [body(1, 1, 0)]),
                CombatFrame.from_iterable(1, player, [body(1, 1, 0)]),
                CombatFrame.from_iterable(2, player, [body(2, 1, 0)]),
            ),
        ),
        Scenario(
            "enemy_diagonal",
            "Diagonal cells are adjacent by Chebyshev distance.",
            (
                CombatFrame.from_iterable(0, player, [body(3, -1, -1)]),
                CombatFrame.from_iterable(1, player, [body(3, -1, -1)]),
            ),
        ),
        Scenario(
            "track_switch_same_cell",
            "A visual track ID change in the same cell preserves logical identity.",
            (
                CombatFrame.from_iterable(0, player, [body(10, 1, 0)]),
                CombatFrame.from_iterable(1, player, [body(10, 1, 0)]),
                CombatFrame.from_iterable(2, player, [body(77, 1, 0)]),
            ),
        ),
        Scenario(
            "multi_cell_effect",
            "A multicell effect cannot acquire or rebind a target.",
            (
                CombatFrame.from_iterable(0, player, [multi_blob(20, {(0, 0), (1, 0), (2, 0)})]),
                CombatFrame.from_iterable(1, player, [multi_blob(21, {(0, 0), (1, 0), (2, 0)})]),
            ),
        ),
        Scenario(
            "short_occlusion",
            "A confirmed identity survives a short absence without movement authority.",
            (
                CombatFrame.from_iterable(0, player, [body(30, 1, 0)]),
                CombatFrame.from_iterable(1, player, [body(30, 1, 0)]),
                CombatFrame.from_iterable(2, player, []),
                CombatFrame.from_iterable(3, player, []),
                CombatFrame.from_iterable(4, player, [body(31, 1, 0)]),
            ),
        ),
        Scenario(
            "ko_disables_combat",
            "KO removes all combat authority and ignores later blobs.",
            (
                CombatFrame.from_iterable(0, player, [body(40, 1, 0)]),
                CombatFrame.from_iterable(1, player, [body(40, 1, 0)]),
                CombatFrame.from_iterable(2, player, [], ko_confirmed=True),
                CombatFrame.from_iterable(3, player, [body(41, -1, 0)]),
            ),
        ),
    )
