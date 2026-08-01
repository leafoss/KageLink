from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import time
from typing import Any, Callable

from .combat_strategy_v351 import (
    AttackVisualContext,
    CombatPhase,
    CombatStrategyConfig,
    CombatStrategyFrame,
    CombatTargetSnapshotV2,
    GridObservation,
    ObservationClass,
    PerceptionScope,
    chebyshev_distance,
    combat_strategy_config_path,
    create_combat_target_strategy,
    direction_between,
    load_combat_strategy_config,
)
from .combat_target_config_v351 import load_combat_target_config
from .combat_target_filter_v351 import (
    candidate_bbox,
    combat_body_rejection_reason,
    effect_rejection_reason,
)
from .combat_target_model_v351 import RejectedCandidate


Telemetry = Callable[[str, dict[str, object]], None]
_CARDINAL = {"LEFT", "RIGHT", "UP", "DOWN"}
_DIRECTION_KEYS = {
    "LEFT": "left",
    "RIGHT": "right",
    "UP": "up",
    "DOWN": "down",
}
_CURRENT_COMMANDS: dict[int, str] = {}


@dataclass(frozen=True, slots=True)
class StrategyCombatDecision:
    mode: str
    navigation: str
    face: str
    base_r: bool
    h_opportunity: bool
    target_id: int | None
    grid_distance: int | None
    reason: str
    engagement_active: bool
    engagement_stable_seconds: float
    combat_target_id: int | None
    visual_track_id: int | None
    target_state: str
    target_confidence: float
    movement_mode: str
    predicted_position: tuple[float, float] | None
    time_since_last_seen: float
    strategy: str
    combat_phase: str
    perception_scope: str
    player_cell: tuple[int, int]
    confirmed_target_cell: tuple[int, int] | None
    predicted_target_cell: tuple[int, int] | None
    pending_rebind_cell: tuple[int, int] | None
    pending_rebind_hits: int
    contamination: str
    melee_visual_authority: bool
    track_creation_enabled: bool
    movement_authority: bool
    attack_authority: bool


@dataclass(frozen=True, slots=True)
class InstalledCombatRuntime:
    strategy_name: str
    config: CombatStrategyConfig
    config_path: Path
    tracker_class: type
    observer_class: type
    engine_class: type
    planner_class: type
    watcher_class: type


class _RuntimeRegistry:
    def __init__(self) -> None:
        self.installed: InstalledCombatRuntime | None = None
        self.active_observer: Any | None = None
        self.active_planner: Any | None = None
        self.provenance_emitted = False

    def end_combat(self) -> None:
        observer = self.active_observer
        if observer is not None and hasattr(observer, "end_combat"):
            observer.end_combat()
        planner = self.active_planner
        if planner is not None and hasattr(planner, "reset"):
            planner.reset()


_REGISTRY = _RuntimeRegistry()


def current_runtime_command(combat_target_id: int | None) -> str:
    if combat_target_id is None:
        return "-"
    return _CURRENT_COMMANDS.get(int(combat_target_id), "-")


def _class_name(value: object) -> str:
    cls = value if isinstance(value, type) else type(value)
    return f"{cls.__module__}.{cls.__qualname__}"


def _context_state(context: Any) -> str:
    return str(getattr(context, "state", "LOST") or "LOST").upper()


def _appearance(context: Any) -> tuple[float, ...]:
    value = getattr(context, "appearance", ())
    try:
        return tuple(float(item) for item in value)
    except Exception:
        return ()


def _cells_for_bbox(observer: Any, state: Any, bbox: tuple[int, int, int, int]) -> frozenset[tuple[int, int]]:
    x, y, width, height = bbox
    points = (
        (float(x), float(y)),
        (float(x + max(0, width - 1)), float(y)),
        (float(x), float(y + max(0, height - 1))),
        (float(x + max(0, width - 1)), float(y + max(0, height - 1))),
    )
    frame_cell = getattr(observer, "_frame_cell", None)
    if not callable(frame_cell):
        return frozenset()
    corner_cells = [frame_cell(point, state) for point in points]
    min_x = min(cell[0] for cell in corner_cells)
    max_x = max(cell[0] for cell in corner_cells)
    min_y = min(cell[1] for cell in corner_cells)
    max_y = max(cell[1] for cell in corner_cells)
    return frozenset(
        (cell_x, cell_y)
        for cell_y in range(min_y, max_y + 1)
        for cell_x in range(min_x, max_x + 1)
    )


