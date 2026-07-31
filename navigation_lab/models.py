from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CellState(str, Enum):
    UNKNOWN = "unknown"
    WALKABLE = "walkable"
    BLOCKED = "blocked"
    TEMPORARY_BLOCK = "temporary_block"
    DANGEROUS = "dangerous"
    LANDMARK = "landmark"
    TRANSITION = "transition"
    DESTINATION = "destination"
    CURRENT_POSITION = "current_position"
    PLANNED_PATH = "planned_path"
    VISITED = "visited"


class NavigationState(str, Enum):
    IDLE = "IDLE"
    WAITING_FOR_WINDOW = "WAITING_FOR_WINDOW"
    OBSERVING = "OBSERVING"
    TEACHING = "TEACHING"
    LOCALIZING = "LOCALIZING"
    PLANNING = "PLANNING"
    NAVIGATING = "NAVIGATING"
    VERIFYING_PROGRESS = "VERIFYING_PROGRESS"
    VERIFYING_TRANSITION = "VERIFYING_TRANSITION"
    RELOCALIZING = "RELOCALIZING"
    STUCK = "STUCK"
    RECOVERING = "RECOVERING"
    ARRIVED = "ARRIVED"
    PAUSED = "PAUSED"
    ABORTED = "ABORTED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int

    def manhattan(self, other: "Point") -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)


@dataclass(slots=True)
class Pose:
    region_id: str
    x: float
    y: float
    confidence: float = 1.0
    source: str = "simulator"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Decision:
    action: str
    reason: str
    state: NavigationState
    current_region: str
    destination: str | None
    localization_confidence: float
    route_confidence: float
    next_point: Point | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        if self.next_point is not None:
            data["next_point"] = asdict(self.next_point)
        return data
