from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Iterable

CELL_SIZE_PX: Final[int] = 64
GRID_CONTRACT_VERSION: Final[str] = "kage-grid-64-v1"

H_PULSE_MS: Final[int] = 50
H_COOLDOWN_SECONDS: Final[float] = 5.0
VERY_SHORT_PULSE_MS: Final[int] = 50
APPROACH_PULSE_MS: Final[int] = 100
POST_PULSE_OBSERVE_MS: Final[int] = 150
MOVEMENT_REPEAT_INTERVAL_SECONDS: Final[float] = 0.25
R_KEYDOWN_HEARTBEAT_MS: Final[int] = 250
MAX_H_RANGE_CELLS: Final[int] = 50
SHORT_OCCLUSION_SECONDS: Final[float] = 1.0
HARD_LOST_SECONDS: Final[float] = 2.0
FIRST_LIVE_TEST_MAX_SECONDS: Final[float] = 45.0
EMERGENCY_STOP_KEY: Final[str] = "F12"
DEFAULT_FRAME_SECONDS: Final[float] = 0.5

_CARDINAL_DIRECTIONS: Final[frozenset[str]] = frozenset(
    {"LEFT", "RIGHT", "UP", "DOWN"}
)


def require_canonical_cell_size(value: int | float) -> int:
    """Return the canonical cell size or fail closed."""

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


class MovementPulseProfile(str, Enum):
    """Semantic pulse profiles backed by approved physical defaults."""

    VERY_SHORT = "VERY_SHORT"
    APPROACH = "APPROACH"

    @property
    def duration_ms(self) -> int:
        return (
            VERY_SHORT_PULSE_MS
            if self is MovementPulseProfile.VERY_SHORT
            else APPROACH_PULSE_MS
        )


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
    face_hint: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.cells_touched:
            object.__setattr__(self, "cells_touched", frozenset({self.anchor_cell}))
        if self.face_hint is not None:
            normalized = str(self.face_hint).upper()
            if normalized not in _CARDINAL_DIRECTIONS:
                raise ValueError(f"face_hint must be cardinal, got {self.face_hint!r}")
            object.__setattr__(self, "face_hint", normalized)

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
    timestamp_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("frame_index must be non-negative")
        if self.timestamp_seconds is not None and self.timestamp_seconds < 0:
            raise ValueError("timestamp_seconds must be non-negative")

    @property
    def effective_time_seconds(self) -> float:
        if self.timestamp_seconds is not None:
            return float(self.timestamp_seconds)
        return float(self.frame_index) * DEFAULT_FRAME_SECONDS

    @classmethod
    def from_iterable(
        cls,
        frame_index: int,
        player_cell: GridCell,
        candidates: Iterable[CandidateObservation],
        *,
        ko_confirmed: bool = False,
        timestamp_seconds: float | None = None,
    ) -> "CombatFrame":
        return cls(
            frame_index,
            player_cell,
            tuple(candidates),
            ko_confirmed,
            timestamp_seconds,
        )


@dataclass(frozen=True, slots=True)
class CombatDecision:
    frame_index: int
    target_state: TargetState
    combat_target_id: int | None
    confirmed_cell: GridCell | None
    predicted_cell: GridCell | None
    grid_distance: int | None
    face: str | None
    move: str | None
    move_pulse_profile: MovementPulseProfile | None
    move_pulse_ms: int | None
    post_pulse_observe_ms: int
    hold_r: bool
    r_keydown_heartbeat_ms: int | None
    press_h: bool
    h_pulse_ms: int | None
    h_cooldown_remaining_seconds: float
    action_sequence: tuple[str, ...]
    reason: str


def cardinal_face(player: GridCell, target: GridCell, previous: str | None = None) -> str | None:
    dx = target.x - player.x
    dy = target.y - player.y
    if dx == 0 and dy == 0:
        return previous

    if abs(dx) == abs(dy) and previous in _CARDINAL_DIRECTIONS:
        if previous == "LEFT" and dx < 0:
            return previous
        if previous == "RIGHT" and dx > 0:
            return previous
        if previous == "UP" and dy < 0:
            return previous
        if previous == "DOWN" and dy > 0:
            return previous

    if abs(dx) >= abs(dy):
        return "RIGHT" if dx > 0 else "LEFT"
    return "DOWN" if dy > 0 else "UP"


def cardinal_move(player: GridCell, target: GridCell, previous: str | None = None) -> str | None:
    face = cardinal_face(player, target, previous)
    return None if face is None else face.lower()
