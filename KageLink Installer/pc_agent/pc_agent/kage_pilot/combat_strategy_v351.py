from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import json
import math
import os
from pathlib import Path
from typing import Iterable, Mapping, Sequence


Cell = tuple[int, int]
_CARDINAL = {"LEFT", "RIGHT", "UP", "DOWN"}


class ObservationClass(str, Enum):
    CLEAN_SINGLE_CELL_BODY = "CLEAN_SINGLE_CELL_BODY"
    BODY_SPANS_BORDER = "BODY_SPANS_BORDER"
    MULTI_CELL_EFFECT = "MULTI_CELL_EFFECT"
    TARGET_EFFECT_CONTAMINATED = "TARGET_EFFECT_CONTAMINATED"
    CAMERA_OR_SCENE_MOTION = "CAMERA_OR_SCENE_MOTION"
    UNKNOWN_BLOB = "UNKNOWN_BLOB"


class CombatPhase(str, Enum):
    COMBAT = "COMBAT"
    POST_COMBAT = "POST_COMBAT"


class PerceptionScope(str, Enum):
    GLOBAL_DISCOVERY = "GLOBAL_DISCOVERY"
    LOCKED_CELL_FOCUS = "LOCKED_CELL_FOCUS"
    PREDICTED_CELL_FOCUS = "PREDICTED_CELL_FOCUS"
    LOCAL_GRID_RECOVERY = "LOCAL_GRID_RECOVERY"
    GLOBAL_RECOVERY = "GLOBAL_RECOVERY"
    COMBAT_DISABLED = "COMBAT_DISABLED"


@dataclass(frozen=True, slots=True)
class AttackVisualContext:
    attack_id: int
    started_at: float
    origin_cell: Cell
    direction: str
    expected_cells: frozenset[Cell]
    expires_at: float

    def active(self, now: float) -> bool:
        return float(now) <= float(self.expires_at)


@dataclass(frozen=True, slots=True)
class GridObservation:
    frame_index: int
    timestamp: float
    track_id: int
    anchor_cell: Cell
    bbox_cells: frozenset[Cell]
    visible: bool
    body_like: bool
    contaminated: bool
    enemy_score: float
    appearance_signature: tuple[float, ...] = ()
    body_size: tuple[float, float] = (1.0, 1.0)
    body_cell_coverage: float = 0.0
    classification: str = ObservationClass.UNKNOWN_BLOB.value
    context_state: str = "VISIBLE"
    anchor_point: tuple[float, float] | None = None
    base_selected: bool = False
    motion_burst: bool = False

    @property
    def clean(self) -> bool:
        return bool(
            self.visible
            and self.body_like
            and not self.contaminated
            and self.classification
            in {
                ObservationClass.CLEAN_SINGLE_CELL_BODY.value,
                ObservationClass.BODY_SPANS_BORDER.value,
            }
        )

    @property
    def multi_cell(self) -> bool:
        return self.classification == ObservationClass.MULTI_CELL_EFFECT.value


@dataclass(frozen=True, slots=True)
class CombatStrategyFrame:
    frame_index: int
    timestamp: float
    player_cell: Cell
    observations: tuple[GridObservation, ...]
    attack_context: AttackVisualContext | None = None
    camera_shift: Cell = (0, 0)
    motion_burst: bool = False
    ko: bool = False


@dataclass(slots=True)
class AttentionHypothesis:
    cell: Cell
    clean_hits: int = 0
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    best_score: float = 0.0
    supporting_track_ids: set[int] = field(default_factory=set)
    best_observation: GridObservation | None = None


@dataclass(slots=True)
class GridRebindHypothesis:
    candidate_cell: Cell
    supporting_track_ids: set[int] = field(default_factory=set)
    clean_hits: int = 0
    contaminated_hits: int = 0
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    best_score: float = 0.0
    best_observation: GridObservation | None = None


@dataclass(slots=True)
class PendingRebind:
    cell: Cell
    track_id: int
    first_observation: GridObservation
    hits: int
    score: float
    hypothesis: GridRebindHypothesis


@dataclass(slots=True)
class SpatialCombatTarget:
    combat_target_id: int
    confirmed_cell: Cell
    predicted_cell: Cell
    clean_visual_track_id: int
    acquired_at: float
    last_clean_seen_at: float
    last_any_activity_at: float
    last_clean_frame: int
    confidence: float
    appearance_signature: tuple[float, ...]
    body_size: tuple[float, float]
    last_confirmed_direction: str
    previous_confirmed_cell: Cell | None = None
    pending_direction: str = "-"
    pending_direction_hits: int = 0
    current_clean_visible: bool = True
    contamination: str = "NONE"
    possible_presence_in_locked_cell: bool = False
    trail: list[Cell] = field(default_factory=list)


