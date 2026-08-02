from __future__ import annotations

import json
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, is_dataclass, replace
from types import SimpleNamespace
from typing import Any, Iterable

from .domain import GridCell
from .hostility_gate import EntityState, HostilityState
from .occupancy_model import DiffSource, PR26ControlMode


_TRACKING_INSTALLED = False
_PHYSICAL_INSTALLED = False
_EVENT_RECORDER_INSTALLED = False

_CAMERA_MIN_RESPONSE = 0.16
_CAMERA_DIRECT_RESPONSE = 0.22
_CAMERA_SMALL_SHIFT_PX = 4.0
_CAMERA_PENDING_TOLERANCE_PX = 3.0
_CAMERA_MAX_LOW_CONFIDENCE_SHIFT_PX = 8.0
_CAMERA_MAX_MEDIUM_CONFIDENCE_SHIFT_PX = 64.0
_ORIENTATION_HINT_MAX_AGE_SECONDS = 1.50
_ORIENTATION_REPEAT_SECONDS = 0.90


@dataclass(slots=True)
class CameraStabilityGate:
    """Require temporal agreement before moving the frozen world baseline.

    Small high-confidence corrections can be accepted immediately. A meaningful
    camera translation must be observed consistently before it becomes
    authoritative. Low-response jumps keep the previous accepted translation
    and block all visual authority for that frame.
    """

    accepted: tuple[float, float] = (0.0, 0.0)
    pending: tuple[float, float] | None = None
    pending_votes: int = 0
    initialized: bool = False
    reason: str = "UNINITIALIZED"

    def evaluate(
        self,
        dx: float,
        dy: float,
        response: float,
        raw_authoritative: bool,
    ) -> tuple[float, float, float, bool]:
        candidate = (float(round(dx)), float(round(dy)))
        response = float(response)

        if not raw_authoritative or response < _CAMERA_MIN_RESPONSE:
            self.pending = None
            self.pending_votes = 0
            self.reason = "LOW_RESPONSE_OR_RAW_REJECT"
            return self.accepted[0], self.accepted[1], response, False

        delta = math.dist(self.accepted, candidate)
        if delta <= _CAMERA_SMALL_SHIFT_PX and response >= _CAMERA_MIN_RESPONSE:
            self.accepted = candidate
            self.pending = None
            self.pending_votes = 0
            self.initialized = True
            self.reason = "SMALL_STABLE_CORRECTION"
            return candidate[0], candidate[1], response, True

        if response < _CAMERA_DIRECT_RESPONSE and delta > _CAMERA_MAX_LOW_CONFIDENCE_SHIFT_PX:
            self.pending = None
            self.pending_votes = 0
            self.reason = "LOW_CONFIDENCE_ACCELERATION"
            return self.accepted[0], self.accepted[1], response, False

        if (
            delta > _CAMERA_MAX_MEDIUM_CONFIDENCE_SHIFT_PX
            and response < 0.45
        ):
            self.pending = None
            self.pending_votes = 0
            self.reason = "IMPLAUSIBLE_SINGLE_FRAME_SHIFT"
            return self.accepted[0], self.accepted[1], response, False

        if self.pending is not None and math.dist(self.pending, candidate) <= _CAMERA_PENDING_TOLERANCE_PX:
            self.pending_votes += 1
            self.pending = (
                float(round((self.pending[0] + candidate[0]) / 2.0)),
                float(round((self.pending[1] + candidate[1]) / 2.0)),
            )
        else:
            self.pending = candidate
            self.pending_votes = 1

        required = 2 if response >= 0.28 else 3
        if self.pending_votes < required:
            self.reason = f"PENDING_TEMPORAL_CONFIRMATION_{self.pending_votes}_OF_{required}"
            return self.accepted[0], self.accepted[1], response, False

        self.accepted = self.pending
        self.pending = None
        self.pending_votes = 0
        self.initialized = True
        self.reason = "TEMPORALLY_CONFIRMED_TRANSLATION"
        return self.accepted[0], self.accepted[1], response, True


