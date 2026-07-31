from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Iterable

CELL_SIZE_PX: Final[int] = 64
GRID_CONTRACT_VERSION: Final[str] = "kage-grid-64-v1"


def require_canonical_cell_size(value: int | float) -> int:
    """Return the canonical cell size or fail closed.

    The Combat Lab models the BYOND combat lattice as 64×64 pixel cells. This is a
    protected product contract, not a tuning parameter.
    """

    normalized = int(value)
    if float(value) != float(CELL_SIZE_PX) or normalized != CELL_SIZE_PX:
        raise ValueError(
            f"KAGE_GRID_CELL_SIZE_IMMUTABLE: expected {CELL_SIZE_PX}px, got {value!r}"
        )
    return CELL_SIZE_PX


class ObservationKind(str, Enum):
    CLEAN_BODY = "CLEAN_BODY"
    CONTAMINATED_ACTIVITY = "CONTAMINATED_ACTIVITY"
    MULTI_CELL_BLOB = "MULTI_CELL_BLOB"
    EMPTY = "EMPTY"
    KO = "KO"


class TargetState(str, Enum):
    SEARCH = "SEARCH"
    ATTENTION = "ATTENTION"
    LOCKED = "LOCKED"
    SUSPENDED = "SUSPENDED"
    ENDED = "ENDED"


@dataclass(frozen=True, order=True, slots=True)
class GridCell:
    x: int
    y: int

    def chebyshev_distance(self, other: "GridCell") -> int:
        return max(abs(self.x - other.x), abs(self.y - other.y))

    def is_adjacent_to(self, other: "GridCell") -> bool:
        return self.chebyshev_distance(other) <= 1

    def step_toward(self, other: "GridCell") -> "GridCell":
        def step(delta: int) -> int:
            return 0 if delta == 0 else (1 if delta > 0 else -1)

        return GridCell(self.x + step(other.x - self.x), self.y + step(other.y - self.y))


@dataclass(frozen=True, slots=True)
class CandidateObservation:
    track_id: int
    anchor_cell: GridCell
    kind: ObservationKind
    visible: bool = True
    body_like: bool = True
    confidence: float = 1.0
    cells_touched: frozenset[GridCell] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.cells_touched:
            object.__setattr__(self, "cells_touched", frozenset({self.anchor_cell}))

    @property
    def is_single_cell(self) -> bool:
        return len(self.cells_touched) == 1

    @property
    def is_clean_body(self) -> bool:
        return (
            self.kind is ObservationKind.CLEAN_BODY
            and self.visible
            and self.body_like
            and self.is_single_cell
        )


@dataclass(frozen=True, slots=True)
class CombatFrame:
    frame_index: int
    player_cell: GridCell
    candidates: tuple[CandidateObservation, ...] = ()
    ko_confirmed: bool = False

    @classmethod
    def from_iterable(
        cls,
        frame_index: int,
        player_cell: GridCell,
        candidates: Iterable[CandidateObservation],
        *,
        ko_confirmed: bool = False,
    ) -> "CombatFrame":
        return cls(frame_index, player_cell, tuple(candidates), ko_confirmed)


@dataclass(frozen=True, slots=True)
class CombatDecision:
    frame_index: int
    target_state: TargetState
    combat_target_id: int | None
    confirmed_cell: GridCell | None
    predicted_cell: GridCell | None
    face: str | None
    move: str | None
    attack_primary: bool
    attack_secondary: bool
    reason: str


CARDINAL_BY_DELTA: Final[dict[tuple[int, int], str]] = {
    (-1, 0): "LEFT",
    (1, 0): "RIGHT",
    (0, -1): "UP",
    (0, 1): "DOWN",
}


def cardinal_face(player: GridCell, target: GridCell, previous: str | None = None) -> str | None:
    dx = target.x - player.x
    dy = target.y - player.y
    if dx == 0 and dy == 0:
        return previous
    if abs(dx) >= abs(dy):
        return "RIGHT" if dx > 0 else "LEFT"
    return "DOWN" if dy > 0 else "UP"


def cardinal_move(player: GridCell, target: GridCell) -> str | None:
    face = cardinal_face(player, target)
    return None if face is None else face.lower()