@dataclass(slots=True)
class StrategyMetrics:
    false_target_acquisitions: int = 0
    identity_hops: int = 0
    clean_rebinds: int = 0
    false_rebinds: int = 0
    rebind_time_total: float = 0.0
    rebind_count: int = 0
    time_without_clean_visual: float = 0.0
    time_in_melee_lock_without_clean_visual: float = 0.0
    direction_errors: int = 0
    targets_created_per_round: int = 0
    tracks_attached_per_combat_target: dict[int, set[int]] = field(default_factory=dict)
    multi_cell_blobs_promoted: int = 0
    post_ko_targets: int = 0
    global_candidates_after_lock: int = 0
    prediction_cell_jumps: int = 0

    def as_dict(self) -> dict[str, float | int]:
        average_rebind = self.rebind_time_total / max(1, self.rebind_count)
        attached = sum(len(value) for value in self.tracks_attached_per_combat_target.values())
        return {
            "false_target_acquisitions": self.false_target_acquisitions,
            "identity_hops": self.identity_hops,
            "clean_rebinds": self.clean_rebinds,
            "false_rebinds": self.false_rebinds,
            "average_rebind_time": round(average_rebind, 6),
            "time_without_clean_visual": round(self.time_without_clean_visual, 6),
            "time_in_melee_lock_without_clean_visual": round(
                self.time_in_melee_lock_without_clean_visual, 6
            ),
            "direction_errors": self.direction_errors,
            "targets_created_per_round": self.targets_created_per_round,
            "tracks_attached_per_combat_target": attached,
            "multi_cell_blobs_promoted": self.multi_cell_blobs_promoted,
            "post_ko_targets": self.post_ko_targets,
            "global_candidates_after_lock": self.global_candidates_after_lock,
            "prediction_cell_jumps": self.prediction_cell_jumps,
        }


@dataclass(frozen=True, slots=True)
class CombatTargetSnapshotV2:
    strategy: str
    combat_phase: str
    perception_scope: str
    player_cell: Cell
    confirmed_target_cell: Cell | None
    predicted_target_cell: Cell | None
    pending_rebind_cell: Cell | None
    pending_rebind_hits: int
    clean_last_seen: float
    any_activity_last_seen: float
    contamination: str
    melee_visual_authority: bool
    track_creation_enabled: bool
    attention_cell: Cell | None
    attention_hits: int
    combat_target_id: int | None
    current_visual_track_id: int | None
    target_state: str
    confidence: float
    target_age: float
    frames_since_last_seen: int
    time_since_last_seen: float
    last_known_position: tuple[float, float] | None
    predicted_position: tuple[float, float] | None
    last_contact_direction: str
    movement_mode: str
    local_rebind_radius: float
    best_rebind_score: float
    target_switch_pending: int | None
    target_switch_confirmation: int
    target_size: tuple[float, float] | None
    trail: tuple[tuple[float, float], ...]
    active: bool
    movement_authority: bool
    attack_authority: bool
    reason: str


@dataclass(frozen=True, slots=True)
class CombatStrategyConfig:
    strategy: str = "persistent_hardened"
    attention_confirm_hits: int = 2
    rebind_confirm_hits: int = 2
    clean_visual_grace_seconds: float = 0.20
    local_recovery_seconds: float = 1.20
    hard_lost_timeout: float = 3.0
    minimum_enemy_score: float = 55.0
    minimum_rebind_score: float = 0.62
    direction_confirm_hits: int = 2
    maximum_prediction_cells: int = 1
    runtime_provenance_enabled: bool = True

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object] | None) -> "CombatStrategyConfig":
        values = dict(mapping or {})
        defaults = cls()

        def integer(name: str, default: int, low: int, high: int) -> int:
            try:
                value = int(values.get(name, default))
            except (TypeError, ValueError):
                value = default
            return max(low, min(high, value))

        def number(name: str, default: float, low: float, high: float) -> float:
            try:
                value = float(values.get(name, default))
            except (TypeError, ValueError):
                value = default
            return max(low, min(high, value))

        strategy = str(
            os.getenv("KAGELINK_COMBAT_STRATEGY")
            or values.get("strategy")
            or defaults.strategy
        ).strip().lower()
        if strategy not in {"legacy_safe", "persistent_hardened", "grid_focus_v2"}:
            strategy = defaults.strategy
        return cls(
            strategy=strategy,
            attention_confirm_hits=integer(
                "attention_confirm_hits", defaults.attention_confirm_hits, 2, 5
            ),
            rebind_confirm_hits=integer(
                "rebind_confirm_hits", defaults.rebind_confirm_hits, 2, 5
            ),
            clean_visual_grace_seconds=number(
                "clean_visual_grace_seconds", defaults.clean_visual_grace_seconds, 0.05, 0.50
            ),
            local_recovery_seconds=number(
                "local_recovery_seconds", defaults.local_recovery_seconds, 0.50, 3.0
            ),
            hard_lost_timeout=number(
                "hard_lost_timeout", defaults.hard_lost_timeout, 1.25, 8.0
            ),
            minimum_enemy_score=number(
                "minimum_enemy_score", defaults.minimum_enemy_score, 20.0, 100.0
            ),
            minimum_rebind_score=number(
                "minimum_rebind_score", defaults.minimum_rebind_score, 0.20, 0.95
            ),
            direction_confirm_hits=integer(
                "direction_confirm_hits", defaults.direction_confirm_hits, 2, 5
            ),
            maximum_prediction_cells=integer(
                "maximum_prediction_cells", defaults.maximum_prediction_cells, 1, 1
            ),
            runtime_provenance_enabled=bool(
                values.get("runtime_provenance_enabled", defaults.runtime_provenance_enabled)
            ),
        )