def _body_cell_coverage(
    observer: Any,
    state: Any,
    bbox: tuple[int, int, int, int],
    anchor_cell: tuple[int, int],
) -> float:
    x, y, width, height = (float(value) for value in bbox)
    tile = max(1.0, float(getattr(observer, "tile_size", 32.0) or 32.0))
    arena = tuple(float(value) for value in state.arena_rect)
    origin_x = float(getattr(observer, "grid_origin_x", 0.0) or 0.0)
    origin_y = float(getattr(observer, "grid_origin_y", 0.0) or 0.0)
    full_left = origin_x + anchor_cell[0] * tile
    full_top = origin_y + anchor_cell[1] * tile
    local_left = full_left - arena[0]
    local_top = full_top - arena[1]
    intersection_width = max(0.0, min(x + width, local_left + tile) - max(x, local_left))
    intersection_height = max(0.0, min(y + height, local_top + tile) - max(y, local_top))
    return max(0.0, min(1.0, intersection_width * intersection_height / max(1.0, width * height)))


def _classification(
    *,
    context_state: str,
    body_reason: str | None,
    bbox_cells: frozenset[tuple[int, int]],
    body_like: bool,
    coverage: float,
    motion_burst: bool,
) -> tuple[str, bool]:
    if motion_burst:
        return ObservationClass.CAMERA_OR_SCENE_MOTION.value, True
    if context_state != "VISIBLE":
        return ObservationClass.UNKNOWN_BLOB.value, True
    if body_reason is not None:
        if any(
            marker in body_reason
            for marker in ("WIDE", "TALL", "HORIZONTAL", "VERTICAL", "AREA", "BORDER")
        ):
            return ObservationClass.MULTI_CELL_EFFECT.value, True
        return ObservationClass.UNKNOWN_BLOB.value, True
    if len(bbox_cells) >= 3:
        return ObservationClass.MULTI_CELL_EFFECT.value, True
    if body_like and len(bbox_cells) == 1:
        return ObservationClass.CLEAN_SINGLE_CELL_BODY.value, False
    if body_like and len(bbox_cells) <= 2 and coverage >= 0.34:
        return ObservationClass.BODY_SPANS_BORDER.value, False
    return ObservationClass.UNKNOWN_BLOB.value, True


def _observation_for_track(observer: Any, state: Any, track: Any, *, frame_index: int) -> GridObservation:
    track_id = int(getattr(track, "track_id", 0) or 0)
    context = observer.tracker.context_for(track_id)
    metrics = observer.metrics_for(track_id)
    bbox = candidate_bbox(track)
    anchor_method = getattr(observer, "_track_anchor", None)
    if callable(anchor_method):
        anchor_point = tuple(float(value) for value in anchor_method(track))
    else:
        x, y, width, height = bbox
        anchor_point = (x + width * 0.50, y + height * 0.90)
    if metrics is not None:
        anchor_cell = tuple(int(value) for value in getattr(metrics, "cell"))
    else:
        frame_cell = getattr(observer, "_frame_cell", None)
        anchor_cell = tuple(int(value) for value in frame_cell(anchor_point, state))
    bbox_cells = _cells_for_bbox(observer, state, bbox)
    coverage = _body_cell_coverage(observer, state, bbox, anchor_cell)
    body_reason = observer.combat_track_rejection_reason(
        track,
        state=state,
        for_acquire=False,
    )
    context_value = _context_state(context)
    body_like = body_reason is None
    classification, contaminated = _classification(
        context_state=context_value,
        body_reason=body_reason,
        bbox_cells=bbox_cells,
        body_like=body_like,
        coverage=coverage,
        motion_burst=False,
    )
    return GridObservation(
        frame_index=int(frame_index),
        timestamp=float(state.timestamp),
        track_id=track_id,
        anchor_cell=anchor_cell,
        bbox_cells=bbox_cells,
        visible=context_value == "VISIBLE",
        body_like=body_like,
        contaminated=contaminated,
        enemy_score=float(getattr(track, "enemy_score", 0.0) or 0.0),
        appearance_signature=_appearance(context),
        body_size=(float(bbox[2]), float(bbox[3])),
        body_cell_coverage=coverage,
        classification=classification,
        context_state=context_value,
        anchor_point=anchor_point,
        base_selected=int(getattr(state, "target_id", -1) or -1) == track_id,
    )