def rawless_orientation_geometry(
    *,
    bbox: tuple[int, int, int, int],
    changed_ratio: float,
    largest_blob_area: int,
    cell_count: int,
) -> bool:
    """Strict raw-less geometry allowed to suggest a turn, never a target.

    A whole or nearly whole 64px cell is scenery/camera evidence, not a
    humanoid. Raw-less orientation is restricted to one compact vertical
    component. A raw/Target-Capsule body uses the separate same-cell binding
    path and is not constrained by this helper.
    """

    _, _, width, height = (int(value) for value in bbox)
    area = width * height
    ratio = float(changed_ratio)
    blob = int(largest_blob_area)
    return bool(
        int(cell_count) == 1
        and 8 <= width <= 48
        and 28 <= height <= 78
        and height >= width * 1.20
        and area <= 2200
        and 0.035 <= ratio <= 0.35
        and 90 <= blob <= 1800
    )


def has_latched_hostile_memory(gate: Any | None) -> bool:
    if gate is None:
        return False
    memory = getattr(gate, "_pr26_round_target_memory", None)
    if memory is None or getattr(memory, "last_raw_track_id", None) is None:
        return False
    track = getattr(memory, "track", None)
    return bool(
        track is not None
        and getattr(track, "entity_state", None) is EntityState.ENTITY_CONFIRMED
        and getattr(track, "hostility_state", None) is HostilityState.HOSTILE_CONFIRMED
    )


def _copy_decision(decision: Any, **updates: Any) -> Any:
    allowed = {
        name: value
        for name, value in updates.items()
        if hasattr(decision, name)
    }
    if is_dataclass(decision):
        return replace(decision, **allowed)
    values = dict(vars(decision)) if hasattr(decision, "__dict__") else {}
    values.update(allowed)
    return SimpleNamespace(**values)


def _strict_near_body(cluster: Any, player_cell: GridCell) -> bool:
    from .runtime_near_enemy_focus import within_player_search_radius

    if not within_player_search_radius(cluster, player_cell):
        return False
    exact = any(
        getattr(item, "diff_source", None) is DiffSource.EXACT_CELL_BASELINE
        or bool(getattr(item, "reference_authoritative", False))
        for item in cluster.cell_observations
    )
    return bool(
        exact
        and rawless_orientation_geometry(
            bbox=cluster.bbox,
            changed_ratio=float(cluster.true_changed_ratio),
            largest_blob_area=int(cluster.largest_blob_area),
            cell_count=len(cluster.cells),
        )
        and float(cluster.occupancy_score) >= 0.50
    )


