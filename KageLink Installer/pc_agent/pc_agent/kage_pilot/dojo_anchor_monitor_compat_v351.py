from __future__ import annotations

from .dojo_position_bridge import DojoAnchorMonitor
from .dojo_vision_lab_v351 import install_anchor_monitor_lab
from .entity_tracker_v03 import MeleeAwareEntityTracker


def install_anchor_monitor_tracker_compat() -> None:
    """Use the required tracker and attach the local visual diagnostic recorder."""

    monitor_type = DojoAnchorMonitor
    if not bool(getattr(monitor_type, "_kagelink_v351_tracker_compat", False)):
        original_init = monitor_type.__init__

        def compatible_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            observer = getattr(self, "observer", None)
            tracker = getattr(observer, "tracker", None)
            if observer is None or hasattr(tracker, "context_for"):
                return
            config = getattr(observer, "config", None)
            if config is None:
                return
            observer.tracker = MeleeAwareEntityTracker(config)
            self._emit(
                "DOJO_ANCHOR_MONITOR_TRACKER_READY",
                {"tracker": type(observer.tracker).__name__},
            )

        monitor_type.__init__ = compatible_init
        monitor_type._kagelink_v351_tracker_compat = True

    # The Vision Lab wraps the already-corrected monitor. It only observes frames
    # and writes diagnostics; it never clicks, moves or changes detector thresholds.
    install_anchor_monitor_lab(monitor_type)


__all__ = ["install_anchor_monitor_tracker_compat"]