def combat_strategy_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "kage_pilot_combat_target.json"


def load_combat_strategy_config(path: str | Path | None = None) -> CombatStrategyConfig:
    source = Path(path) if path is not None else combat_strategy_config_path()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    strategy_section = payload.get("combat_strategy", {})
    merged = dict(payload)
    if isinstance(strategy_section, dict):
        merged.update(strategy_section)
    return CombatStrategyConfig.from_mapping(merged)


def chebyshev_distance(first: Cell, second: Cell) -> int:
    return max(abs(int(first[0]) - int(second[0])), abs(int(first[1]) - int(second[1])))


def adjacent(first: Cell, second: Cell) -> bool:
    return chebyshev_distance(first, second) <= 1


def direction_between(origin: Cell, target: Cell, previous: str = "-") -> str:
    dx = int(target[0]) - int(origin[0])
    dy = int(target[1]) - int(origin[1])
    if dx == 0 and dy == 0:
        return previous if previous in _CARDINAL else "-"
    if abs(dx) >= abs(dy):
        return "RIGHT" if dx > 0 else "LEFT"
    return "DOWN" if dy > 0 else "UP"


def predicted_neighbor(cell: Cell, direction: str) -> Cell:
    delta = {
        "LEFT": (-1, 0),
        "RIGHT": (1, 0),
        "UP": (0, -1),
        "DOWN": (0, 1),
    }.get(str(direction).upper(), (0, 0))
    return int(cell[0]) + delta[0], int(cell[1]) + delta[1]


def appearance_similarity(first: Sequence[float], second: Sequence[float]) -> float:
    if not first or not second or len(first) != len(second):
        return 0.45
    left = [float(value) for value in first]
    right = [float(value) for value in second]
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    if norm <= 1e-9:
        return 0.45
    return max(0.0, min(1.0, dot / norm))


def size_similarity(first: tuple[float, float], second: tuple[float, float]) -> float:
    first_area = max(1.0, float(first[0]) * float(first[1]))
    second_area = max(1.0, float(second[0]) * float(second[1]))
    return math.exp(-abs(math.log(second_area / first_area)))