def _player_cell(observer: Any, state: Any) -> tuple[int, int]:
    anchor_method = getattr(observer, "_player_anchor", None)
    frame_cell = getattr(observer, "_frame_cell", None)
    if callable(anchor_method) and callable(frame_cell):
        return tuple(int(value) for value in frame_cell(anchor_method(state), state))
    for track in tuple(getattr(state, "tracks", ()) or ()):
        metrics = observer.metrics_for(int(getattr(track, "track_id", 0) or 0))
        if metrics is not None:
            return tuple(int(value) for value in getattr(metrics, "player_cell"))
    return (0, 0)


def _grid_distance_for_snapshot(snapshot: CombatTargetSnapshotV2) -> int | None:
    if snapshot.confirmed_target_cell is None:
        return None
    return chebyshev_distance(snapshot.player_cell, snapshot.confirmed_target_cell)


def _direction_for_snapshot(snapshot: CombatTargetSnapshotV2) -> str:
    if snapshot.confirmed_target_cell is None:
        if snapshot.attention_cell is None:
            return "-"
        return direction_between(snapshot.player_cell, snapshot.attention_cell)
    return direction_between(
        snapshot.player_cell,
        snapshot.confirmed_target_cell,
        snapshot.last_contact_direction,
    )


class StrategyFilteredTrackerMixin:
    _strategy_telemetry: Telemetry | None = None
    _legacy_combat_config = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.raw_candidate_count = 0
        self.filtered_candidate_count = 0
        self.rejected_candidates: tuple[RejectedCandidate, ...] = ()
        self._last_rejection_signature: tuple[tuple[str, tuple[int, int, int, int]], ...] = ()
        self._last_rejection_at = -1e9

    def update(self, candidates, *, flow, player_center, now):
        raw = list(candidates)
        gray = getattr(self, "_frame_gray", None)
        frame_shape = tuple(gray.shape[:2]) if getattr(gray, "size", 0) else None
        config = self._legacy_combat_config or load_combat_target_config()
        filtered = []
        rejected: list[RejectedCandidate] = []
        for candidate in raw:
            reason = effect_rejection_reason(
                candidate,
                frame_shape=frame_shape,
                flow=flow,
                player_center=player_center,
                config=config,
            )
            if reason is None:
                filtered.append(candidate)
            else:
                rejected.append(RejectedCandidate(candidate_bbox(candidate), reason))
        self.raw_candidate_count = len(raw)
        self.filtered_candidate_count = len(filtered)
        self.rejected_candidates = tuple(rejected)
        signature = tuple((item.reason, item.bbox) for item in rejected[:12])
        telemetry = self._strategy_telemetry
        if signature and (
            signature != self._last_rejection_signature
            or float(now) - self._last_rejection_at >= 0.75
        ):
            self._last_rejection_signature = signature
            self._last_rejection_at = float(now)
            if telemetry is not None:
                telemetry(
                    "DOJO_COMBAT_CANDIDATES_REJECTED",
                    {
                        "count": len(rejected),
                        "reasons": ",".join(sorted({item.reason for item in rejected})),
                        "raw_candidates": len(raw),
                        "filtered_candidates": len(filtered),
                    },
                )
        result = super().update(filtered, flow=flow, player_center=player_center, now=now)
        suppressed = int(
            getattr(getattr(self, "background", None), "suppressed_last_frame", 0) or 0
        )
        self.filtered_candidate_count = max(0, len(filtered) - suppressed)
        return result


