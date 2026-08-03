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


class LocalBackgroundState(str, Enum):
    KNOWN_BACKGROUND = "KNOWN_BACKGROUND"
    LEARNING_BACKGROUND = "LEARNING_BACKGROUND"
    OCCUPIED_BY_PLAYER = "OCCUPIED_BY_PLAYER"
    OCCUPIED_BY_ENEMY = "OCCUPIED_BY_ENEMY"
    OCCLUDED_BY_EFFECT = "OCCLUDED_BY_EFFECT"
    UNKNOWN = "UNKNOWN"


class LocalPerceptionState(str, Enum):
    NORMAL = "NORMAL"
    LOCAL_VISUAL_OCCLUSION = "LOCAL_VISUAL_OCCLUSION"
    LOCAL_UNKNOWN_BACKGROUND = "LOCAL_UNKNOWN_BACKGROUND"


class FragmentRole(str, Enum):
    BODY_CANDIDATE = "BODY_CANDIDATE"
    GROUND_LIKE = "GROUND_LIKE"
    EFFECT_LIKE = "EFFECT_LIKE"
    NOISE = "NOISE"


class SpriteClass(str, Enum):
    PLAYER = "PLAYER"
    ENEMY = "ENEMY"
    NPC = "NPC"
    UNKNOWN = "UNKNOWN"


class SpriteRole(str, Enum):
    SELF = "SELF"
    ENEMY = "ENEMY"
    NPC = "NPC"
    UNKNOWN = "UNKNOWN"
    MERGED_BODY = "MERGED_BODY"
    EFFECT = "EFFECT"
    BACKGROUND = "BACKGROUND"


class TrackState(str, Enum):
    TRACKED = "TRACKED"
    TEMPORARILY_MISSING = "TEMPORARILY_MISSING"
    LOST = "LOST"


class SelfTrackState(str, Enum):
    SELF_TRACKED = "SELF_TRACKED"
    SELF_PREDICTED = "SELF_PREDICTED"
    SELF_TEMPORARILY_OCCLUDED = "SELF_TEMPORARILY_OCCLUDED"
    SELF_REACQUIRING = "SELF_REACQUIRING"
    SELF_LOST_CRITICAL = "SELF_LOST_CRITICAL"


class RecoveryState(str, Enum):
    NONE = "NONE"
    CLOSE_TARGET_SEARCH = "CLOSE_TARGET_SEARCH"
    CLOSE_REACQUIRE = "CLOSE_REACQUIRE"
    CLOSE_FACING_RECOVERY = "CLOSE_FACING_RECOVERY"
    MERGED_BODY_RECOVERY = "MERGED_BODY_RECOVERY"
    SEPARATION_RECOVERY = "SEPARATION_RECOVERY"
    HIT_RECOVERY = "HIT_RECOVERY"


class RoundState(str, Enum):
    CAPTURING_BASELINE = "CAPTURING_BASELINE"
    SEARCHING = "SEARCHING"
    TRACKING = "TRACKING"
    PURSUING = "PURSUING"
    ATTACKING = "ATTACKING"
    TARGET_TEMPORARILY_MISSING = "TARGET_TEMPORARILY_MISSING"
    TARGET_LOST = "TARGET_LOST"
    LOCAL_VISUAL_OCCLUSION = "LOCAL_VISUAL_OCCLUSION"
    LOCAL_UNKNOWN_BACKGROUND = "LOCAL_UNKNOWN_BACKGROUND"
    CLOSE_TARGET_SEARCH = "CLOSE_TARGET_SEARCH"
    CLOSE_REACQUIRE = "CLOSE_REACQUIRE"
    CLOSE_FACING_RECOVERY = "CLOSE_FACING_RECOVERY"
    MERGED_BODY_RECOVERY = "MERGED_BODY_RECOVERY"
    SEPARATION_RECOVERY = "SEPARATION_RECOVERY"
    HIT_RECOVERY = "HIT_RECOVERY"
    # Compatibility-only legacy member. PR27.7 never returns this state.
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
    SEPARATE_LEFT = "SEPARATE_LEFT"
    SEPARATE_RIGHT = "SEPARATE_RIGHT"
    SEPARATE_UP = "SEPARATE_UP"
    SEPARATE_DOWN = "SEPARATE_DOWN"
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

    def contains(self, point: tuple[float, float]) -> bool:
        px, py = point
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