class CombatTargetStrategy(ABC):
    name = "abstract"

    def __init__(self, config: CombatStrategyConfig | None = None) -> None:
        self.config = config or CombatStrategyConfig()
        self.metrics = StrategyMetrics()
        self._phase = CombatPhase.COMBAT
        self._scope = PerceptionScope.GLOBAL_DISCOVERY
        self._target: SpatialCombatTarget | None = None
        self._attention: AttentionHypothesis | None = None
        self._pending_rebind: PendingRebind | None = None
        self._next_target_id = 1
        self._last_frame_index = 0
        self._last_timestamp = 0.0
        self._last_player_cell: Cell = (0, 0)
        self._last_reason = "round reset"
        self._best_rebind_score = 0.0
        self._last_metric_timestamp = 0.0

    @abstractmethod
    def update(self, observation: CombatStrategyFrame) -> CombatTargetSnapshotV2:
        raise NotImplementedError

    def reset_round(self) -> None:
        next_id = self._next_target_id
        config = self.config
        self.__init__(config)
        self._next_target_id = next_id

    def end_combat(self) -> None:
        self._phase = CombatPhase.POST_COMBAT
        self._scope = PerceptionScope.COMBAT_DISABLED
        self._target = None
        self._attention = None
        self._pending_rebind = None
        self._last_reason = "KO accepted; combat disabled"

    def _record_time_metrics(self, frame: CombatStrategyFrame, movement_mode: str) -> None:
        if self._last_metric_timestamp <= 0.0:
            self._last_metric_timestamp = float(frame.timestamp)
            return
        delta = max(0.0, min(1.0, float(frame.timestamp) - self._last_metric_timestamp))
        self._last_metric_timestamp = float(frame.timestamp)
        target = self._target
        if target is not None and not target.current_clean_visible:
            self.metrics.time_without_clean_visual += delta
            if movement_mode == "MELEE_LOCK":
                self.metrics.time_in_melee_lock_without_clean_visual += delta

    def _new_target(self, observation: GridObservation, player_cell: Cell) -> None:
        direction = direction_between(player_cell, observation.anchor_cell)
        target = SpatialCombatTarget(
            combat_target_id=self._next_target_id,
            confirmed_cell=observation.anchor_cell,
            predicted_cell=observation.anchor_cell,
            clean_visual_track_id=observation.track_id,
            acquired_at=float(observation.timestamp),
            last_clean_seen_at=float(observation.timestamp),
            last_any_activity_at=float(observation.timestamp),
            last_clean_frame=int(observation.frame_index),
            confidence=0.72,
            appearance_signature=tuple(observation.appearance_signature),
            body_size=tuple(observation.body_size),
            last_confirmed_direction=direction,
            current_clean_visible=True,
            trail=[observation.anchor_cell],
        )
        self._target = target
        self._next_target_id += 1
        self.metrics.targets_created_per_round += 1
        self.metrics.tracks_attached_per_combat_target[target.combat_target_id] = {
            int(observation.track_id)
        }
        if observation.multi_cell:
            self.metrics.multi_cell_blobs_promoted += 1
        self._attention = None
        self._pending_rebind = None

    def _update_direction(self, target: SpatialCombatTarget, player_cell: Cell, cell: Cell) -> None:
        candidate = direction_between(player_cell, cell, target.last_confirmed_direction)
        if candidate not in _CARDINAL or candidate == target.last_confirmed_direction:
            target.pending_direction = "-"
            target.pending_direction_hits = 0
            return
        if candidate == target.pending_direction:
            target.pending_direction_hits += 1
        else:
            target.pending_direction = candidate
            target.pending_direction_hits = 1
        if target.pending_direction_hits >= self.config.direction_confirm_hits:
            target.last_confirmed_direction = candidate
            target.pending_direction = "-"
            target.pending_direction_hits = 0

    def _accept_clean(
        self,
        observation: GridObservation,
        player_cell: Cell,
        *,
        rebound: bool,
    ) -> None:
        target = self._target
        if target is None:
            self._new_target(observation, player_cell)
            return
        previous_track = target.clean_visual_track_id
        previous_cell = target.confirmed_cell
        target.previous_confirmed_cell = previous_cell
        target.confirmed_cell = observation.anchor_cell
        target.clean_visual_track_id = int(observation.track_id)
        target.last_clean_seen_at = float(observation.timestamp)
        target.last_any_activity_at = float(observation.timestamp)
        target.last_clean_frame = int(observation.frame_index)
        target.current_clean_visible = True
        target.contamination = "NONE"
        target.possible_presence_in_locked_cell = False
        target.confidence = min(1.0, max(0.55, target.confidence + (0.03 if rebound else 0.05)))
        target.body_size = tuple(observation.body_size)
        if observation.appearance_signature:
            target.appearance_signature = tuple(observation.appearance_signature)
        self._update_direction(target, player_cell, observation.anchor_cell)
        if previous_cell != observation.anchor_cell and adjacent(previous_cell, observation.anchor_cell):
            target.predicted_cell = predicted_neighbor(
                observation.anchor_cell, target.last_confirmed_direction
            )
        else:
            target.predicted_cell = observation.anchor_cell
        target.trail.append(observation.anchor_cell)
        target.trail[:] = target.trail[-16:]
        self.metrics.tracks_attached_per_combat_target.setdefault(
            target.combat_target_id, set()
        ).add(int(observation.track_id))
        if rebound and previous_track != observation.track_id:
            self.metrics.identity_hops += 1

    def _movement_mode(self, frame: CombatStrategyFrame) -> tuple[str, bool, bool, str]:
        target = self._target
        if target is None:
            return "ATTENTION" if self._attention is not None else "SEARCH", False, False, "no target"
        elapsed = max(0.0, float(frame.timestamp) - target.last_clean_seen_at)
        local = adjacent(frame.player_cell, target.confirmed_cell)
        melee_visual = bool(target.current_clean_visible and local)
        if melee_visual:
            return "MELEE_LOCK", True, True, "current clean adjacent body"
        if local and elapsed <= self.config.clean_visual_grace_seconds:
            return "MELEE_HOLD", False, False, "short grace after clean contact"
        if target.current_clean_visible:
            return "PURSUIT", True, False, "current clean distant body"
        if elapsed < self.config.local_recovery_seconds:
            return "LOCAL_GRID_RECOVERY", False, False, "clean body temporarily absent"
        return "GLOBAL_RECOVERY", False, False, "hard local recovery expired"

    def _snapshot(self, frame: CombatStrategyFrame) -> CombatTargetSnapshotV2:
        target = self._target
        movement_mode, movement_authority, attack_authority, movement_reason = self._movement_mode(
            frame
        )
        self._record_time_metrics(frame, movement_mode)
        if self._phase == CombatPhase.POST_COMBAT and target is not None:
            self.metrics.post_ko_targets += 1
        attention_cell = self._attention.cell if self._attention else None
        attention_hits = self._attention.clean_hits if self._attention else 0
        pending_cell = self._pending_rebind.cell if self._pending_rebind else None
        pending_hits = self._pending_rebind.hits if self._pending_rebind else 0
        if target is None:
            return CombatTargetSnapshotV2(
                strategy=self.name,
                combat_phase=self._phase.value,
                perception_scope=self._scope.value,
                player_cell=frame.player_cell,
                confirmed_target_cell=None,
                predicted_target_cell=None,
                pending_rebind_cell=pending_cell,
                pending_rebind_hits=pending_hits,
                clean_last_seen=-1.0,
                any_activity_last_seen=-1.0,
                contamination="NONE",
                melee_visual_authority=False,
                track_creation_enabled=self._scope
                not in {PerceptionScope.COMBAT_DISABLED},
                attention_cell=attention_cell,
                attention_hits=attention_hits,
                combat_target_id=None,
                current_visual_track_id=None,
                target_state="ATTENTION" if self._attention else "NONE",
                confidence=0.0,
                target_age=0.0,
                frames_since_last_seen=0,
                time_since_last_seen=0.0,
                last_known_position=None,
                predicted_position=None,
                last_contact_direction="-",
                movement_mode=movement_mode,
                local_rebind_radius=1.0,
                best_rebind_score=self._best_rebind_score,
                target_switch_pending=None,
                target_switch_confirmation=pending_hits,
                target_size=None,
                trail=(),
                active=False,
                movement_authority=False,
                attack_authority=False,
                reason=self._last_reason,
            )
        elapsed = max(0.0, float(frame.timestamp) - target.last_clean_seen_at)
        state = (
            "VISIBLE"
            if target.current_clean_visible
            else "LOCAL_REBIND"
            if elapsed < self.config.hard_lost_timeout
            else "LOST"
        )
        return CombatTargetSnapshotV2(
            strategy=self.name,
            combat_phase=self._phase.value,
            perception_scope=self._scope.value,
            player_cell=frame.player_cell,
            confirmed_target_cell=target.confirmed_cell,
            predicted_target_cell=target.predicted_cell,
            pending_rebind_cell=pending_cell,
            pending_rebind_hits=pending_hits,
            clean_last_seen=target.last_clean_seen_at,
            any_activity_last_seen=target.last_any_activity_at,
            contamination=target.contamination,
            melee_visual_authority=bool(attack_authority),
            track_creation_enabled=self._scope != PerceptionScope.COMBAT_DISABLED,
            attention_cell=attention_cell,
            attention_hits=attention_hits,
            combat_target_id=target.combat_target_id,
            current_visual_track_id=(
                target.clean_visual_track_id if target.current_clean_visible else None
            ),
            target_state=state,
            confidence=max(0.0, min(1.0, target.confidence)),
            target_age=max(0.0, float(frame.timestamp) - target.acquired_at),
            frames_since_last_seen=max(0, int(frame.frame_index) - target.last_clean_frame),
            time_since_last_seen=elapsed,
            last_known_position=(
                float(target.confirmed_cell[0]), float(target.confirmed_cell[1])
            ),
            predicted_position=(
                float(target.predicted_cell[0]), float(target.predicted_cell[1])
            ),
            last_contact_direction=target.last_confirmed_direction,
            movement_mode=movement_mode,
            local_rebind_radius=1.0,
            best_rebind_score=self._best_rebind_score,
            target_switch_pending=(
                self._pending_rebind.track_id if self._pending_rebind else None
            ),
            target_switch_confirmation=pending_hits,
            target_size=target.body_size,
            trail=tuple((float(cell[0]), float(cell[1])) for cell in target.trail),
            active=self._phase == CombatPhase.COMBAT,
            movement_authority=bool(movement_authority),
            attack_authority=bool(attack_authority),
            reason=f"{self._last_reason}; {movement_reason}",
        )

    def metrics_snapshot(self) -> dict[str, float | int]:
        return self.metrics.as_dict()


