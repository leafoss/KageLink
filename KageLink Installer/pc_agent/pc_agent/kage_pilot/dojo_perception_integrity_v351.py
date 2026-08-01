from __future__ import annotations

"""Physical perception integrity guards for the Kage Pilot 3.5.1 combat runtime.

The compatibility runtime still exposes motion contours and historical map-resync
heuristics. This module establishes three hard boundaries before the canonical
combat strategy is instantiated:

* the RAW 32/64 grid selected for the isolated round is immutable;
* a motion contour must pass a body gate before it may create a visual track;
* capture stalls and dense combat effects block controls without deleting identity.

The module is installed only by the isolated round entrypoint. It does not send
keyboard or mouse input and it does not promote ``grid_focus_v2`` automatically.
"""

from dataclasses import dataclass
import math
import time
from typing import Any, Callable

from .combat_target_filter_v351 import (
    candidate_bbox,
    combat_body_rejection_reason,
)
from .combat_target_model_v351 import RejectedCandidate
from .grid_geometry_v351 import (
    GridGeometry,
    current_grid_geometry,
    emit_grid_geometry,
)


Telemetry = Callable[[str, dict[str, object]], None]


@dataclass(slots=True)
class PerceptionStallLatch:
    active_until: float = -1e9
    reason: str = ""
    generation: int = 0

    def mark(self, reason: str, *, now: float, hold_seconds: float = 0.75) -> None:
        value = float(now)
        if value >= self.active_until:
            self.generation += 1
        self.reason = str(reason)
        self.active_until = max(
            self.active_until,
            value + max(0.35, min(2.0, float(hold_seconds))),
        )

    def active(self, *, now: float) -> bool:
        return float(now) < self.active_until


_STALL = PerceptionStallLatch()


def _candidate_center(candidate: Any) -> tuple[float, float]:
    value = getattr(candidate, "center", None)
    try:
        if value is not None and len(value) == 2:
            return float(value[0]), float(value[1])
    except Exception:
        pass
    x, y, width, height = candidate_bbox(candidate)
    return x + width * 0.50, y + height * 0.50


def _tracker_tile_size(tracker: Any) -> float:
    geometry = current_grid_geometry()
    if geometry is not None:
        return float(geometry.cell_size)

    config = getattr(tracker, "config", None)
    player_height = float(getattr(config, "player_box_height", 38.0) or 38.0)
    return 64.0 if player_height >= 57.0 else 32.0


def motion_candidate_body_rejection_reason(
    candidate: Any,
    *,
    player_center: tuple[float, float],
    tile_size: float,
    player_box_size: tuple[float, float],
    frame_shape: tuple[int, int] | None,
) -> str | None:
    """Reject motion-only scenery before it can become an EntityTrack."""

    center = _candidate_center(candidate)
    tile = max(16.0, float(tile_size))
    grid_distance = int(
        round(
            max(
                abs(center[0] - float(player_center[0])),
                abs(center[1] - float(player_center[1])),
            )
            / tile
        )
    )
    return combat_body_rejection_reason(
        candidate,
        context_state="VISIBLE",
        grid_distance=grid_distance,
        player_center=player_center,
        player_box_size=player_box_size,
        tile_size=tile,
        frame_shape=frame_shape,
        for_acquire=True,
    )


def _existing_contact_owner(
    tracker: Any,
    candidate: Any,
    *,
    tile_size: float,
) -> bool:
    """Allow a merged PLAYER+enemy contour only for an established nearby track."""

    center = _candidate_center(candidate)
    tracks = tuple(getattr(tracker, "_tracks", {}).values())
    base_gate = float(
        getattr(getattr(tracker, "config", None), "track_match_distance", 90.0)
        or 90.0
    )
    gate = base_gate + max(18.0, float(tile_size) * 0.65)
    for track in tracks:
        if int(getattr(track, "observations", 0) or 0) < 2:
            continue
        track_center = _candidate_center(track)
        if math.dist(center, track_center) <= gate:
            return True
    return False


