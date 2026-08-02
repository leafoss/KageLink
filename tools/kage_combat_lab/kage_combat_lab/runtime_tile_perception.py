from __future__ import annotations

import json
import time
from typing import Any, Callable

from .domain import CELL_SIZE_PX
from .hostility_gate_v2 import PR26ContinuityHostilityGate
from .tile_perception import PR24CombatTilePerception, TileClass

# Backward-compatible injection point used by existing runtime tests and tools.
PR26HostilityGate = PR26ContinuityHostilityGate

_INSTALLED = False
_RUNTIME: PR24CombatTilePerception | None = None
_HOSTILITY_GATE: PR26ContinuityHostilityGate | None = None


def current_hostility_gate() -> PR26ContinuityHostilityGate | None:
    return _HOSTILITY_GATE


def install_runtime_tile_perception(
    live_bridge_module: Any,
    full_round_module: Any | None = None,
) -> PR24CombatTilePerception:
    """Install PR24 classification through the continuity-aware hostility gate.

    PR24 may identify a DANGER cell and maintain VISUAL_LOCK, but only a
    positive real track that approaches the stationary player may reach PR25
    Target Capsule and offensive combat authority. PR26.2 bridges normal
    DANGER/UNKNOWN/WALKABLE oscillation with short memory and 2-of-3 voting.
    """

    global _INSTALLED, _RUNTIME, _HOSTILITY_GATE
    if _INSTALLED and _RUNTIME is not None:
        return _RUNTIME

    perception = PR24CombatTilePerception()
    gate = PR26HostilityGate()
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

    def tile_aware_combat_frame_from_observer_state(*args: Any, **kwargs: Any):
        nonlocal next_telemetry_at
        target_memory = kwargs.get("target_memory")
        frame_bgr = kwargs.get("frame_bgr")
        observer = kwargs.get("observer")
        state = kwargs.get("state")
        timestamp = float(kwargs.get("timestamp_seconds") or time.monotonic())
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

        def hostility_first_enrich(*, frame_bgr, state, candidates, timestamp):
            evidence = perception.scan(
                frame_bgr=frame_bgr,
                state=state,
                observer=observer,
            )
            combat_authorized = gate.filter_candidates(
                frame_bgr=frame_bgr,
                state=state,
                observer=observer,
                candidates=candidates,
                evidence=evidence,
                now=timestamp,
            )
            return original_enrich(
                frame_bgr=frame_bgr,
                state=state,
                candidates=combat_authorized,
                timestamp=timestamp,
            )

        target_memory.enrich_candidates = hostility_first_enrich
        previous_origin_x = float(getattr(observer, "grid_origin_x", 0.0))
        previous_origin_y = float(getattr(observer, "grid_origin_y", 0.0))
        # PR24 offsets are measured on the full captured game frame. PR25 tracks
        # and player_center are arena-relative, so subtract arena_rect before
        # using the calibration as the shared cell origin.
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

        now = time.monotonic()
        if now >= next_telemetry_at:
            summary = perception.last_summary
            danger_cells = sum(
                1
                for item in perception.last_evidence.values()
                if item.category is TileClass.DANGER
            )
            snapshot = gate.last_snapshot
            history = ",".join(str(value) for value in snapshot.distance_history) or "-"
            print(
                "PR26_TILE_SCAN "
                f"full_origin=({int(calibrated_full_origin[0])},{int(calibrated_full_origin[1])}) "
                f"arena_origin=({int(calibrated_arena_origin[0])},{int(calibrated_arena_origin[1])}) "
                f"cells={summary.get('cells', 0)} "
                f"danger={danger_cells} "
                f"unknown={summary.get('unknown', 0)} "
                f"active_unknown={summary.get('active_unknown', 0)} "
                "synthetic=0 synthetic_authority=BLOCKED "
                "continuity=2of3 danger_memory=1.25s"
            )
            print(
                "PR26_HOSTILITY "
                f"track={snapshot.raw_track_id if snapshot.raw_track_id is not None else '-'} "
                f"visual_lock={snapshot.visual_lock} combat_lock={snapshot.combat_lock} "
                f"entity_state={snapshot.entity_state.value} "
                f"hostility_state={snapshot.hostility_state.value} "
                f"class={snapshot.terrain_class.value} "
                f"danger_confidence={snapshot.danger_confidence:.2f} "
                f"changed_ratio={snapshot.changed_pixel_ratio:.3f} "
                f"largest_blob={snapshot.largest_blob_area} "
                f"persistence={snapshot.persistence} "
                f"D_history={history} reason={snapshot.reason}"
            )
            next_telemetry_at = now + 1.0
        return combat_frame

    live_bridge_module.combat_frame_from_observer_state = (
        tile_aware_combat_frame_from_observer_state
    )

    if full_round_module is not None:
        original_write_log = full_round_module._write_log

        def hostility_write_log(handle, payload: dict[str, Any]) -> None:
            if payload.get("phase") == "combat":
                payload.update(gate.last_snapshot.as_log_fields())
                payload["synthetic_offensive_authority"] = False
                payload["pr26_continuity_contract"] = {
                    "entity_votes": "2_of_3",
                    "danger_memory_seconds": 1.25,
                    "entity_cell_source": "foot_point_then_bbox_bottom",
                    "acquire": "strict",
                    "maintain": "tolerant",
                }
                payload["pr24_calibrated_full_origin"] = [
                    int(calibrated_full_origin[0]),
                    int(calibrated_full_origin[1]),
                ]
                payload["pr24_calibrated_arena_origin"] = [
                    int(last_arena_origin[0]),
                    int(last_arena_origin[1]),
                ]
                payload["tile_pipeline_contract"] = (
                    "PR24_DANGER_TO_VISUAL_LOCK_TO_HOSTILITY_TO_COMBAT_LOCK"
                )
            original_write_log(handle, payload)

        full_round_module._write_log = hostility_write_log

    # Installed before the facing recorder patch. The later wrapper inherits this
    # class, so hostility transitions are included in evidence videos.
    from . import event_recorder as event_module

    CurrentRecorder = event_module.CombatEventVideoRecorder

    class HostilityEventRecorder(CurrentRecorder):
        def push(self, frame_bgr, *, events=(), **kwargs):
            merged = tuple(events) + gate.consume_video_events()
            overlay = gate.last_overlay_frame
            selected_frame = (
                overlay
                if overlay is not None
                and getattr(overlay, "shape", None) == getattr(frame_bgr, "shape", None)
                else frame_bgr
            )
            return super().push(
                selected_frame,
                events=merged,
                **kwargs,
            )

        def close(self) -> None:
            # FullRound calls close() from its finally block after F12, Ctrl+C,
            # exceptions and normal completion. Persist the current circular
            # buffer before the base recorder clears active events.
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
            snapshot = gate.last_snapshot.as_log_fields()
            for path in getattr(self, "saved_paths", ()):
                if path in before:
                    continue
                metadata_path = path.with_suffix(".json")
                metadata_path.write_text(
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
                            "hostility": snapshot,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

    event_module.CombatEventVideoRecorder = HostilityEventRecorder

    _RUNTIME = perception
    _HOSTILITY_GATE = gate
    _INSTALLED = True
    return perception


__all__ = [
    "current_hostility_gate",
    "install_runtime_tile_perception",
]