class StrategyObserverMixin:
    _strategy_config = CombatStrategyConfig()
    _strategy_telemetry: Telemetry | None = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.combat_strategy = create_combat_target_strategy(config=self._strategy_config)
        self._combat_frame_index = 0
        self._combat_last_snapshot = self.combat_strategy._snapshot(
            CombatStrategyFrame(0, time.monotonic(), (0, 0), ())
        )
        self._last_strategy_observations: tuple[GridObservation, ...] = ()
        self._attack_visual_context: AttackVisualContext | None = None
        self._last_body_rejection: tuple[int, str] | None = None
        self._last_body_rejection_at = -1e9
        _REGISTRY.active_observer = self

    @property
    def combat_target_id(self) -> int | None:
        return self._combat_last_snapshot.combat_target_id

    @property
    def combat_target_state(self) -> str:
        return self._combat_last_snapshot.target_state

    @property
    def target_mode(self) -> str:
        return self._combat_last_snapshot.perception_scope

    def combat_snapshot(self) -> CombatTargetSnapshotV2:
        return self._combat_last_snapshot

    def strategy_metrics(self) -> dict[str, float | int]:
        return self.combat_strategy.metrics_snapshot()

    def set_attack_visual_context(self, value: AttackVisualContext | None) -> None:
        self._attack_visual_context = value

    def end_combat(self) -> None:
        self.combat_strategy.end_combat()
        self._grid_target_id = None
        self._locked_target_id = None
        tracker = getattr(self, "tracker", None)
        if tracker is not None and hasattr(tracker, "full_reset"):
            tracker.full_reset()

    def reset(self) -> None:
        super().reset()
        if hasattr(self, "combat_strategy"):
            self.combat_strategy.reset_round()
        self._combat_frame_index = 0
        self._grid_target_id = None
        self._locked_target_id = None

    def combat_track_rejection_reason(
        self,
        track: Any,
        *,
        state: Any | None = None,
        for_acquire: bool = False,
    ) -> str | None:
        track_id = int(getattr(track, "track_id", 0) or 0)
        context = self.tracker.context_for(track_id)
        metrics = self.metrics_for(track_id)
        if metrics is None:
            return "BODY_NO_GRID_METRICS"
        frame_shape = None
        if state is not None:
            mask = getattr(state, "motion_mask", None)
            if getattr(mask, "size", 0):
                frame_shape = tuple(mask.shape[:2])
        player_center = (
            tuple(float(value) for value in state.player_center)
            if state is not None
            else (0.0, 0.0)
        )
        return combat_body_rejection_reason(
            track,
            context_state=_context_state(context),
            grid_distance=int(getattr(metrics, "grid_distance", 99)),
            player_center=player_center,
            player_box_size=(
                float(getattr(self.config, "player_box_width", 18.0) or 18.0),
                float(getattr(self.config, "player_box_height", 38.0) or 38.0),
            ),
            tile_size=float(getattr(self, "tile_size", 32.0) or 32.0),
            frame_shape=frame_shape,
            for_acquire=for_acquire,
        )

    def process(self, frame_bgr, *, timestamp=None):
        state = super().process(frame_bgr, timestamp=timestamp)
        self._combat_frame_index += 1
        player_cell = _player_cell(self, state)
        if self.combat_strategy._phase == CombatPhase.POST_COMBAT:
            tracker = getattr(self, "tracker", None)
            if tracker is not None and hasattr(tracker, "full_reset"):
                tracker.full_reset()
            frame = CombatStrategyFrame(
                frame_index=self._combat_frame_index,
                timestamp=float(state.timestamp),
                player_cell=player_cell,
                observations=(),
            )
            self._combat_last_snapshot = self.combat_strategy.update(frame)
            return replace(state, tracks=(), target_id=None)

        observations = tuple(
            _observation_for_track(self, state, track, frame_index=self._combat_frame_index)
            for track in tuple(getattr(state, "tracks", ()) or ())
        )
        self._last_strategy_observations = observations
        frame = CombatStrategyFrame(
            frame_index=self._combat_frame_index,
            timestamp=float(state.timestamp),
            player_cell=player_cell,
            observations=observations,
            attack_context=self._attack_visual_context,
        )
        snapshot = self.combat_strategy.update(frame)
        self._combat_last_snapshot = snapshot
        selected_id = snapshot.current_visual_track_id
        selected = next(
            (item for item in observations if item.track_id == selected_id and item.clean),
            None,
        )
        authoritative_id = selected.track_id if selected is not None else None
        self._grid_target_id = authoritative_id
        self._locked_target_id = authoritative_id
        return replace(state, target_id=authoritative_id)


