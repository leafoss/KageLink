from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

import numpy as np

CELL_SIZE_PX = 64


class CellState(str, Enum):
    STABLE = "STABLE"
    CHANGED = "CHANGED"
    UNCERTAIN = "UNCERTAIN"
    BASELINE_INVALID = "BASELINE_INVALID"


class SpriteClass(str, Enum):
    PLAYER = "PLAYER"
    ENEMY = "ENEMY"
    NPC = "NPC"
    UNKNOWN = "UNKNOWN"


class TrackState(str, Enum):
    TRACKED = "TRACKED"
    TEMPORARILY_MISSING = "TEMPORARILY_MISSING"
    LOST = "LOST"


class RoundState(str, Enum):
    CAPTURING_BASELINE = "CAPTURING_BASELINE"
    SEARCHING = "SEARCHING"
    TRACKING = "TRACKING"
    PURSUING = "PURSUING"
    ATTACKING = "ATTACKING"
    TARGET_TEMPORARILY_MISSING = "TARGET_TEMPORARILY_MISSING"
    TARGET_LOST = "TARGET_LOST"
    SCENE_CHANGED = "SCENE_CHANGED"


class CombatAction(str, Enum):
    NONE = "NONE"
    TURN_LEFT = "TURN_LEFT"
    TURN_RIGHT = "TURN_RIGHT"
    TURN_UP = "TURN_UP"
    TURN_DOWN = "TURN_DOWN"
    CHASE_LEFT = "CHASE_LEFT"
    CHASE_RIGHT = "CHASE_RIGHT"
    CHASE_UP = "CHASE_UP"
    CHASE_DOWN = "CHASE_DOWN"
    ATTACK = "ATTACK"


@dataclass(frozen=True, slots=True)
class ArenaRect:
    x: int
    y: int
    width: int
    height: int

    def clamp(self, frame_shape: Sequence[int]) -> "ArenaRect":
        frame_h, frame_w = int(frame_shape[0]), int(frame_shape[1])
        x = max(0, min(self.x, frame_w))
        y = max(0, min(self.y, frame_h))
        width = max(0, min(self.width, frame_w - x))
        height = max(0, min(self.height, frame_h - y))
        return ArenaRect(x=x, y=y, width=width, height=height)


@dataclass(frozen=True, order=True, slots=True)
class GridCell:
    row: int
    column: int
    x: int = field(compare=False)
    y: int = field(compare=False)
    width: int = field(compare=False)
    height: int = field(compare=False)

    @property
    def cell_id(self) -> str:
        return f"r{self.row}_c{self.column}"

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.width, self.height

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2.0, self.y + self.height / 2.0


@dataclass(slots=True)
class CellBaseline:
    cell: GridCell
    image: np.ndarray
    captured_at: float
    valid: bool = True
    stability_score: float = 0.0


@dataclass(frozen=True, slots=True)
class ComponentEvidence:
    local_bbox: tuple[int, int, int, int]
    pixel_count: int


@dataclass(slots=True)
class CellDifference:
    cell: GridCell
    difference_mask: np.ndarray
    changed_pixel_count: int
    changed_ratio: float
    components: tuple[ComponentEvidence, ...]
    state: CellState


@dataclass(frozen=True, slots=True)
class CellSearchGroup:
    """A search hint only. It deliberately has no identity or target fields."""

    group_id: int
    cells: tuple[GridCell, ...]


@dataclass(slots=True)
class AppearanceDescriptor:
    hsv_histogram: np.ndarray
    structure_vector: np.ndarray
    edge_density: float


@dataclass(slots=True)
class SpriteFragment:
    fragment_id: int
    cell: GridCell
    local_bbox: tuple[int, int, int, int]
    native_bbox: tuple[int, int, int, int]
    mask: np.ndarray
    crop: np.ndarray
    contour: np.ndarray
    pixel_count: int
    descriptor: AppearanceDescriptor


@dataclass(slots=True)
class SpriteObservation:
    observation_id: int
    source_group_id: int
    fragments: tuple[SpriteFragment, ...]
    cells: frozenset[tuple[int, int]]
    native_bbox: tuple[int, int, int, int]
    combined_mask: np.ndarray
    crop: np.ndarray
    descriptor: AppearanceDescriptor

    @property
    def center(self) -> tuple[float, float]:
        left, top, width, height = self.native_bbox
        return left + width / 2.0, top + height / 2.0