def install_motion_body_gate(*, telemetry: Telemetry | None = None) -> None:
    """Filter floor/effect motion before the historical tracker allocates IDs."""

    from .combat_strategy_runtime_v351 import StrategyFilteredTrackerMixin

    tracker_mixin = StrategyFilteredTrackerMixin
    original_update = tracker_mixin.update
    if bool(getattr(original_update, "_kagelink_motion_body_gate", False)):
        return

    def body_guarded_update(self, candidates, *, flow, player_center, now):
        raw = list(candidates)
        gray = getattr(self, "_frame_gray", None)
        frame_shape = tuple(gray.shape[:2]) if getattr(gray, "size", 0) else None
        tile_size = _tracker_tile_size(self)
        config = getattr(self, "config", None)
        player_box_size = (
            float(getattr(config, "player_box_width", 18.0) or 18.0),
            float(getattr(config, "player_box_height", 38.0) or 38.0),
        )

        accepted: list[Any] = []
        rejected: list[RejectedCandidate] = []
        for candidate in raw:
            reason = motion_candidate_body_rejection_reason(
                candidate,
                player_center=player_center,
                tile_size=tile_size,
                player_box_size=player_box_size,
                frame_shape=frame_shape,
            )
            contact_rebind = (
                reason in {"BODY_PLAYER_OVERLAP", "BODY_SELF_CELL"}
                and _existing_contact_owner(self, candidate, tile_size=tile_size)
            )
            if reason is None or contact_rebind:
                accepted.append(candidate)
            else:
                rejected.append(RejectedCandidate(candidate_bbox(candidate), reason))

        result = original_update(
            self,
            accepted,
            flow=flow,
            player_center=player_center,
            now=now,
        )
        downstream = tuple(getattr(self, "rejected_candidates", ()) or ())
        self.raw_candidate_count = len(raw)
        self.rejected_candidates = tuple(rejected) + downstream

        if rejected and telemetry is not None:
            last_at = float(getattr(self, "_kagelink_body_gate_telemetry_at", -1e9))
            signature = tuple(
                (item.reason, item.bbox)
                for item in self.rejected_candidates[:12]
            )
            previous = getattr(self, "_kagelink_body_gate_signature", ())
            if signature != previous or float(now) - last_at >= 0.75:
                self._kagelink_body_gate_signature = signature
                self._kagelink_body_gate_telemetry_at = float(now)
                telemetry(
                    "DOJO_MOTION_BODY_GATE_REJECTED",
                    {
                        "count": len(rejected),
                        "raw_candidates": len(raw),
                        "accepted_candidates": len(accepted),
                        "reasons": ",".join(
                            sorted({item.reason for item in rejected})
                        ),
                        "cell_size": f"{tile_size:.0f}",
                    },
                )
        return result

    body_guarded_update._kagelink_motion_body_gate = True
    tracker_mixin.update = body_guarded_update


def install_round_geometry_lock(runtime: Any) -> None:
    """Keep the CLI/round RAW grid immutable even if a later template match conflicts."""

    from .dojo_resolution_bridge_v351 import apply_tracker_geometry, read_dojo_geometry

    engine_class = runtime.ClosedLoopVisualRecoveryEngine
    original_sync = engine_class._sync_cell_mode
    if bool(getattr(original_sync, "_kagelink_round_geometry_lock", False)):
        return

    telemetry = getattr(runtime, "_telemetry", None)

    def locked_sync_cell_mode(self) -> str:
        locked = getattr(self, "_kagelink_locked_grid_mode", None)
        if locked not in {"32", "64"}:
            position_cell = float(
                getattr(getattr(self, "position", None), "cell_size", 0.0) or 0.0
            )
            geometry = read_dojo_geometry()
            if position_cell in {32.0, 64.0}:
                locked = str(int(position_cell))
                source = "round_cli"
            elif geometry is not None:
                locked = geometry.template_mode
                source = "precombat_geometry"
            else:
                value = str(original_sync(self))
                if value not in {"32", "64"}:
                    raise RuntimeError("DOJO_ROUND_GRID_MODE_UNAVAILABLE")
                locked = value
                source = "runtime_fallback"
            self._kagelink_locked_grid_mode = locked
            self._kagelink_locked_grid_cell_size = float(locked)
            emit_grid_geometry(
                GridGeometry.from_mode(locked),
                telemetry=telemetry,
            )
            if callable(telemetry):
                telemetry(
                    "DOJO_ROUND_GRID_LOCKED",
                    {
                        "mode": locked,
                        "cell_size": locked,
                        "source": source,
                    },
                )

        cell_size = float(locked)
        position = getattr(self, "position", None)
        if position is not None and abs(
            float(getattr(position, "cell_size", cell_size) or cell_size) - cell_size
        ) > 0.05:
            apply_tracker_geometry(position, cell_size)

        detector = getattr(self, "leader_detector", None)
        detected = str(
            getattr(detector, "last_accepted_template_mode", "") or ""
        )
        conflict_signature = (locked, detected)
        if (
            detected in {"32", "64"}
            and detected != locked
            and conflict_signature
            != getattr(self, "_kagelink_grid_conflict_signature", None)
        ):
            self._kagelink_grid_conflict_signature = conflict_signature
            if callable(telemetry):
                telemetry(
                    "DOJO_GRID_MODE_CONFLICT",
                    {
                        "expected_mode": locked,
                        "detected_mode": detected,
                        "action": "IGNORED",
                        "authority": "round_cli",
                    },
                )
        return str(locked)

    locked_sync_cell_mode._kagelink_round_geometry_lock = True
    engine_class._sync_cell_mode = locked_sync_cell_mode


