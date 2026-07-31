from __future__ import annotations

import threading

from .dojo_position_bridge import DojoAnchorMonitor
from .dojo_raw_trainer_v351 import (
    RawDojoLeaderDetector,
    RawWindowsGameFrameSource,
)
from .dojo_vision_lab_v351 import install_anchor_monitor_lab
from .entity_tracker_v03 import MeleeAwareEntityTracker


def install_anchor_monitor_tracker_compat() -> None:
    """Use RAW Trainer capture, the required tracker and async first capture."""

    monitor_type = DojoAnchorMonitor
    if not bool(getattr(monitor_type, "_kagelink_v351_tracker_compat", False)):
        original_init = monitor_type.__init__
        original_capture_once = monitor_type.capture_once

        def compatible_init(self, *args, **kwargs):
            injected_source = kwargs.get("source") is None
            if injected_source:
                kwargs["source"] = RawWindowsGameFrameSource()
            original_init(self, *args, **kwargs)
            if injected_source:
                self._owns_source = True
            observer = getattr(self, "observer", None)
            tracker = getattr(observer, "tracker", None)
            if (
                observer is not None
                and not hasattr(tracker, "context_for")
                and getattr(observer, "config", None) is not None
            ):
                observer.tracker = MeleeAwareEntityTracker(observer.config)
            self._emit(
                "DOJO_ANCHOR_MONITOR_TRACKER_READY",
                {
                    "tracker": type(getattr(observer, "tracker", None)).__name__,
                    "detector": type(getattr(self, "detector", None)).__name__,
                    "capture": type(getattr(self, "source", None)).__name__,
                    "raw": True,
                },
            )

        def capture_once_with_first_frame(self):
            before = int(getattr(self, "_sequence", 0) or 0)
            result = original_capture_once(self)
            if before == 0 and int(getattr(self, "_sequence", 0) or 0) > 0:
                self._emit(
                    "DOJO_ANCHOR_MONITOR_FIRST_FRAME",
                    {
                        "detector": type(getattr(self, "detector", None)).__name__,
                        "capture": type(getattr(self, "source", None)).__name__,
                        "template_processing": "denied",
                    },
                )
            return result

        def asynchronous_start(self):
            thread = getattr(self, "_thread", None)
            if thread is not None and thread.is_alive():
                return self
            self._stop.clear()
            self._emit(
                "DOJO_ANCHOR_MONITOR_START_REQUESTED",
                {
                    "detector": type(getattr(self, "detector", None)).__name__,
                    "capture": type(getattr(self, "source", None)).__name__,
                    "sync_capture": False,
                },
            )
            self._emit(
                "DOJO_ANCHOR_MONITOR_DETECTOR",
                {
                    "type": type(getattr(self, "detector", None)).__name__,
                    "raw": isinstance(
                        getattr(self, "detector", None),
                        RawDojoLeaderDetector,
                    ),
                    "scan": "exact-1.00",
                },
            )
            self._thread = threading.Thread(
                target=self._run,
                name="DojoAnchorMonitor",
                daemon=True,
            )
            self._thread.start()
            self._emit(
                "DOJO_ANCHOR_MONITOR_STARTED",
                {
                    "buffer_frames": self._frames.maxlen,
                    "sync_capture": False,
                },
            )
            return self

        monitor_type.__init__ = compatible_init
        monitor_type.capture_once = capture_once_with_first_frame
        monitor_type.start = asynchronous_start
        monitor_type._kagelink_v351_tracker_compat = True
        monitor_type._kagelink_raw_async_start = True

    # Vision Lab observes only copies after the RAW detector has completed.
    install_anchor_monitor_lab(monitor_type)


__all__ = ["install_anchor_monitor_tracker_compat"]