@dataclass(slots=True)
class CellBaseline:
    cell: GridCell
    image: np.ndarray
    lab_image: np.ndarray
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
    """Search addresses only; never identity, lock, direction or combat authority."""

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
    role: FragmentRole = FragmentRole.BODY_CANDIDATE
    role_reason: str = "body geometry"
    body_score: float = 0.0


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
    body_bbox: tuple[int, int, int, int] | None = None
    body_anchor: tuple[float, float] | None = None
    anchor_cell: tuple[int, int] | None = None
    body_confidence: float = 0.0
    rejection_reason: str | None = None
    reserved_role: SpriteRole = SpriteRole.UNKNOWN
    merged_body: bool = False
    role_conflict_reason: str | None = None

    @property
    def center(self) -> tuple[float, float]:
        left, top, width, height = self.native_bbox
        return left + width / 2.0, top + height / 2.0

    @property
    def authority_position(self) -> tuple[float, float] | None:
        return self.body_anchor

    @property
    def pixel_count(self) -> int:
        return sum(fragment.pixel_count for fragment in self.fragments)

    @property
    def has_body_lock(self) -> bool:
        return self.body_bbox is not None and self.body_anchor is not None and self.anchor_cell is not None


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
    body_bbox: tuple[int, int, int, int] | None = None
    body_anchor: tuple[float, float] | None = None
    anchor_cell: tuple[int, int] | None = None
    body_confidence: float = 0.0
    missing_frames: int = 0
    observations: int = 1
    movement_history: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=12))
    classification: SpriteClass = SpriteClass.UNKNOWN
    known_enemy: bool = False
    confidence: float = 0.0
    track_state: TrackState = TrackState.TRACKED
    known_sprite_id: str | None = None
    rejection_reason: str | None = None
    observation_id: int | None = None
    role: SpriteRole = SpriteRole.UNKNOWN
    role_locked: bool = False
    role_assigned_frame: int = -1
    role_source: str = "unassigned"
    role_confidence: float = 0.0
    role_conflict_reason: str | None = None
    association_score: float = 0.0
    identity_score: float = 0.0
    predicted_anchor: tuple[float, float] | None = None
    track_source: str = "tracked"

    @property
    def center(self) -> tuple[float, float]:
        if self.body_anchor is not None:
            return self.body_anchor
        left, top, width, height = self.native_bbox
        return left + width / 2.0, top + height / 2.0

    @property
    def has_body_lock(self) -> bool:
        return self.body_bbox is not None and self.body_anchor is not None and self.anchor_cell is not None

    @property
    def effective_role(self) -> SpriteRole:
        if self.role is not SpriteRole.UNKNOWN:
            return self.role
        if self.classification is SpriteClass.PLAYER:
            return SpriteRole.SELF
        if self.classification is SpriteClass.ENEMY:
            return SpriteRole.ENEMY
        if self.classification is SpriteClass.NPC:
            return SpriteRole.NPC
        return SpriteRole.UNKNOWN