class LegacySafeStrategy(CombatTargetStrategy):
    name = "legacy_safe"

    def update(self, observation: CombatStrategyFrame) -> CombatTargetSnapshotV2:
        frame = observation
        self._last_frame_index = frame.frame_index
        self._last_timestamp = frame.timestamp
        self._last_player_cell = frame.player_cell
        if frame.ko:
            self.end_combat()
        if self._phase == CombatPhase.POST_COMBAT:
            return self._snapshot(frame)

        candidates = [item for item in frame.observations if item.visible and item.body_like]
        selected = max(
            candidates,
            key=lambda item: (item.base_selected, item.enemy_score),
            default=None,
        )
        if self._target is None and selected is not None:
            self._new_target(selected, frame.player_cell)
            if not selected.clean:
                self.metrics.false_target_acquisitions += 1
            self._last_reason = "legacy immediate visual acquisition"
        elif self._target is not None:
            if selected is not None:
                rebound = selected.track_id != self._target.clean_visual_track_id
                self._accept_clean(selected, frame.player_cell, rebound=rebound)
                self._target.current_clean_visible = bool(selected.visible)
                if not selected.clean:
                    self._target.contamination = selected.classification
                self._last_reason = "legacy nearest/best track owns identity"
            else:
                self._target.current_clean_visible = False
                if frame.timestamp - self._target.last_clean_seen_at >= 1.2:
                    self._target = None
                    self._scope = PerceptionScope.GLOBAL_RECOVERY
                    self._last_reason = "legacy target expired"
        return self._snapshot(frame)