class StrategyDecisionEngineMixin:
    def decide(
        self,
        state,
        observer,
        tracker,
        *,
        now: float,
        skills_allowed: bool = True,
    ):
        base = super().decide(
            state,
            observer,
            tracker,
            now=now,
            skills_allowed=skills_allowed,
        )
        snapshot = observer.combat_snapshot()
        direction = _direction_for_snapshot(snapshot)
        distance = _grid_distance_for_snapshot(snapshot)
        mode = str(getattr(base, "mode", "ENGAGED_SEARCH"))
        navigation = str(getattr(base, "navigation", "HOLD"))
        base_r = bool(getattr(base, "base_r", True))
        h_opportunity = bool(getattr(base, "h_opportunity", False))
        reason = str(getattr(base, "reason", ""))

        if snapshot.combat_phase == CombatPhase.POST_COMBAT.value:
            mode = "COMBAT_DISABLED"
            navigation = "HOLD"
            base_r = False
            h_opportunity = False
            reason = "KO accepted; combat inputs and target creation disabled"
        elif snapshot.target_state == "ATTENTION":
            mode = "ATTENTION"
            navigation = f"FACE_{direction}" if direction in _CARDINAL else "HOLD"
            h_opportunity = False
            reason = "attention hypothesis only; keep R, no H, no persistent identity"
        elif snapshot.active:
            if snapshot.movement_mode == "MELEE_LOCK":
                mode = "MELEE"
                navigation = f"FACE_{direction}" if direction in _CARDINAL else "HOLD"
                h_opportunity = bool(h_opportunity and snapshot.attack_authority)
            elif snapshot.movement_mode in {"MELEE_HOLD", "LOCAL_GRID_RECOVERY"}:
                mode = snapshot.movement_mode
                navigation = f"FACE_{direction}" if direction in _CARDINAL else "HOLD"
                h_opportunity = False
            elif snapshot.movement_mode == "GLOBAL_RECOVERY":
                mode = "GLOBAL_RECOVERY"
                navigation = "HOLD"
                h_opportunity = False
            elif not snapshot.movement_authority:
                navigation = "HOLD"
                h_opportunity = False
            reason += (
                f"; strategy={snapshot.strategy} scope={snapshot.perception_scope} "
                f"confirmed_cell={snapshot.confirmed_target_cell} "
                f"predicted_cell={snapshot.predicted_target_cell} "
                f"pending_cell={snapshot.pending_rebind_cell} "
                f"contamination={snapshot.contamination}"
            )

        return StrategyCombatDecision(
            mode=mode,
            navigation=navigation,
            face=direction if direction in _CARDINAL else str(getattr(base, "face", "-")),
            base_r=base_r,
            h_opportunity=h_opportunity,
            target_id=getattr(state, "target_id", None),
            grid_distance=distance,
            reason=reason,
            engagement_active=bool(getattr(base, "engagement_active", True)),
            engagement_stable_seconds=float(
                getattr(base, "engagement_stable_seconds", 0.0) or 0.0
            ),
            combat_target_id=snapshot.combat_target_id,
            visual_track_id=snapshot.current_visual_track_id,
            target_state=snapshot.target_state,
            target_confidence=snapshot.confidence,
            movement_mode=snapshot.movement_mode,
            predicted_position=snapshot.predicted_position,
            time_since_last_seen=snapshot.time_since_last_seen,
            strategy=snapshot.strategy,
            combat_phase=snapshot.combat_phase,
            perception_scope=snapshot.perception_scope,
            player_cell=snapshot.player_cell,
            confirmed_target_cell=snapshot.confirmed_target_cell,
            predicted_target_cell=snapshot.predicted_target_cell,
            pending_rebind_cell=snapshot.pending_rebind_cell,
            pending_rebind_hits=snapshot.pending_rebind_hits,
            contamination=snapshot.contamination,
            melee_visual_authority=snapshot.melee_visual_authority,
            track_creation_enabled=snapshot.track_creation_enabled,
            movement_authority=snapshot.movement_authority,
            attack_authority=snapshot.attack_authority,
        )