def install_target_integrity_tracking() -> None:
    """Install PR26.14 logical-target, camera and geometry invariants."""

    global _TRACKING_INSTALLED
    if _TRACKING_INSTALLED:
        return

    from . import runtime_camera_compensation as camera_module
    from . import runtime_near_enemy_focus as near_module
    from . import strategy as strategy_module
    from .occupancy_tracking import PR26OccupancyTracker

    raw_camera_estimate = camera_module.estimate_camera_translation
    camera_gate = CameraStabilityGate()
    last_camera_event: list[tuple[str, float, float] | None] = [None]

    def stable_camera_estimate(*args: Any, **kwargs: Any):
        dx, dy, response, raw_authoritative = raw_camera_estimate(*args, **kwargs)
        accepted_dx, accepted_dy, response, authoritative = camera_gate.evaluate(
            dx,
            dy,
            response,
            raw_authoritative,
        )
        event_key = (
            camera_gate.reason,
            round(float(accepted_dx), 1),
            round(float(accepted_dy), 1),
        )
        if event_key != last_camera_event[0]:
            last_camera_event[0] = event_key
            print(
                "PR26_CAMERA_STABILITY "
                f"raw=({float(dx):.1f},{float(dy):.1f}) "
                f"accepted=({accepted_dx:.1f},{accepted_dy:.1f}) "
                f"response={response:.3f} authoritative={authoritative} "
                f"reason={camera_gate.reason}"
            )
        return accepted_dx, accepted_dy, response, authoritative

    camera_module.estimate_camera_translation = stable_camera_estimate
    near_module.near_vertical_body_evidence = _strict_near_body

    original_update = PR26OccupancyTracker._update_track

    def integrity_update(self, track, component, now, player_center, player_cell):
        original_update(self, track, component, now, player_center, player_cell)
        body_bound = getattr(self, "_pr26_body_bound_tracks", None)
        if body_bound is None:
            body_bound = {}
            self._pr26_body_bound_tracks = body_bound

        raw_supported = bool(component.raw_track_ids)
        if raw_supported:
            body_bound[track.track_id] = float(now)
            return

        recent_body = float(now) - float(body_bound.get(track.track_id, -1e9)) <= 1.50
        compact_hint = rawless_orientation_geometry(
            bbox=component.bbox,
            changed_ratio=float(component.true_changed_ratio),
            largest_blob_area=int(component.largest_blob_area),
            cell_count=len(component.cells),
        )
        if compact_hint or recent_body:
            # Raw-less geometry may keep attention, but contact/hostile authority
            # still requires the same-cell body binding performed by PR26.13.
            track.combat_lock = False
            if track.hostility_state is HostilityState.HOSTILE_CONFIRMED:
                track.hostility_state = HostilityState.OBSERVE_HOSTILITY
            return

        if track.entity_votes:
            track.entity_votes[-1] = False
        meta = getattr(self, "_pr26_hardening_meta", {}).get(track.track_id)
        if meta is not None:
            if getattr(meta, "entity_votes", None):
                meta.entity_votes[-1] = False
            if getattr(meta, "motion_votes", None):
                meta.motion_votes[-1] = False
        near_votes = getattr(self, "_pr26_near_body_votes", {}).get(track.track_id)
        if near_votes:
            near_votes[-1] = False
        contact_votes = getattr(self, "_pr26_visual_contact_votes", {}).get(track.track_id)
        if contact_votes:
            contact_votes[-1] = False

        memory = getattr(self, "_pr26_round_target_memory", None)
        if memory is None or memory.track_id != track.track_id:
            track.entity_state = EntityState.DANGER_CANDIDATE
            track.attention_lock = False
            track.face_only_lock = False
            track.combat_lock = False
            if track.hostility_state is HostilityState.HOSTILE_CONFIRMED:
                track.hostility_state = HostilityState.OBSERVE_HOSTILITY
            track.reason = (
                "raw-less cell-wide/non-humanoid change rejected; no orientation or combat authority"
            )

    PR26OccupancyTracker._update_track = integrity_update

    original_active = PR26OccupancyTracker._active

    def hostile_latch_active(self):
        selected = original_active(self)
        memory = getattr(self, "_pr26_round_target_memory", None)
        if memory is not None and getattr(memory, "last_raw_track_id", None) is None:
            bad_track = self._tracks.get(memory.track_id)
            if bad_track is not None:
                bad_track.combat_lock = False
                bad_track.hostility_state = HostilityState.OBSERVE_HOSTILITY
            self._pr26_round_target_memory = None
            self.map._pr26_contact_mask_enabled = False
            self._pr26_continuity_authority = "NONE"
            self._emit(
                f"PR26_INVALID_LATCH_REJECTED id={memory.track_id} "
                "reason=NO_SAME_CELL_BODY_ID"
            )
            if selected is not None and selected.track_id == memory.track_id:
                selected.combat_lock = False

        if (
            selected is not None
            and getattr(self, "_pr26_round_target_memory", None) is None
            and selected.combat_lock
            and not selected.raw_track_ids
        ):
            selected.combat_lock = False
            selected.hostility_state = HostilityState.OBSERVE_HOSTILITY
            selected.reason = "COMBAT_LOCK rejected: no same-cell body binding"
        return selected

    PR26OccupancyTracker._active = hostile_latch_active

    original_filter = PR26OccupancyTracker.filter_candidates

    def combat_only_filter(self, *args: Any, **kwargs: Any):
        result = tuple(original_filter(self, *args, **kwargs))
        if self.mode is not PR26ControlMode.FULL_COMBAT:
            return result

        self._pr26_orientation_hint = None
        selected_id = getattr(self, "_pr26_selected_track_id", None)
        selected = self._tracks.get(selected_id) if selected_id is not None else None
        state = kwargs.get("state")
        timestamp = float(kwargs.get("now", time.monotonic()))
        camera_ok = bool(getattr(self.map, "camera_alignment_authoritative", False))

        if has_latched_hostile_memory(self):
            memory = self._pr26_round_target_memory
            track = self._tracks.get(memory.track_id, memory.track)
            if track.visible and track.combat_lock and result:
                return result
            return ()

        # No hostile latch: candidates are forbidden from entering GridFocusStrategy.
        # A compact body may only provide a separate physical orientation hint.
        if (
            selected is not None
            and state is not None
            and camera_ok
            and selected.visible
            and selected.face_only_lock
            and not selected.combat_lock
            and selected.entity_state is EntityState.ENTITY_CONFIRMED
        ):
            raw_supported = bool(selected.raw_track_ids)
            compact_rawless = rawless_orientation_geometry(
                bbox=selected.bbox,
                changed_ratio=float(selected.true_changed_ratio),
                largest_blob_area=int(selected.largest_blob_area),
                cell_count=len(selected.cells),
            )
            if raw_supported or compact_rawless:
                player = (
                    float(state.player_center[0]),
                    float(state.player_center[1]),
                )
                direction = self._face(player, selected.foot_point)
                if direction is not None:
                    self._pr26_orientation_hint = SimpleNamespace(
                        track_id=selected.track_id,
                        direction=direction,
                        timestamp=timestamp,
                        raw_supported=raw_supported,
                        cells=frozenset(selected.cells),
                    )
                    marker = (selected.track_id, direction, raw_supported)
                    if getattr(self, "_pr26_last_integrity_hint", None) != marker:
                        self._pr26_last_integrity_hint = marker
                        self._emit(
                            f"PR26_ORIENTATION_HINT id={selected.track_id} "
                            f"direction={direction} raw_supported={raw_supported} "
                            "logical_target=BLOCKED combat_candidate=BLOCKED"
                        )
        return ()

    PR26OccupancyTracker.filter_candidates = combat_only_filter

    CurrentStrategy = strategy_module.GridFocusStrategy

    class HostileLatchOnlyStrategy(CurrentStrategy):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._pr26_last_false_reset_frame: int | None = None

        def update(self, frame):
            from .runtime_tile_perception import current_hostility_gate

            gate = current_hostility_gate()
            latched = has_latched_hostile_memory(gate)
            if self.logical_target_id is not None and not latched:
                if self._pr26_last_false_reset_frame != frame.frame_index:
                    print(
                        "PR26_FALSE_LOGICAL_TARGET_RESET "
                        f"logical={self.logical_target_id} frame={frame.frame_index} "
                        "reason=NO_HOSTILE_ROUND_LATCH"
                    )
                    self._pr26_last_false_reset_frame = frame.frame_index
                self.reset_round()

            if not latched and frame.candidates:
                frame = replace(frame, candidates=())
            decision = super().update(frame)
            if not latched and decision.combat_target_id is not None:
                self.reset_round()
                empty = replace(frame, candidates=())
                decision = super().update(empty)
            return decision

    strategy_module.GridFocusStrategy = HostileLatchOnlyStrategy

    _TRACKING_INSTALLED = True
    print(
        "PR26.14 TARGET INTEGRITY: camera shifts require temporal confirmation; "
        "TURN_ONLY is a separate orientation hint; GridFocusStrategy receives candidates "
        "only after a raw body-bound hostile round latch"
    )


