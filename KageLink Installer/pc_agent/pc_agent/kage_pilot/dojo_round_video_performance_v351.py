from __future__ import annotations

import threading
import time
from typing import Any


def install_round_video_performance_guard(
    recorder: Any,
    *,
    target_fps: float = 2.0,
):
    """Move diagnostic rendering/encoding off the combat perception thread.

    The recorder keeps one latest-frame slot. Observer iterations only copy and
    enqueue an eligible sample; a daemon worker renders the 1280x720 diagnostic
    canvas and writes the AVI. When the worker is busy, an older pending sample is
    replaced by the newest one instead of building latency.
    """

    if recorder is None or bool(getattr(recorder, "_kagelink_performance_guard", False)):
        return recorder

    fps = max(1.0, min(4.0, float(target_fps)))
    interval = 1.0 / fps
    original_record = recorder.record
    original_close = recorder.close

    condition = threading.Condition(threading.RLock())
    pending: tuple[Any, Any, Any, tuple[Any, ...], Any] | None = None
    stopping = False
    worker_busy = False
    last_enqueued_at = -1e9
    skipped = 0
    replaced = 0

    def worker_loop() -> None:
        nonlocal pending, worker_busy
        while True:
            with condition:
                while pending is None and not stopping:
                    condition.wait(timeout=0.25)
                if pending is None and stopping:
                    return
                payload = pending
                pending = None
                worker_busy = True
            try:
                if payload is not None:
                    frame_bgr, state, observer, raw_candidates, engine = payload
                    original_record(
                        frame_bgr,
                        state,
                        observer,
                        raw_candidates=raw_candidates,
                        engine=engine,
                    )
            finally:
                with condition:
                    worker_busy = False
                    condition.notify_all()

    worker = threading.Thread(
        target=worker_loop,
        name="KageLinkRoundVideoWorker",
        daemon=True,
    )
    worker.start()

    def async_record(
        frame_bgr,
        state,
        observer,
        *,
        raw_candidates=(),
        engine=None,
    ) -> bool:
        nonlocal pending, last_enqueued_at, skipped, replaced
        now = time.monotonic()
        with condition:
            if stopping or bool(getattr(recorder, "_closed", False)):
                return False
            if now - last_enqueued_at < interval:
                skipped += 1
                recorder.skipped_observer_frames = skipped
                return False
            last_enqueued_at = now

        try:
            frame_copy = frame_bgr.copy()
        except Exception:
            frame_copy = frame_bgr
        payload = (
            frame_copy,
            state,
            observer,
            tuple(raw_candidates or ()),
            engine,
        )
        with condition:
            if pending is not None:
                replaced += 1
                recorder.replaced_pending_frames = replaced
            pending = payload
            condition.notify()
        return True

    def async_close(reason: str = "runtime_exit"):
        nonlocal stopping
        with condition:
            if stopping:
                return original_close(reason)
            stopping = True
            condition.notify_all()

        # Flush the one pending sample. The recorder's own lock serializes a worker
        # still finishing a frame with the underlying close/release operation.
        worker.join(timeout=4.0)
        destination = original_close(reason)
        emit = getattr(recorder, "_emit", None)
        if callable(emit):
            emit(
                "DOJO_ROUND_VIDEO_PERFORMANCE_SUMMARY",
                {
                    "queued_fps": f"{fps:.1f}",
                    "skipped_observer_frames": skipped,
                    "replaced_pending_frames": replaced,
                    "worker_alive": worker.is_alive(),
                },
            )
        return destination

    recorder.record = async_record
    recorder.close = async_close
    recorder.fps = fps
    recorder.skipped_observer_frames = 0
    recorder.replaced_pending_frames = 0
    recorder._kagelink_performance_guard = True
    recorder._kagelink_video_worker = worker

    emit = getattr(recorder, "_emit", None)
    if callable(emit):
        emit(
            "DOJO_ROUND_VIDEO_PERFORMANCE_GUARD",
            {
                "target_fps": f"{fps:.1f}",
                "cadence": "wall_clock_latest_frame",
                "combat_thread": "enqueue_only",
                "render_thread": "asynchronous",
                "queue_depth": 1,
            },
        )
    return recorder


__all__ = ["install_round_video_performance_guard"]