class StrategyControlPlannerMixin:
    _strategy_telemetry: Telemetry | None = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._strategy_next_move_at = -1e9
        self._strategy_attack_sequence = 0
        self._strategy_last_block_at = -1e9
        _REGISTRY.active_planner = self

    def reset(self) -> None:
        super().reset()
        self._strategy_next_move_at = -1e9

    def _emit_block(self, reason: str, decision: StrategyCombatDecision, now: float) -> None:
        telemetry = self._strategy_telemetry
        if telemetry is None or now - self._strategy_last_block_at < 0.50:
            return
        self._strategy_last_block_at = now
        telemetry(
            "DOJO_COMBAT_MOVE_BLOCKED",
            {
                "reason": reason,
                "strategy": decision.strategy,
                "phase": decision.combat_phase,
                "scope": decision.perception_scope,
                "combat_target_id": decision.combat_target_id,
                "visual_track_id": decision.visual_track_id,
            },
        )

    def _publish_attack_context(self, decision: StrategyCombatDecision, now: float) -> None:
        observer = _REGISTRY.active_observer
        if observer is None:
            return
        direction = str(decision.face).upper()
        delta = {
            "LEFT": (-1, 0),
            "RIGHT": (1, 0),
            "UP": (0, -1),
            "DOWN": (0, 1),
        }.get(direction)
        if delta is None:
            return
        self._strategy_attack_sequence += 1
        origin = decision.player_cell
        expected = frozenset(
            {
                (origin[0] + delta[0], origin[1] + delta[1]),
                (origin[0] + 2 * delta[0], origin[1] + 2 * delta[1]),
            }
        )
        observer.set_attack_visual_context(
            AttackVisualContext(
                attack_id=self._strategy_attack_sequence,
                started_at=now,
                origin_cell=origin,
                direction=direction,
                expected_cells=expected,
                expires_at=now + 0.85,
            )
        )

    def plan(
        self,
        decision,
        *,
        now: float,
        movement_allowed: bool = True,
        block_reason: str = "",
    ):
        now = float(now)
        proxy = decision
        if getattr(decision, "combat_target_id", None) is not None:
            proxy = replace(decision, target_id=int(decision.combat_target_id))
        command = super().plan(
            proxy,
            now=now,
            movement_allowed=movement_allowed,
            block_reason=block_reason,
        )
        expected_key = _DIRECTION_KEYS.get(str(getattr(decision, "face", "-")).upper())
        deny_move = None
        if command.move_pulse is not None:
            if decision.combat_phase == CombatPhase.POST_COMBAT.value:
                deny_move = "POST_COMBAT"
            elif not decision.movement_authority or decision.visual_track_id is None:
                deny_move = "NO_CLEAN_VISUAL_AUTHORITY"
            elif decision.movement_mode != "PURSUIT":
                deny_move = "NOT_PURSUIT"
            elif expected_key is None or command.move_pulse != expected_key:
                deny_move = "DIRECTION_MISMATCH"
            elif now < self._strategy_next_move_at:
                deny_move = "MANDATORY_REOBSERVATION"
            if deny_move is not None:
                command = replace(
                    command,
                    move_pulse=None,
                    safety_state=deny_move,
                    reason=str(command.reason) + f"; {deny_move.lower()}",
                )
                self._emit_block(deny_move, decision, now)
            else:
                self._strategy_next_move_at = now + 0.75
                command = replace(
                    command,
                    safety_state="ONE_STEP_PURSUIT",
                    reason=str(command.reason) + "; one pulse then reobserve",
                )

        if command.face_pulse is not None and (
            expected_key is None or command.face_pulse != expected_key
        ):
            command = replace(
                command,
                face_pulse=None,
                h_fire=False,
                safety_state="FACE_DIRECTION_MISMATCH",
                reason=str(command.reason) + "; face direction mismatch blocked",
            )

        if command.h_fire and not decision.attack_authority:
            command = replace(
                command,
                h_fire=False,
                h_shadow_ready=False,
                safety_state="H_NO_CLEAN_MELEE_AUTHORITY",
                reason=str(command.reason) + "; H requires current clean adjacent body",
            )
        elif command.h_fire:
            self._publish_attack_context(decision, now)

        if decision.combat_phase == CombatPhase.POST_COMBAT.value:
            command = replace(
                command,
                held_keys=(),
                move_pulse=None,
                face_pulse=None,
                h_fire=False,
                h_shadow_ready=False,
                safety_state="COMBAT_DISABLED",
            )

        logical_id = getattr(decision, "combat_target_id", None)
        if logical_id is not None:
            parts: list[str] = []
            if command.held_keys:
                parts.append("+".join(command.held_keys))
            if command.move_pulse:
                parts.append(f"MOVE:{command.move_pulse}")
            if command.face_pulse:
                parts.append(f"FACE:{command.face_pulse}")
            if command.h_fire:
                parts.append("H")
            _CURRENT_COMMANDS[int(logical_id)] = ",".join(parts) or "HOLD"
        return command