@dataclass(frozen=True, slots=True)
class CombatTarget:
    track_id: int
    cells: frozenset[tuple[int, int]]
    position: tuple[float, float]
    direction: str | None
    distance_cells: int | None
    confidence: float
    visible: bool
    body_bbox: tuple[int, int, int, int] | None = None
    body_anchor: tuple[float, float] | None = None
    anchor_cell: tuple[int, int] | None = None
    relative_anchor_px: tuple[float, float] | None = None


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
    grid_phase: tuple[int, int] = (0, 0)
    fragment_rejections: Mapping[str, int] = field(default_factory=dict)
    candidate_rejections: tuple[str, ...] = ()
    roi_center: tuple[float, float] | None = None
    roi_radius_cells: int = 4
    roi_processed_cell_count: int = 0
    ignored_outside_roi_count: int = 0
    player_cell: tuple[int, int] = (0, 0)
    player_body_bbox: tuple[int, int, int, int] | None = None
    player_body_anchor: tuple[float, float] | None = None
    player_body_containment_ratio: float = 0.0
    enemy_relative_cell: tuple[int, int] | None = None
    local_state: LocalPerceptionState = LocalPerceptionState.NORMAL
    local_background_states: Mapping[tuple[int, int], LocalBackgroundState] = field(default_factory=dict)
    local_occlusion_detected: bool = False
    facing_expected: str | None = None
    facing_detected: str | None = None
    facing_confirmed: bool = False
    facing_correction_action: str | None = None
    timings_ms: Mapping[str, float] = field(default_factory=dict)
    self_track_state: SelfTrackState = SelfTrackState.SELF_REACQUIRING
    self_role_source: str = "unavailable"
    self_confidence: float = 0.0
    self_observation_id: int | None = None
    self_predicted_anchor: tuple[float, float] | None = None
    self_association_score: float = 0.0
    self_identity_score: float = 0.0
    enemy_observation_id: int | None = None
    enemy_association_score: float = 0.0
    enemy_identity_score: float = 0.0
    enemy_relative_anchor_px: tuple[float, float] | None = None
    subcell_direction: str | None = None
    subcell_direction_confidence: float = 0.0
    role_conflict: bool = False
    role_flip_attempt: str | None = None
    role_flip_blocked: str | None = None
    shared_observation_blocked: bool = False
    merged_body_detected: bool = False
    merged_body_bbox: tuple[int, int, int, int] | None = None
    self_enemy_iou: float = 0.0
    close_candidate_count: int = 0
    close_reacquire_state: RecoveryState = RecoveryState.NONE
    deadlock_counters: Mapping[str, int] = field(default_factory=dict)
    hit_event: bool = False
    facing_commanded: str | None = None
    facing_observed: str | None = None
    facing_template_scores: Mapping[str, float] = field(default_factory=dict)
    h_block_reason: str | None = None
    recovery_action: str | None = None
    separation_action: str | None = None
    association_diagnostics: tuple[Mapping[str, object], ...] = ()


