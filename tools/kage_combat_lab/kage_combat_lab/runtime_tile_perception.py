from __future__ import annotations

import time
from typing import Any, Callable

from .tile_perception import PR24CombatTilePerception


_INSTALLED = False
_RUNTIME: PR24CombatTilePerception | None = None


def install_runtime_tile_perception(live_bridge_module: Any) -> PR24CombatTilePerception:
    """Install PR24 tile perception before PR25 Target Capsule enrichment."""

    global _INSTALLED, _RUNTIME
    if _INSTALLED and _RUNTIME is not None:
        return _RUNTIME

    perception = PR24CombatTilePerception()
    original: Callable[..., Any] = live_bridge_module.combat_frame_from_observer_state
    next_telemetry_at = 0.0

    def tile_aware_combat_frame_from_observer_state(*args: Any, **kwargs: Any):
        nonlocal next_telemetry_at
        target_memory = kwargs.get("target_memory")
        frame_bgr = kwargs.get("frame_bgr")
        observer = kwargs.get("observer")
        state = kwargs.get("state")
        if target_memory is None or frame_bgr is None or observer is None or state is None:
            raise RuntimeError(
                "PR26_TILE_PIPELINE_REQUIRES_FRAME_STATE_OBSERVER_AND_TARGET_MEMORY"
            )

        original_enrich = target_memory.enrich_candidates

        def tile_first_enrich(*, frame_bgr, state, candidates, timestamp):
            tile_candidates = perception.enrich_candidates(
                frame_bgr=frame_bgr,
                state=state,
                observer=observer,
                candidates=candidates,
                target_memory=target_memory,
            )
            return original_enrich(
                frame_bgr=frame_bgr,
                state=state,
                candidates=tile_candidates,
                timestamp=timestamp,
            )

        target_memory.enrich_candidates = tile_first_enrich
        try:
            combat_frame = original(*args, **kwargs)
        finally:
            target_memory.enrich_candidates = original_enrich

        now = time.monotonic()
        if now >= next_telemetry_at:
            summary = perception.last_summary
            synthetic = sum(
                1 for candidate in combat_frame.candidates if int(candidate.track_id) < 0
            )
            print(
                "PR26_TILE_SCAN "
                f"cells={summary.get('cells', 0)} "
                f"unknown={summary.get('unknown', 0)} "
                f"active_unknown={summary.get('active_unknown', 0)} "
                f"synthetic={synthetic} "
                f"capsule_ready={bool(getattr(target_memory, 'ready', False))}"
            )
            next_telemetry_at = now + 1.0
        return combat_frame

    live_bridge_module.combat_frame_from_observer_state = (
        tile_aware_combat_frame_from_observer_state
    )
    _RUNTIME = perception
    _INSTALLED = True
    return perception


__all__ = ["install_runtime_tile_perception"]