class StrategyVictoryWatcherMixin:
    def poll(self):
        signal = super().poll()
        if signal is not None:
            _REGISTRY.end_combat()
        return signal


def install_combat_strategy_runtime(
    runtime: Any,
    *,
    strategy_name: str | None = None,
) -> InstalledCombatRuntime:
    """Install one explicit combat strategy factory over the validated v03 chain.

    This is the only canonical combat installation point. Historical classes remain
    available as bases/fallback compatibility, but the round entrypoint no longer
    stacks the old persistent bridge and a second hardening bridge.
    """

    import kage_pilot_live_v03 as live_runtime

    existing = getattr(live_runtime, "_kagelink_combat_strategy_runtime", None)
    if isinstance(existing, InstalledCombatRuntime):
        return existing

    settings = load_combat_strategy_config()
    if strategy_name is not None:
        payload = {
            key: getattr(settings, key)
            for key in settings.__dataclass_fields__
        }
        payload["strategy"] = strategy_name
        settings = CombatStrategyConfig.from_mapping(payload)
    telemetry: Telemetry | None = getattr(runtime, "_telemetry", None)
    legacy_config = load_combat_target_config()

    BaseTracker = live_runtime.PersistentBackgroundWaterAwareEntityTracker
    BaseObserver = live_runtime.ParticleSafeGridTargetObserver
    BaseEngine = live_runtime.ShadowCombatDecisionEngine
    BasePlanner = live_runtime.LiveCombatControlPlanner
    BaseWatcher = live_runtime.ChatVictoryWatcher

    CanonicalCombatTracker = type(
        "CanonicalCombatTracker",
        (StrategyFilteredTrackerMixin, BaseTracker),
        {
            "__module__": __name__,
            "_strategy_telemetry": telemetry,
            "_legacy_combat_config": legacy_config,
        },
    )
    CanonicalCombatObserver = type(
        "CanonicalCombatObserver",
        (StrategyObserverMixin, BaseObserver),
        {
            "__module__": __name__,
            "_strategy_config": settings,
            "_strategy_telemetry": telemetry,
        },
    )
    CanonicalCombatDecisionEngine = type(
        "CanonicalCombatDecisionEngine",
        (StrategyDecisionEngineMixin, BaseEngine),
        {"__module__": __name__},
    )
    CanonicalCombatPlanner = type(
        "CanonicalCombatPlanner",
        (StrategyControlPlannerMixin, BasePlanner),
        {"__module__": __name__, "_strategy_telemetry": telemetry},
    )
    CanonicalCombatVictoryWatcher = type(
        "CanonicalCombatVictoryWatcher",
        (StrategyVictoryWatcherMixin, BaseWatcher),
        {"__module__": __name__},
    )

    live_runtime.PersistentBackgroundWaterAwareEntityTracker = CanonicalCombatTracker
    live_runtime.ParticleSafeGridTargetObserver = CanonicalCombatObserver
    live_runtime.ShadowCombatDecisionEngine = CanonicalCombatDecisionEngine
    live_runtime.LiveCombatControlPlanner = CanonicalCombatPlanner
    live_runtime.ChatVictoryWatcher = CanonicalCombatVictoryWatcher

    for name, value in (
        ("PersistentBackgroundWaterAwareEntityTracker", CanonicalCombatTracker),
        ("ParticleSafeGridTargetObserver", CanonicalCombatObserver),
        ("ShadowCombatDecisionEngine", CanonicalCombatDecisionEngine),
        ("LiveCombatControlPlanner", CanonicalCombatPlanner),
        ("ChatVictoryWatcher", CanonicalCombatVictoryWatcher),
    ):
        if hasattr(runtime, name):
            setattr(runtime, name, value)

    installed = InstalledCombatRuntime(
        strategy_name=settings.strategy,
        config=settings,
        config_path=combat_strategy_config_path(),
        tracker_class=CanonicalCombatTracker,
        observer_class=CanonicalCombatObserver,
        engine_class=CanonicalCombatDecisionEngine,
        planner_class=CanonicalCombatPlanner,
        watcher_class=CanonicalCombatVictoryWatcher,
    )
    _REGISTRY.installed = installed
    live_runtime._kagelink_combat_strategy_runtime = installed
    live_runtime._kagelink_combat_strategy_installed = True
    if telemetry is not None:
        telemetry(
            "DOJO_COMBAT_STRATEGY_INSTALLED",
            {
                "strategy": settings.strategy,
                "factory": "canonical-single-install",
                "legacy_safe_available": "true",
                "persistent_hardened_available": "true",
                "grid_focus_v2_available": "true",
            },
        )
    return installed