def install_target_integrity_physical_gate() -> None:
    """Execute pre-combat orientation without creating a facing/target transaction."""

    global _PHYSICAL_INSTALLED
    if _PHYSICAL_INSTALLED:
        return

    from . import live_bridge as live_module
    from .runtime_tile_perception import current_hostility_gate

    CurrentPhysical = live_module.PhysicalCombatInput

    class TargetIntegrityPhysicalInput(CurrentPhysical):
        def execute(self, decision, *, confirm_aim=None):
            mode = PR26ControlMode.from_environment()
            if mode is not PR26ControlMode.FULL_COMBAT:
                return super().execute(decision, confirm_aim=confirm_aim)

            gate = current_hostility_gate()
            if has_latched_hostile_memory(gate):
                return super().execute(decision, confirm_aim=confirm_aim)

            safe = _copy_decision(
                decision,
                move=None,
                move_pulse_profile=None,
                move_pulse_ms=None,
                press_h=False,
                h_pulse_ms=None,
                h_authorized=False,
                r_authorized=False,
                turn_direction=None,
                h_cancel_reason="PR26_NO_HOSTILE_LATCH",
            )
            hint = getattr(gate, "_pr26_orientation_hint", None) if gate is not None else None
            now = time.monotonic()
            hint_fresh = bool(
                hint is not None
                and now - float(hint.timestamp) <= _ORIENTATION_HINT_MAX_AGE_SECONDS
                and bool(getattr(gate.map, "camera_alignment_authoritative", False))
            )
            if hint_fresh:
                last_at = float(getattr(gate, "_pr26_orientation_command_at", -1e9))
                last_direction = getattr(gate, "_pr26_orientation_command_direction", None)
                can_repeat = (
                    hint.direction != last_direction
                    or now - last_at >= _ORIENTATION_REPEAT_SECONDS
                )
                if can_repeat:
                    self.controller.repeat_keys = set()
                    self.controller.release_all()
                    actions = tuple(self.execute_turn(hint.direction))
                    gate._pr26_orientation_command_at = now
                    gate._pr26_orientation_command_direction = hint.direction
                    print(
                        "PR26_ORIENTATION_HINT_TURN "
                        f"direction={hint.direction} track={hint.track_id} "
                        "logical_target=NONE combat_lock=False facing_transaction=NONE"
                    )
                    return actions + ("PR26_ORIENTATION_HINT_ONLY",)

            actions = tuple(super().execute(safe, confirm_aim=confirm_aim))
            return actions + ("PR26_NO_HOSTILE_LATCH_MOVE_H_BLOCKED",)

    live_module.PhysicalCombatInput = TargetIntegrityPhysicalInput
    _PHYSICAL_INSTALLED = True
    print(
        "PR26.14 PHYSICAL INTEGRITY: pre-combat orientation is an isolated pulse; "
        "without a hostile latch TURN transactions, MOVE and H cannot enter combat state"
    )


