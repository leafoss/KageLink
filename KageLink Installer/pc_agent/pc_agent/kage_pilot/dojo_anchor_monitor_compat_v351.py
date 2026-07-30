from __future__ import annotations

from .dojo_position_bridge import DojoAnchorMonitor
from .entity_tracker_v03 import MeleeAwareEntityTracker


def install_anchor_monitor_tracker_compat() -> None:
    """Use the tracker required by the v0.3d observer inside the sidecar monitor.

    The standalone click-time monitor instantiates ParticleSafeGridTargetObserver
    outside the validated runtime patch chain. Its default EntityTracker does not
    expose ``context_for()``, while the observer calls that method for contact
    memory. Replacing only the sidecar's tracker restores the expected contract;
    capture, detection and game control remain unchanged.
    """

    monitor_type = DojoAnchorMonitor
    if bool(getattr(monitor_type, "_kagelink_v351_tracker_compat", False)):
        return

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


__all__ = ["install_anchor_monitor_tracker_compat"]
