from __future__ import annotations

import math
from typing import Iterable

from .visual_position_v351 import VisualKeyframe, VisualPositionTracker


def merge_nonorigin_keyframes(
    tracker: VisualPositionTracker,
    preserved: Iterable[VisualKeyframe],
    *,
    coordinate_tolerance: float = 0.35,
) -> int:
    """Merge previous-session-map keyframes after an exact Trainer anchor refresh.

    The Trainer represents the same world origin, so non-origin X/Y coordinates remain valid.
    Near-duplicate points are ignored and the bounded tracker capacity is preserved.
    """

    existing = list(tracker.keyframes)
    added = 0
    for item in preserved:
        if item.origin:
            continue
        duplicate = any(
            math.hypot(candidate.x - item.x, candidate.y - item.y) <= coordinate_tolerance
            and candidate.mode == item.mode
            for candidate in existing
        )
        if duplicate:
            continue
        next_id = max((candidate.keyframe_id for candidate in existing), default=0) + 1
        copy = VisualKeyframe(
            keyframe_id=next_id,
            x=item.x,
            y=item.y,
            descriptor=item.descriptor.copy(),
            created_at=item.created_at,
            quality=item.quality,
            mode=item.mode,
            origin=False,
        )
        existing.append(copy)
        added += 1

    if len(existing) > tracker.max_keyframes:
        origin = [item for item in existing if item.origin]
        nonorigin = [item for item in existing if not item.origin]
        nonorigin.sort(key=lambda item: (item.quality, item.created_at), reverse=True)
        existing = [*origin[:1], *nonorigin[: max(0, tracker.max_keyframes - len(origin[:1]))]]

    tracker._keyframes = existing
    tracker._next_keyframe_id = max((item.keyframe_id for item in existing), default=0) + 1
    nonorigin = [item for item in existing if not item.origin]
    tracker._last_keyframe_position = (
        (nonorigin[-1].x, nonorigin[-1].y) if nonorigin else (0.0, 0.0)
    )
    if added:
        tracker._emit(
            "DOJO_KEYFRAME_MAP_PRESERVED",
            added=added,
            total=len(existing),
        )
    return added


__all__ = ["merge_nonorigin_keyframes"]