class PersistentHardenedStrategy(CombatTargetStrategy):
    name = "persistent_hardened"

    def __init__(self, config: CombatStrategyConfig | None = None) -> None:
        super().__init__(config)
        self._pending_track_id: int | None = None
        self._pending_track_hits = 0
        self._pending_started_at = 0.0

    def update(self, observation: CombatStrategyFrame) -> CombatTargetSnapshotV2:
        frame = observation
        self._last_frame_index = frame.frame_index
        self._last_timestamp = frame.timestamp
        self._last_player_cell = frame.player_cell
        if frame.ko:
            self.end_combat()
        if self._phase == CombatPhase.POST_COMBAT:
            return self._snapshot(frame)

        clean = [
            item
            for item in frame.observations
            if item.clean and item.enemy_score >= self.config.minimum_enemy_score
        ]
        if self._target is None:
            selected = max(clean, key=lambda item: item.enemy_score, default=None)
            if selected is not None:
                self._new_target(selected, frame.player_cell)
                self._scope = PerceptionScope.LOCKED_CELL_FOCUS
                self._last_reason = "hardened immediate clean acquisition"
            return self._snapshot(frame)

        target = self._target
        current = next(
            (
                item
                for item in clean
                if item.track_id == target.clean_visual_track_id
            ),
            None,
        )
        if current is not None:
            self._accept_clean(current, frame.player_cell, rebound=False)
            self._pending_track_id = None
            self._pending_track_hits = 0
            self._scope = PerceptionScope.LOCKED_CELL_FOCUS
            self._last_reason = "hardened current visible track"
            return self._snapshot(frame)

        target.current_clean_visible = False
        nearby = [
            item
            for item in clean
            if chebyshev_distance(item.anchor_cell, target.predicted_cell) <= 1
        ]
        selected = max(nearby, key=lambda item: item.enemy_score, default=None)
        if selected is not None:
            score = (
                0.50
                + 0.25 * appearance_similarity(
                    target.appearance_signature, selected.appearance_signature
                )
                + 0.25 * size_similarity(target.body_size, selected.body_size)
            )
            self._best_rebind_score = score
            if score >= self.config.minimum_rebind_score:
                if selected.track_id == self._pending_track_id:
                    self._pending_track_hits += 1
                else:
                    self._pending_track_id = selected.track_id
                    self._pending_track_hits = 1
                    self._pending_started_at = frame.timestamp
                hypothesis = GridRebindHypothesis(
                    candidate_cell=selected.anchor_cell,
                    supporting_track_ids={selected.track_id},
                    clean_hits=self._pending_track_hits,
                    first_seen_at=self._pending_started_at,
                    last_seen_at=frame.timestamp,
                    best_score=score,
                    best_observation=selected,
                )
                self._pending_rebind = PendingRebind(
                    cell=selected.anchor_cell,
                    track_id=selected.track_id,
                    first_observation=selected,
                    hits=self._pending_track_hits,
                    score=score,
                    hypothesis=hypothesis,
                )
                if self._pending_track_hits >= self.config.rebind_confirm_hits:
                    elapsed = max(0.0, frame.timestamp - self._pending_started_at)
                    self._accept_clean(selected, frame.player_cell, rebound=True)
                    self.metrics.clean_rebinds += 1
                    self.metrics.rebind_count += 1
                    self.metrics.rebind_time_total += elapsed
                    self._pending_rebind = None
                    self._pending_track_id = None
                    self._pending_track_hits = 0
                    self._last_reason = "track-oriented hardened rebind confirmed"
        elapsed = frame.timestamp - target.last_clean_seen_at
        self._scope = (
            PerceptionScope.LOCAL_GRID_RECOVERY
            if elapsed < self.config.local_recovery_seconds
            else PerceptionScope.GLOBAL_RECOVERY
        )
        if elapsed >= self.config.hard_lost_timeout:
            self._target = None
            self._pending_rebind = None
            self._last_reason = "hardened target hard-lost"
        return self._snapshot(frame)