@dataclass(slots=True)
class KnownSprite:
    sprite_id: str
    name: str
    category: SpriteClass
    descriptors: tuple[AppearanceDescriptor, ...]


@dataclass(slots=True)
class TrackedSprite:
    track_id: int
    current_cells: frozenset[tuple[int, int]]
    previous_cells: frozenset[tuple[int, int]]
    fragments: tuple[SpriteFragment, ...]
    native_bbox: tuple[int, int, int, int]
    combined_mask: np.ndarray
    appearance_signature: AppearanceDescriptor
    first_seen_frame: int
    last_seen_frame: int
    missing_frames: int = 0
    observations: int = 1
    movement_history: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=12))
    classification: SpriteClass = SpriteClass.UNKNOWN
    known_enemy: bool = False
    confidence: float = 0.0
    track_state: TrackState = TrackState.TRACKED
    known_sprite_id: str | None = None

    @property
    def center(self) -> tuple[float, float]:
        left, top, width, height = self.native_bbox
        return left + width / 2.0, top + height / 2.0


@dataclass(frozen=True, slots=True)
class CombatTarget:
    track_id: int
    cells: frozenset[tuple[int, int]]
    position: tuple[float, float]
    direction: str | None
    distance_cells: int | None
    confidence: float
    visible: bool


@dataclass(slots=True)
class PR27FrameResult:
    frame_index: int
    timestamp: float
    arena_rect: ArenaRect
    arena_bgr: np.ndarray
    cells: tuple[GridCell, ...]
    differences: Mapping[tuple[int, int], CellDifference]
    groups: tuple[CellSearchGroup, ...]
    fragments: tuple[SpriteFragment, ...]
    observations: tuple[SpriteObservation, ...]
    tracks: tuple[TrackedSprite, ...]
    player_track_id: int | None
    target: CombatTarget | None
    action: CombatAction
    state: RoundState
    scene_changed: bool
    reason: str


@dataclass(slots=True)
class PR27Config:
    cell_size_px: int = CELL_SIZE_PX
    pixel_delta_threshold: int = 18
    changed_ratio_threshold: float = 0.035
    uncertain_ratio_threshold: float = 0.018
    minimum_component_area: int = 14
    morphology_kernel: int = 3
    scene_changed_cell_ratio: float = 0.42
    scene_changed_min_cells: int = 8
    scene_stable_frames: int = 3
    fragment_join_gap_px: int = 10
    association_min_score: float = 0.48
    maximum_track_cell_step: int = 2
    maximum_missing_frames: int = 3
    player_anchor_x_ratio: float = 0.50
    player_anchor_y_ratio: float = 0.54
    player_anchor_radius_px: float = 58.0
    player_confirm_frames: int = 2
    enemy_confirm_frames: int = 3
    known_sprite_threshold: float = 0.82
    attack_distance_cells: int = 1
    enable_context_enemy: bool = True

    def normalized(self) -> "PR27Config":
        self.cell_size_px = CELL_SIZE_PX
        self.pixel_delta_threshold = max(1, int(self.pixel_delta_threshold))
        self.changed_ratio_threshold = min(1.0, max(0.001, float(self.changed_ratio_threshold)))
        self.uncertain_ratio_threshold = min(
            self.changed_ratio_threshold,
            max(0.0, float(self.uncertain_ratio_threshold)),
        )
        self.minimum_component_area = max(1, int(self.minimum_component_area))
        self.morphology_kernel = max(1, int(self.morphology_kernel) | 1)
        self.scene_changed_cell_ratio = min(1.0, max(0.05, float(self.scene_changed_cell_ratio)))
        self.scene_changed_min_cells = max(2, int(self.scene_changed_min_cells))
        self.scene_stable_frames = max(2, int(self.scene_stable_frames))
        self.maximum_missing_frames = max(1, int(self.maximum_missing_frames))
        self.enemy_confirm_frames = max(2, int(self.enemy_confirm_frames))
        return self