def install_nondestructive_perception_stall(
    runtime: Any,
    *,
    telemetry: Telemetry | None = None,
) -> None:
    """Convert frame gaps and dense effects into holds, never identity deletion."""

    import kage_pilot_live_v03i_round as historical

    emit = telemetry or getattr(runtime, "_telemetry", None)

    observer_class = historical.MapSaveResyncObserver
    if not bool(getattr(observer_class, "_kagelink_nondestructive_stall", False)):
        parent_process = historical._PREVIOUS_OBSERVER.process

        def process_without_destructive_resync(self, frame_bgr, *, timestamp=None):
            now = time.monotonic()
            previous = getattr(self, "_last_process_wall", None)
            if previous is not None:
                gap = now - float(previous)
                threshold = float(getattr(self, "frame_gap_seconds", 1.25) or 1.25)
                if gap >= threshold:
                    _STALL.mark(
                        f"frame_gap={gap:.2f}s",
                        now=now,
                        hold_seconds=min(1.5, max(0.55, gap * 0.35)),
                    )
                    if callable(emit):
                        emit(
                            "DOJO_PERCEPTION_STALL",
                            {
                                "reason": f"frame_gap={gap:.2f}s",
                                "action": "HOLD_PRESERVE_IDENTITY",
                                "tracker_reset": False,
                            },
                        )
            self._last_process_wall = now
            # Preserve support for an explicit external resync generation, but this
            # method no longer creates one from a slow frame.
            self._apply_resync_if_needed()
            return parent_process(self, frame_bgr, timestamp=timestamp)

        observer_class.process = process_without_destructive_resync
        observer_class._kagelink_nondestructive_stall = True

    guard_class = historical.MapSaveResyncMotionBurstGuard
    if not bool(getattr(guard_class, "_kagelink_nondestructive_stall", False)):
        parent_update = historical._PREVIOUS_GUARD.update

        def update_without_scene_reset(self, *, active_cells: int, entities: int, now: float):
            value = float(now)
            if _STALL.active(now=value):
                return historical.MotionBurstState(
                    blocked=True,
                    reason=f"perception_stall:{_STALL.reason}",
                    active_cells=max(0, int(active_cells)),
                    entities=max(0, int(entities)),
                    baseline_active_cells=float(
                        getattr(self, "_baseline_active", 1.0) or 1.0
                    ),
                    baseline_entities=float(
                        getattr(self, "_baseline_entities", 1.0) or 1.0
                    ),
                )

            # The previous guard may block a particle burst, but it cannot turn
            # active-cell density into MAP_SAVE_RESYNC or clear target memory.
            state = parent_update(
                self,
                active_cells=active_cells,
                entities=entities,
                now=value,
            )
            if (
                bool(getattr(state, "blocked", False))
                and "active_cells_spike" in str(getattr(state, "reason", ""))
            ):
                if callable(emit):
                    last_at = float(
                        getattr(self, "_kagelink_dense_effect_telemetry_at", -1e9)
                    )
                    if value - last_at >= 0.75:
                        self._kagelink_dense_effect_telemetry_at = value
                        emit(
                            "DOJO_DENSE_COMBAT_EFFECT_HOLD",
                            {
                                "active_cells": int(active_cells),
                                "entities": int(entities),
                                "action": "HOLD_PRESERVE_IDENTITY",
                                "tracker_reset": False,
                            },
                        )
            return state

        guard_class.update = update_without_scene_reset
        guard_class._kagelink_nondestructive_stall = True


def install_perception_integrity(runtime: Any) -> None:
    telemetry = getattr(runtime, "_telemetry", None)
    install_motion_body_gate(telemetry=telemetry)
    install_nondestructive_perception_stall(runtime, telemetry=telemetry)


__all__ = [
    "PerceptionStallLatch",
    "install_motion_body_gate",
    "install_nondestructive_perception_stall",
    "install_perception_integrity",
    "install_round_geometry_lock",
    "motion_candidate_body_rejection_reason",
]