class GridFocusV2Strategy(CombatTargetStrategy):
    name = "grid_focus_v2"

    def __init__(self, config: CombatStrategyConfig | None = None) -> None:
        super().__init__(config)
        self._rebind_hypotheses: dict[Cell, GridRebindHypothesis] = {}

    def _clean_candidates(self, frame: CombatStrategyFrame) -> list[GridObservation]:
        result: list[GridObservation] = []
        attack = frame.attack_context
        for item in frame.observations:
            contaminated_by_attack = bool(
                attack is not None
                and attack.active(frame.timestamp)
                and item.anchor_cell in attack.expected_cells
            )
            if item.multi_cell:
                continue
            if contaminated_by_attack or frame.motion_burst or item.motion_burst:
                continue
            if item.clean and item.enemy_score >= self.config.minimum_enemy_score:
                result.append(item)
        return result

    def _update_attention(self, frame: CombatStrategyFrame, clean: list[GridObservation]) -> None:
        if not clean:
            self._attention = None
            self._last_reason = "no clean acquisition evidence"
            return
        grouped: dict[Cell, list[GridObservation]] = {}
        for item in clean:
            grouped.setdefault(item.anchor_cell, []).append(item)
        cell, items = max(
            grouped.items(),
            key=lambda value: max(item.enemy_score for item in value[1]),
        )
        best = max(items, key=lambda item: item.enemy_score)
        if self._attention is None or self._attention.cell != cell:
            self._attention = AttentionHypothesis(
                cell=cell,
                clean_hits=1,
                first_seen_at=frame.timestamp,
                last_seen_at=frame.timestamp,
                best_score=best.enemy_score,
                supporting_track_ids={item.track_id for item in items},
                best_observation=best,
            )
        else:
            self._attention.clean_hits += 1
            self._attention.last_seen_at = frame.timestamp
            self._attention.best_score = max(self._attention.best_score, best.enemy_score)
            self._attention.supporting_track_ids.update(item.track_id for item in items)
            if best.enemy_score >= self._attention.best_score:
                self._attention.best_observation = best
        self._last_reason = (
            f"ATTENTION cell={cell} hits={self._attention.clean_hits}; identity not created"
        )
        if self._attention.clean_hits >= self.config.attention_confirm_hits:
            selected = self._attention.best_observation or best
            self._new_target(selected, frame.player_cell)
            self._scope = PerceptionScope.LOCKED_CELL_FOCUS
            self._last_reason = "TARGET_CONFIRMED by coherent clean cell evidence"

    def _focused_cells(self, frame: CombatStrategyFrame) -> set[Cell]:
        target = self._target
        if target is None:
            return set()
        elapsed = max(0.0, frame.timestamp - target.last_clean_seen_at)
        if target.current_clean_visible:
            return {target.confirmed_cell}
        if elapsed <= self.config.clean_visual_grace_seconds:
            return {target.confirmed_cell, target.predicted_cell}
        if elapsed < self.config.local_recovery_seconds:
            cells: set[Cell] = set()
            for origin in {target.confirmed_cell, target.predicted_cell}:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        cells.add((origin[0] + dx, origin[1] + dy))
            return cells
        return set()

    def _contaminated_presence(self, frame: CombatStrategyFrame) -> None:
        target = self._target
        if target is None:
            return
        for item in frame.observations:
            if item.anchor_cell not in {target.confirmed_cell, target.predicted_cell}:
                continue
            if item.clean:
                continue
            target.last_any_activity_at = max(target.last_any_activity_at, frame.timestamp)
            target.contamination = item.classification
            target.possible_presence_in_locked_cell = True
            hypothesis = self._rebind_hypotheses.get(item.anchor_cell)
            if hypothesis is None:
                hypothesis = GridRebindHypothesis(
                    candidate_cell=item.anchor_cell,
                    first_seen_at=frame.timestamp,
                    last_seen_at=frame.timestamp,
                )
                self._rebind_hypotheses[item.anchor_cell] = hypothesis
            hypothesis.contaminated_hits += 1
            hypothesis.last_seen_at = frame.timestamp
            self._last_reason = (
                f"contaminated activity in locked hypothesis {item.anchor_cell}; memory unchanged"
            )

    def _rebind_score(self, target: SpatialCombatTarget, item: GridObservation) -> float:
        cell_distance = chebyshev_distance(target.confirmed_cell, item.anchor_cell)
        if cell_distance > 1:
            return 0.0
        distance_score = 1.0 if item.anchor_cell == target.confirmed_cell else 0.78
        appearance = appearance_similarity(
            target.appearance_signature, item.appearance_signature
        )
        size = size_similarity(target.body_size, item.body_size)
        return max(0.0, min(1.0, 0.50 * distance_score + 0.30 * appearance + 0.20 * size))

    def _update_rebind(self, frame: CombatStrategyFrame, candidates: list[GridObservation]) -> None:
        target = self._target
        if target is None:
            return
        focused = self._focused_cells(frame)
        eligible = [item for item in candidates if item.anchor_cell in focused]
        for item in candidates:
            if item.anchor_cell not in focused:
                self.metrics.global_candidates_after_lock += 1
        if not eligible:
            self._pending_rebind = None
            return
        by_cell: dict[Cell, list[GridObservation]] = {}
        for item in eligible:
            if chebyshev_distance(target.confirmed_cell, item.anchor_cell) > 1:
                self.metrics.false_rebinds += 1
                continue
            by_cell.setdefault(item.anchor_cell, []).append(item)
        if not by_cell:
            return
        cell, items = max(
            by_cell.items(),
            key=lambda value: max(self._rebind_score(target, item) for item in value[1]),
        )
        best = max(items, key=lambda item: self._rebind_score(target, item))
        score = self._rebind_score(target, best)
        self._best_rebind_score = score
        if score < self.config.minimum_rebind_score:
            self._pending_rebind = None
            return
        hypothesis = self._rebind_hypotheses.get(cell)
        if hypothesis is None or frame.timestamp - hypothesis.last_seen_at > 0.75:
            hypothesis = GridRebindHypothesis(
                candidate_cell=cell,
                first_seen_at=frame.timestamp,
                last_seen_at=frame.timestamp,
            )
            self._rebind_hypotheses[cell] = hypothesis
        hypothesis.clean_hits += 1
        hypothesis.last_seen_at = frame.timestamp
        hypothesis.supporting_track_ids.update(item.track_id for item in items)
        if score >= hypothesis.best_score:
            hypothesis.best_score = score
            hypothesis.best_observation = best
        self._pending_rebind = PendingRebind(
            cell=cell,
            track_id=best.track_id,
            first_observation=hypothesis.best_observation or best,
            hits=hypothesis.clean_hits,
            score=hypothesis.best_score,
            hypothesis=hypothesis,
        )
        self._last_reason = (
            f"rebind quarantined cell={cell} clean_hits={hypothesis.clean_hits}"
        )
        if hypothesis.clean_hits < self.config.rebind_confirm_hits:
            return
        accepted = hypothesis.best_observation or best
        if chebyshev_distance(target.confirmed_cell, accepted.anchor_cell) > 1:
            self.metrics.false_rebinds += 1
            self._pending_rebind = None
            return
        elapsed = max(0.0, frame.timestamp - hypothesis.first_seen_at)
        self._accept_clean(accepted, frame.player_cell, rebound=True)
        self.metrics.clean_rebinds += 1
        self.metrics.rebind_count += 1
        self.metrics.rebind_time_total += elapsed
        self._pending_rebind = None
        self._rebind_hypotheses.clear()
        self._scope = PerceptionScope.LOCKED_CELL_FOCUS
        self._last_reason = "spatial rebind confirmed after clean quarantine"

    def update(self, observation: CombatStrategyFrame) -> CombatTargetSnapshotV2:
        frame = observation
        self._last_frame_index = frame.frame_index
        self._last_timestamp = frame.timestamp
        self._last_player_cell = frame.player_cell
        if frame.ko:
            self.end_combat()
        if self._phase == CombatPhase.POST_COMBAT:
            return self._snapshot(frame)

        clean = self._clean_candidates(frame)
        if self._target is None:
            self._scope = (
                PerceptionScope.GLOBAL_RECOVERY
                if self._scope == PerceptionScope.GLOBAL_RECOVERY
                else PerceptionScope.GLOBAL_DISCOVERY
            )
            self._update_attention(frame, clean)
            return self._snapshot(frame)

        target = self._target
        self._contaminated_presence(frame)
        current = next(
            (
                item
                for item in clean
                if item.track_id == target.clean_visual_track_id
                and item.anchor_cell == target.confirmed_cell
            ),
            None,
        )
        if current is not None:
            self._accept_clean(current, frame.player_cell, rebound=False)
            self._pending_rebind = None
            self._rebind_hypotheses.clear()
            self._scope = PerceptionScope.LOCKED_CELL_FOCUS
            self._last_reason = "clean body remains in confirmed cell"
            return self._snapshot(frame)

        target.current_clean_visible = False
        elapsed = max(0.0, frame.timestamp - target.last_clean_seen_at)
        if elapsed <= self.config.clean_visual_grace_seconds:
            self._scope = PerceptionScope.PREDICTED_CELL_FOCUS
        elif elapsed < self.config.local_recovery_seconds:
            self._scope = PerceptionScope.LOCAL_GRID_RECOVERY
        else:
            self._scope = PerceptionScope.GLOBAL_RECOVERY

        self._update_rebind(frame, clean)
        if self._target is not None and elapsed >= self.config.hard_lost_timeout:
            self._target = None
            self._pending_rebind = None
            self._rebind_hypotheses.clear()
            self._attention = None
            self._scope = PerceptionScope.GLOBAL_RECOVERY
            self._last_reason = "hard clean-visual loss; global recovery re-enabled"
        return self._snapshot(frame)