@dataclass(slots=True)
class PR27Config:
    cell_size_px: int = CELL_SIZE_PX
    pixel_delta_threshold: int = 18
    changed_ratio_threshold: float = 0.035
    uncertain_ratio_threshold: float = 0.018
    minimum_component_area: int = 28
    minimum_fragment_pixels: int = 28
    minimum_fragment_width: int = 4
    minimum_fragment_height: int = 6
    minimum_observation_pixels: int = 72
    maximum_fragments_per_group: int = 32
    morphology_kernel: int = 3
    # Legacy knobs retained for launch compatibility; unused by PR27.7 combat.
    scene_changed_cell_ratio: float = 0.42
    scene_changed_min_cells: int = 8
    scene_stable_frames: int = 3
    fragment_join_gap_px: int = 8
    association_min_score: float = 0.48
    target_association_min_score: float = 0.38
    target_minimum_appearance: float = 0.50
    maximum_track_cell_step: int = 3
    maximum_missing_frames: int = 3
    target_missing_grace_frames: int = 4
    target_focus_radius_cells: int = 3
    global_reacquire_interval_frames: int = 8
    maximum_active_tracks: int = 18
    player_anchor_x_ratio: float = 0.50
    player_anchor_y_ratio: float = 0.54
    player_anchor_radius_px: float = 58.0
    player_confirm_frames: int = 2
    enemy_confirm_frames: int = 5
    known_sprite_threshold: float = 0.82
    attack_distance_cells: int = 1
    enable_context_enemy: bool = True
    grid_player_local_x: int = 32
    grid_player_local_y: int = 56
    body_min_width: int = 6
    body_min_height: int = 12
    body_max_width: int = 96
    body_max_height: int = 112
    body_min_area: int = 110
    body_max_area: int = 9000
    body_ground_max_height: int = 14
    body_ground_min_aspect: float = 1.65
    body_lock_min_confidence: float = 0.42
    trainer_exclusion_cell_margin: int = 1
    roi_radius_cells: int = 4
    player_cell_anchor_offset_x: int = 32
    player_cell_anchor_offset_y: int = 56
    player_cell_min_containment: float = 0.90
    player_cell_hysteresis_px: int = 3
    local_occlusion_min_changed_cells: int = 10
    local_occlusion_row_span_cells: int = 6
    local_occlusion_clear_frames: int = 2
    local_occlusion_max_frames: int = 6
    local_background_learning_frames: int = 5
    local_background_alpha: float = 0.08
    facing_confirm_frames: int = 2
    facing_correction_cooldown_frames: int = 1
    hit_displacement_px: float = 10.0
    self_association_min_score: float = 0.56
    self_identity_min_score: float = 0.34
    self_size_ratio_min: float = 0.48
    self_ambiguity_margin: float = 0.08
    self_prediction_frames: int = 10
    self_reservation_margin_px: int = 6
    merged_body_iou_threshold: float = 0.08
    merged_body_area_ratio: float = 1.28
    merged_anchor_distance_px: float = 12.0
    subcell_direction_threshold_px: float = 4.0
    close_enemy_distance_px: float = 96.0
    close_reacquire_confirm_frames: int = 2
    close_idle_soft_frames: int = 3
    close_idle_turn_frames: int = 5
    close_idle_drop_frames: int = 8
    separation_pulse_ms: int = 60
    separation_cooldown_frames: int = 6
    facing_template_min_score: float = 0.72
    facing_template_margin: float = 0.04
    facing_motion_min_px: float = 3.0
    hit_appearance_similarity: float = 0.60

    def normalized(self) -> "PR27Config":
        self.cell_size_px = CELL_SIZE_PX
        self.pixel_delta_threshold = max(1, int(self.pixel_delta_threshold))
        self.changed_ratio_threshold = min(1.0, max(0.001, float(self.changed_ratio_threshold)))
        self.uncertain_ratio_threshold = min(self.changed_ratio_threshold, max(0.0, float(self.uncertain_ratio_threshold)))
        self.minimum_component_area = max(1, int(self.minimum_component_area))
        self.minimum_fragment_pixels = max(self.minimum_component_area, int(self.minimum_fragment_pixels))
        self.minimum_fragment_width = max(1, int(self.minimum_fragment_width))
        self.minimum_fragment_height = max(1, int(self.minimum_fragment_height))
        self.minimum_observation_pixels = max(self.minimum_fragment_pixels, int(self.minimum_observation_pixels))
        self.maximum_fragments_per_group = max(4, int(self.maximum_fragments_per_group))
        self.morphology_kernel = max(1, int(self.morphology_kernel) | 1)
        self.association_min_score = min(1.0, max(0.05, float(self.association_min_score)))
        self.target_association_min_score = min(self.association_min_score, max(0.05, float(self.target_association_min_score)))
        self.target_minimum_appearance = min(1.0, max(0.0, float(self.target_minimum_appearance)))
        self.maximum_track_cell_step = max(1, int(self.maximum_track_cell_step))
        self.maximum_missing_frames = max(1, int(self.maximum_missing_frames))
        self.target_missing_grace_frames = max(self.maximum_missing_frames, int(self.target_missing_grace_frames))
        self.target_focus_radius_cells = max(1, int(self.target_focus_radius_cells))
        self.global_reacquire_interval_frames = max(2, int(self.global_reacquire_interval_frames))
        self.maximum_active_tracks = max(4, int(self.maximum_active_tracks))
        self.enemy_confirm_frames = max(2, int(self.enemy_confirm_frames))
        self.player_confirm_frames = max(1, int(self.player_confirm_frames))
        self.grid_player_local_x = min(CELL_SIZE_PX - 1, max(0, int(self.grid_player_local_x)))
        self.grid_player_local_y = min(CELL_SIZE_PX - 1, max(0, int(self.grid_player_local_y)))
        self.body_min_width = max(2, int(self.body_min_width))
        self.body_min_height = max(4, int(self.body_min_height))
        self.body_max_width = max(self.body_min_width, int(self.body_max_width))
        self.body_max_height = max(self.body_min_height, int(self.body_max_height))
        self.body_min_area = max(1, int(self.body_min_area))
        self.body_max_area = max(self.body_min_area, int(self.body_max_area))
        self.body_ground_max_height = max(2, int(self.body_ground_max_height))
        self.body_ground_min_aspect = max(1.0, float(self.body_ground_min_aspect))
        self.body_lock_min_confidence = min(1.0, max(0.0, float(self.body_lock_min_confidence)))
        self.trainer_exclusion_cell_margin = max(1, int(self.trainer_exclusion_cell_margin))
        self.roi_radius_cells = max(1, int(self.roi_radius_cells))
        self.player_cell_anchor_offset_x = min(CELL_SIZE_PX - 1, max(1, int(self.player_cell_anchor_offset_x)))
        self.player_cell_anchor_offset_y = min(CELL_SIZE_PX, max(1, int(self.player_cell_anchor_offset_y)))
        self.player_cell_min_containment = min(1.0, max(0.5, float(self.player_cell_min_containment)))
        self.player_cell_hysteresis_px = max(0, int(self.player_cell_hysteresis_px))
        self.local_occlusion_min_changed_cells = max(2, int(self.local_occlusion_min_changed_cells))
        self.local_occlusion_row_span_cells = max(2, int(self.local_occlusion_row_span_cells))
        self.local_occlusion_clear_frames = max(1, int(self.local_occlusion_clear_frames))
        self.local_occlusion_max_frames = max(self.local_occlusion_clear_frames + 1, int(self.local_occlusion_max_frames))
        self.local_background_learning_frames = max(2, int(self.local_background_learning_frames))
        self.local_background_alpha = min(0.5, max(0.001, float(self.local_background_alpha)))
        self.facing_confirm_frames = max(1, int(self.facing_confirm_frames))
        self.facing_correction_cooldown_frames = max(0, int(self.facing_correction_cooldown_frames))
        self.hit_displacement_px = max(2.0, float(self.hit_displacement_px))
        self.self_association_min_score = min(1.0, max(0.1, float(self.self_association_min_score)))
        self.self_identity_min_score = min(1.0, max(0.0, float(self.self_identity_min_score)))
        self.self_size_ratio_min = min(1.0, max(0.1, float(self.self_size_ratio_min)))
        self.self_ambiguity_margin = min(0.5, max(0.0, float(self.self_ambiguity_margin)))
        self.self_prediction_frames = max(2, int(self.self_prediction_frames))
        self.self_reservation_margin_px = max(0, int(self.self_reservation_margin_px))
        self.merged_body_iou_threshold = min(1.0, max(0.0, float(self.merged_body_iou_threshold)))
        self.merged_body_area_ratio = max(1.0, float(self.merged_body_area_ratio))
        self.merged_anchor_distance_px = max(2.0, float(self.merged_anchor_distance_px))
        self.subcell_direction_threshold_px = max(1.0, float(self.subcell_direction_threshold_px))
        self.close_enemy_distance_px = max(float(CELL_SIZE_PX), float(self.close_enemy_distance_px))
        self.close_reacquire_confirm_frames = max(1, int(self.close_reacquire_confirm_frames))
        self.close_idle_soft_frames = max(1, int(self.close_idle_soft_frames))
        self.close_idle_turn_frames = max(self.close_idle_soft_frames, int(self.close_idle_turn_frames))
        self.close_idle_drop_frames = max(self.close_idle_turn_frames + 1, int(self.close_idle_drop_frames))
        self.separation_pulse_ms = min(100, max(30, int(self.separation_pulse_ms)))
        self.separation_cooldown_frames = max(1, int(self.separation_cooldown_frames))
        self.facing_template_min_score = min(1.0, max(0.1, float(self.facing_template_min_score)))
        self.facing_template_margin = min(0.5, max(0.0, float(self.facing_template_margin)))
        self.facing_motion_min_px = max(1.0, float(self.facing_motion_min_px))
        self.hit_appearance_similarity = min(1.0, max(0.0, float(self.hit_appearance_similarity)))
        return self