def _decision_payload(decision: Any) -> dict[str, Any]:
    fields = (
        "frame_index",
        "combat_target_id",
        "visual_track_id",
        "grid_distance",
        "face",
        "raw_target_bearing",
        "stable_target_bearing",
        "commanded_facing",
        "confirmed_facing",
        "turn_direction",
        "r_authorized",
        "h_authorized",
        "orientation_invalidated_reason",
        "reason",
    )
    payload: dict[str, Any] = {}
    for name in fields:
        value = getattr(decision, name, None)
        if hasattr(value, "value"):
            value = value.value
        payload[name] = value
    target_state = getattr(decision, "target_state", None)
    payload["target_state"] = getattr(target_state, "value", target_state)
    return payload


def install_event_snapshot_integrity() -> None:
    """Freeze occupancy/decision metadata at event time instead of close time."""

    global _EVENT_RECORDER_INSTALLED
    if _EVENT_RECORDER_INSTALLED:
        return

    from . import event_recorder as event_module
    from .runtime_tile_perception import current_hostility_gate

    CurrentRecorder = event_module.CombatEventVideoRecorder

    class EventSnapshotRecorder(CurrentRecorder):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._pr26_event_payloads: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
            self._pr26_event_last_at: dict[str, float] = {}
            self._pr26_payload_by_path: dict[Any, dict[str, Any]] = {}

        def _freeze_payload(self, event: str, decision: Any, candidate: Any, now: float) -> dict[str, Any]:
            gate = current_hostility_gate()
            snapshot = getattr(gate, "last_snapshot", None) if gate is not None else None
            as_log_fields = getattr(snapshot, "as_log_fields", None)
            occupancy = as_log_fields() if as_log_fields is not None else {}
            return {
                "event": event,
                "event_timestamp": float(now),
                "snapshot_timing": "EVENT_TRIGGER_FRAME",
                "occupancy": occupancy,
                "decision": _decision_payload(decision),
                "candidate": {
                    "track_id": getattr(candidate, "track_id", None),
                    "bbox": list(candidate.bbox) if candidate is not None and candidate.bbox is not None else None,
                    "anchor_cell": (
                        [candidate.anchor_cell.x, candidate.anchor_cell.y]
                        if candidate is not None and candidate.anchor_cell is not None
                        else None
                    ),
                },
            }

        def push(self, frame_bgr, *, decision, candidate, actions, events=(), timestamp=None, **kwargs):
            now = time.monotonic() if timestamp is None else float(timestamp)
            current_events = tuple(events)
            for raw_event in current_events:
                event = self._sanitize(raw_event)
                if now - self._pr26_event_last_at.get(event, -1e9) < 2.0:
                    continue
                self._pr26_event_last_at[event] = now
                self._pr26_event_payloads[event].append(
                    self._freeze_payload(event, decision, candidate, now)
                )
            return super().push(
                frame_bgr,
                decision=decision,
                candidate=candidate,
                actions=actions,
                events=current_events,
                timestamp=timestamp,
                **kwargs,
            )

        def _write_clip(self, clip) -> None:
            before = len(getattr(self, "saved_paths", ()))
            super()._write_clip(clip)
            new_paths = list(getattr(self, "saved_paths", ()))[before:]
            queue = self._pr26_event_payloads.get(clip.event)
            payload = queue.popleft() if queue else None
            if payload is None:
                gate = current_hostility_gate()
                snapshot = getattr(gate, "last_snapshot", None) if gate is not None else None
                as_log_fields = getattr(snapshot, "as_log_fields", None)
                payload = {
                    "event": clip.event,
                    "event_timestamp": float(getattr(clip, "started_at", time.monotonic())),
                    "snapshot_timing": "CLIP_CLOSE_FALLBACK",
                    "occupancy": as_log_fields() if as_log_fields is not None else {},
                    "decision": {},
                    "candidate": {},
                }
            for path in new_paths:
                self._pr26_payload_by_path[path] = payload

        def close(self) -> None:
            super().close()
            for path, payload in self._pr26_payload_by_path.items():
                path.with_suffix(".json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    event_module.CombatEventVideoRecorder = EventSnapshotRecorder
    _EVENT_RECORDER_INSTALLED = True
    print(
        "PR26.14 EVENT SNAPSHOTS: every event JSON is frozen on its trigger frame; "
        "round-close state can no longer overwrite FACE_ONLY/AIM/R metadata"
    )


__all__ = [
    "CameraStabilityGate",
    "has_latched_hostile_memory",
    "install_event_snapshot_integrity",
    "install_target_integrity_physical_gate",
    "install_target_integrity_tracking",
    "rawless_orientation_geometry",
]