def runtime_provenance(runtime: Any) -> dict[str, object]:
    import kage_pilot_live_v03 as live_runtime

    installed = _REGISTRY.installed
    settings = installed.config if installed is not None else load_combat_strategy_config()
    legacy = load_combat_target_config()
    observer_class = live_runtime.ParticleSafeGridTargetObserver
    tracker_class = live_runtime.PersistentBackgroundWaterAwareEntityTracker
    engine_class = live_runtime.ShadowCombatDecisionEngine
    planner_class = live_runtime.LiveCombatControlPlanner
    strategy = create_combat_target_strategy(config=settings)
    return {
        "observer_class": observer_class.__qualname__,
        "observer_module": observer_class.__module__,
        "tracker_class": _class_name(tracker_class),
        "memory_class": _class_name(strategy),
        "engine_class": _class_name(engine_class),
        "planner_class": _class_name(planner_class),
        "strategy": settings.strategy,
        "config_path": str(combat_strategy_config_path()),
        "contact_radius": legacy.contact_radius,
        "local_rebind_radius": legacy.local_rebind_radius,
        "contact_hold_seconds": legacy.contact_hold_seconds,
        "local_rebind_seconds": legacy.local_rebind_seconds,
        "hard_lost_timeout": settings.hard_lost_timeout,
        "minimum_rebind_score": settings.minimum_rebind_score,
    }


def emit_runtime_provenance(runtime: Any) -> dict[str, object]:
    fields = runtime_provenance(runtime)
    if _REGISTRY.provenance_emitted:
        return fields
    _REGISTRY.provenance_emitted = True
    telemetry = getattr(runtime, "_telemetry", None)
    if telemetry is not None:
        telemetry("DOJO_COMBAT_RUNTIME_PROVENANCE", fields)
    else:
        print("DOJO_COMBAT_RUNTIME_PROVENANCE " + json.dumps(fields, sort_keys=True))
    return fields


__all__ = [
    "InstalledCombatRuntime",
    "StrategyCombatDecision",
    "current_runtime_command",
    "emit_runtime_provenance",
    "install_combat_strategy_runtime",
    "runtime_provenance",
]
