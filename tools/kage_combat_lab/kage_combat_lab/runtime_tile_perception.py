from __future__ import annotations

import time
from typing import Any, Callable

from .hostility_gate import PR26HostilityGate
from .tile_perception import PR24CombatTilePerception, TileClass


_INSTALLED = False
_RUNTIME: PR24CombatTilePerception | None = None
_HOSTILITY_GATE: PR26HostilityGate | None = None


def current_hostility_gate() -> PR26HostilityGate | None:
    return _HOSTILITY_GATE


def install_runtime_tile_perception(
    live_bridge_module: Any,
    full_round_module: Any | None = None,
) -> PR24CombatTilePerception:
    """Install PR24 classification as a passive visual/hostility gate.

    PR24 may identify a DANGER cell and maintain VISUAL_LOCK, but only a
    positive real track that approaches the stationary player may reach PR25
    Target Capsule and offensive combat authority.
    """

    global _INSTALLED, _RUNTIME, _HOSTILITY_GATE
    if _INSTALLED and _RUNTIME is not None:
        return _RUNTIME

    perception = PR24CombatTilePerception()
    gate = PR26HostilityGate()
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
        try:
            combat_frame = original(*args, **kwargs)
        finally:
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
                f"cells={summary.get('cells', 0)} "
                f"danger={danger_cells} "
                f"unknown={summary.get('unknown', 0)} "
                f"active_unknown={summary.get('active_unknown', 0)} "
                "synthetic=0 synthetic_authority=BLOCKED"
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
                f"D_history={history}"
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

    event_module.CombatEventVideoRecorder = HostilityEventRecorder

    _RUNTIME = perception
    _HOSTILITY_GATE = gate
    _INSTALLED = True
    return perception


__all__ = [
    "current_hostility_gate",
    "install_runtime_tile_perception",
]