STRATEGY_TYPES: dict[str, type[CombatTargetStrategy]] = {
    LegacySafeStrategy.name: LegacySafeStrategy,
    PersistentHardenedStrategy.name: PersistentHardenedStrategy,
    GridFocusV2Strategy.name: GridFocusV2Strategy,
}


def create_combat_target_strategy(
    name: str | None = None,
    config: CombatStrategyConfig | None = None,
) -> CombatTargetStrategy:
    settings = config or load_combat_strategy_config()
    selected = str(name or settings.strategy).strip().lower()
    strategy_type = STRATEGY_TYPES.get(selected, PersistentHardenedStrategy)
    return strategy_type(settings)


__all__ = [
    "AttackVisualContext",
    "AttentionHypothesis",
    "Cell",
    "CombatPhase",
    "CombatStrategyConfig",
    "CombatStrategyFrame",
    "CombatTargetSnapshotV2",
    "CombatTargetStrategy",
    "GridFocusV2Strategy",
    "GridObservation",
    "GridRebindHypothesis",
    "LegacySafeStrategy",
    "ObservationClass",
    "PendingRebind",
    "PerceptionScope",
    "PersistentHardenedStrategy",
    "SpatialCombatTarget",
    "StrategyMetrics",
    "adjacent",
    "appearance_similarity",
    "chebyshev_distance",
    "combat_strategy_config_path",
    "create_combat_target_strategy",
    "direction_between",
    "load_combat_strategy_config",
    "predicted_neighbor",
    "size_similarity",
]
