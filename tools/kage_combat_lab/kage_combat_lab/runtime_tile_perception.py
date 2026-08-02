from __future__ import annotations

import json
import os
import time
from typing import Any, Callable

from .domain import CELL_SIZE_PX
from .occupancy_tracking import PR26ControlMode, PR26OccupancyTracker
from .tile_perception import PR24CombatTilePerception, TileClass

# Backward-compatible injection point used by runtime tests and tools.
PR26HostilityGate = PR26OccupancyTracker

_INSTALLED = False
_RUNTIME: PR24CombatTilePerception | None = None
_HOSTILITY_GATE: PR26OccupancyTracker | None = None


def current_hostility_gate() -> PR26OccupancyTracker | None:
    return _HOSTILITY_GATE


def current_control_mode() -> PR26ControlMode:
    gate = current_hostility_gate()
    return gate.mode if gate is not None else PR26ControlMode.from_environment()


def _snapshot_field(snapshot: Any, name: str, default: Any) -> Any:
    return getattr(snapshot, name, default)


def install_runtime_tile_perception(
    live_bridge_module: Any,
    full_round_module: Any | None = None,
) -> PR24CombatTilePerception:
    """Install PR26.3 true-pixel occupancy before PR25 combat authority.

    PR24 classification runs as a slow semantic prior. The fast path compares
    every cell against a real exact baseline or a real PR24 class crop, groups
    occupied cells into clusters, and transfers DANGER identity as the cluster
    moves. Bounding-box coverage is telemetry only and can never masquerade as
    a pixel-difference ratio.
    """

    global _INSTALLED, _RUNTIME, _HOSTILITY_GATE
    if _INSTALLED and _RUNTIME is not None:
        return _RUNTIME

    perception = PR24CombatTilePerception()
    gate = PR26HostilityGate()
    bind = getattr(gate, "bind_perception", None)
    if bind is not None:
        bind(perception)

    calibration_payload = json.loads(
        perception.config.calibration_path.read_text(encoding="utf-8")
    )
    calibrated_full_origin = (
        float(calibration_payload.get("offset_x_px", 0)),
        float(calibration_payload.get("offset_y_px", 0)),
    )
    last_arena_origin = [calibrated_full_origin[0], calibrated_full_origin[1]]
    original: Callable[..., Any] = live_bridge_module.combat_frame_from_observer_state
    next_telemetry_at = 0.0
    last_pr24_scan_at = -1e9
    cached_evidence: dict[Any, Any] = {}
    pr24_interval = max(
        0.20,
        float(os.environ.get("KAGE_PR26_PR24_INTERVAL_SECONDS", "1.0")),
    )

    def tile_aware_combat_frame_from_observer_state(*args: Any, **kwargs: Any):
        nonlocal next_telemetry_at, last_pr24_scan_at, cached_evidence
        target_memory = kwargs.get("target_memory")
        frame_bgr = kwargs.get("frame_bgr")
        observer = kwargs.get("observer")
        state = kwargs.get("state")
        timestamp_raw = kwargs.get("timestamp_seconds")
        timestamp = time.monotonic() if timestamp_raw is None else float(timestamp_raw)
        if target_memory is None or frame_bgr is None or observer is None or state is None:
            raise RuntimeError(
                "PR26_TILE_PIPELINE_REQUIRES_FRAME_STATE_OBSERVER_AND_TARGET_MEMORY"
            )

        arena_x, arena_y, _, _ = (int(value) for value in state.arena_rect)
        calibrated_arena_origin = (
            (calibrated_full_origin[0] - float(arena_x)) % CELL_SIZE_PX,
            (calibrated_full_origin[1] - float(arena_y)) % CELL_SIZE_PX,
        )
        last_arena_origin[0] = calibrated_arena_origin[0]
        last_arena_origin[1] = calibrated_arena_origin[1]
        original_enrich = target_memory.enrich_candidates

        def occupancy_first_enrich(*, frame_bgr, state, candidates, timestamp):
            nonlocal last_pr24_scan_at, cached_evidence
            if not cached_evidence or timestamp - last_pr24_scan_at >= pr24_interval:
                cached_evidence = perception.scan(
                    frame_bgr=frame_bgr,
                    state=state,
                    observer=observer,
                )
                last_pr24_scan_at = timestamp
                notify_scan = getattr(gate, "notify_pr24_scan", None)
                if notify_scan is not None:
                    notify_scan(timestamp)
            combat_authorized = gate.filter_candidates(
                frame_bgr=frame_bgr,
                state=state,
                observer=observer,
                candidates=candidates,
                evidence=cached_evidence,
                now=timestamp,
            )
            return original_enrich(
                frame_bgr=frame_bgr,
                state=state,
                candidates=combat_authorized,
                timestamp=timestamp,
            )

        target_memory.enrich_candidates = occupancy_first_enrich
        previous_origin_x = float(getattr(observer, "grid_origin_x", 0.0))
        previous_origin_y = float(getattr(observer, "grid_origin_y", 0.0))
        observer.grid_origin_x = calibrated_arena_origin[0]
        observer.grid_origin_y = calibrated_arena_origin[1]
        try:
            combat_frame = original(*args, **kwargs)
        finally:
            observer.grid_origin_x = previous_origin_x
            observer.grid_origin_y = previous_origin_y
            target_memory.enrich_candidates = original_enrich

        for event_line in gate.consume_console_events():
            print(event_line)

        monotonic_now = time.monotonic()
        if monotonic_now >= next_telemetry_at:
            summary = getattr(perception, "last_summary", {})
            last_evidence = getattr(perception, "last_evidence", {})
            danger_cells = sum(
                1
                for item in last_evidence.values()
                if item.category is TileClass.DANGER
            )
            snapshot = gate.last_snapshot
            grid_history = _snapshot_field(snapshot, "distance_history", ())
            pixel_history = _snapshot_field(snapshot, "pixel_distance_history", ())
            grid_text = ",".join(str(value) for value in grid_history) or "-"
            pixel_text = ",".join(f"{float(value):.1f}" for value in pixel_history) or "-"
            print(
                "PR26_TILE_SCAN "
                f"full_origin=({int(calibrated_full_origin[0])},{int(calibrated_full_origin[1])}) "
                f"arena_origin=({int(calibrated_arena_origin[0])},{int(calibrated_arena_origin[1])}) "
                f"cells={summary.get('cells', 0)} danger={danger_cells} "
                f"unknown={summary.get('unknown', 0)} "
                f"active_unknown={summary.get('active_unknown', 0)} "
                f"pr24_interval={pr24_interval:.2f}s "
                "synthetic=0 synthetic_authority=BLOCKED"
            )
            print(
                "PR26_OCCUPANCY_STATE "
                f"mode={_snapshot_field(snapshot, 'control_mode', 'UNKNOWN')} "
                f"cluster={_snapshot_field(snapshot, 'cluster_id', '-')} "
                f"cells={_snapshot_field(snapshot, 'cluster_cells', ())} "
                f"attention_lock={_snapshot_field(snapshot, 'attention_lock', False)} "
                f"face_only_lock={_snapshot_field(snapshot, 'face_only_lock', False)} "
                f"combat_lock={_snapshot_field(snapshot, 'combat_lock', False)} "
                f"diff_source={_snapshot_field(snapshot, 'diff_source', 'NONE')} "
                f"true_changed_ratio={float(_snapshot_field(snapshot, 'true_changed_ratio', 0.0)):.3f} "
                f"bbox_coverage_ratio={float(_snapshot_field(snapshot, 'bbox_coverage_ratio', 0.0)):.3f} "
                f"occupancy_score={float(_snapshot_field(snapshot, 'occupancy_score', 0.0)):.2f} "
                f"danger_score={float(_snapshot_field(snapshot, 'danger_score', 0.0)):.2f} "
                f"D_history={grid_text} pixel_history={pixel_text} "
                f"reason={_snapshot_field(snapshot, 'reason', '-')}"
            )
            next_telemetry_at = monotonic_now + 1.0
        return combat_frame

    live_bridge_module.combat_frame_from_observer_state = (
        tile_aware_combat_frame_from_observer_state
    )

    if full_round_module is not None:
        original_write_log = full_round_module._write_log

        def occupancy_write_log(handle, payload: dict[str, Any]) -> None:
            if payload.get("phase") == "combat":
                snapshot = gate.last_snapshot
                as_log_fields = getattr(snapshot, "as_log_fields", None)
                if as_log_fields is not None:
                    payload.update(as_log_fields())
                payload["synthetic_offensive_authority"] = False
                payload["pr26_occupancy_contract"] = {
                    "true_changed_ratio": "real_pixel_reference_only",
                    "bbox_coverage_ratio": "telemetry_only",
                    "danger_identity": "mobile_cluster",
                    "danger_memory_seconds": 2.5,
                    "danger_memory_frames": 12,
                    "pr24_role": "slow_semantic_prior",
                    "occupancy_role": "fast_tracking_authority",
                    "control_mode": getattr(gate.mode, "value", str(gate.mode)),
                }
                payload["pr24_calibrated_full_origin"] = [
                    int(calibrated_full_origin[0]),
                    int(calibrated_full_origin[1]),
                ]
                payload["pr24_calibrated_arena_origin"] = [
                    int(last_arena_origin[0]),
                    int(last_arena_origin[1]),
                ]
            original_write_log(handle, payload)

        full_round_module._write_log = occupancy_write_log

    from . import event_recorder as event_module

    CurrentRecorder = event_module.CombatEventVideoRecorder

    class OccupancyEventRecorder(CurrentRecorder):
        def push(self, frame_bgr, *, events=(), **kwargs):
            merged = tuple(events) + gate.consume_video_events()
            overlay = gate.last_overlay_frame
            selected_frame = (
                overlay
                if overlay is not None
                and getattr(overlay, "shape", None) == getattr(frame_bgr, "shape", None)
                else frame_bgr
            )
            return super().push(selected_frame, events=merged, **kwargs)

        def close(self) -> None:
            before = set(getattr(self, "saved_paths", ()))
            buffered = list(getattr(self, "_buffer", ()))
            if buffered:
                clip_type = getattr(event_module, "_ActiveClip")
                self._write_clip(
                    clip_type(
                        "F12_OR_SESSION_STOP",
                        time.monotonic(),
                        [frame.copy() for frame in buffered],
                        0,
                    )
                )
            super().close()
            snapshot = gate.last_snapshot
            as_log_fields = getattr(snapshot, "as_log_fields", None)
            snapshot_payload = as_log_fields() if as_log_fields is not None else {}
            for path in getattr(self, "saved_paths", ()):
                if path in before:
                    continue
                path.with_suffix(".json").write_text(
                    json.dumps(
                        {
                            "event": path.stem,
                            "saved_on_close": True,
                            "includes_f12_shutdown": True,
                            "pr24_calibrated_full_origin": [
                                int(calibrated_full_origin[0]),
                                int(calibrated_full_origin[1]),
                            ],
                            "pr24_calibrated_arena_origin": [
                                int(last_arena_origin[0]),
                                int(last_arena_origin[1]),
                            ],
                            "occupancy": snapshot_payload,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

    event_module.CombatEventVideoRecorder = OccupancyEventRecorder

    _RUNTIME = perception
    _HOSTILITY_GATE = gate
    _INSTALLED = True
    return perception


__all__ = [
    "current_control_mode",
    "current_hostility_gate",
    "install_runtime_tile_perception",
]
