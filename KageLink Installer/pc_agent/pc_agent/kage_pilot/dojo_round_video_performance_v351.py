from __future__ import annotations

import threading
import time
from typing import Any


def install_round_video_performance_guard(
    recorder: Any,
    *,
    target_fps: float = 2.0,
):
    """Throttle expensive diagnostic rendering by wall clock.

    The recorder previously rendered and encoded a 1280x720 diagnostic frame from
    inside every observer iteration. Dense fights therefore slowed perception and
    made the AVI clock diverge from real time. This guard keeps the exact same source
    frame and annotations, but records at a bounded wall-clock cadence. Skipped
    observer frames return immediately and never affect combat state.
    """

    if recorder is None or bool(getattr(recorder, "_kagelink_performance_guard", False)):
        return recorder

    fps = max(1.0, min(4.0, float(target_fps)))
    interval = 1.0 / fps
    original_record = recorder.record
    lock = threading.RLock()
    last_recorded_at = -1e9
    skipped = 0

    def throttled_record(
        frame_bgr,
        state,
        observer,
        *,
        raw_candidates=(),
        engine=None,
    ) -> bool:
        nonlocal last_recorded_at, skipped
        now = time.monotonic()
        with lock:
            if now - last_recorded_at < interval:
                skipped += 1
                recorder.skipped_observer_frames = skipped
                return False
            last_recorded_at = now
        return bool(
            original_record(
                frame_bgr,
                state,
                observer,
                raw_candidates=raw_candidates,
                engine=engine,
            )
        )

    recorder.record = throttled_record
    recorder.fps = fps
    recorder.skipped_observer_frames = 0
    recorder._kagelink_performance_guard = True
    emit = getattr(recorder, "_emit", None)
    if callable(emit):
        emit(
            "DOJO_ROUND_VIDEO_PERFORMANCE_GUARD",
            {
                "target_fps": f"{fps:.1f}",
                "cadence": "wall_clock",
                "combat_thread": "skip_between_samples",
            },
        )
    return recorder


__all__ = ["install_round_video_performance_guard"]
