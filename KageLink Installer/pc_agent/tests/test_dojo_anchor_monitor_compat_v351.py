from __future__ import annotations

import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pc_agent.kage_pilot.dojo_anchor_monitor_compat_v351 import (
    install_anchor_monitor_tracker_compat,
)
from pc_agent.kage_pilot.dojo_position_bridge import DojoAnchorMonitor
from pc_agent.kage_pilot.entity_tracker_v03 import MeleeAwareEntityTracker


class _Source:
    def capture(self):
        raise RuntimeError("capture not expected")

    def close(self):
        return None


class AnchorMonitorCompatV351Tests(unittest.TestCase):
    def test_monitor_uses_context_aware_tracker(self):
        install_anchor_monitor_tracker_compat()
        events = []
        with patch(
            "pc_agent.kage_pilot.dojo_position_bridge.UserDojoLeaderDetector",
            return_value=SimpleNamespace(describe=lambda: "raw=true scales=1.00"),
        ):
            monitor = DojoAnchorMonitor(
                source=_Source(),
                telemetry=lambda event, fields: events.append((event, fields)),
            )
        self.assertIsInstance(monitor.observer.tracker, MeleeAwareEntityTracker)
        self.assertTrue(hasattr(monitor.observer.tracker, "context_for"))
        self.assertTrue(any(event == "DOJO_ANCHOR_MONITOR_TRACKER_READY" for event, _ in events))

    def test_start_does_not_capture_synchronously(self):
        install_anchor_monitor_tracker_compat()
        entered = threading.Event()
        release = threading.Event()
        events = []
        with patch(
            "pc_agent.kage_pilot.dojo_position_bridge.UserDojoLeaderDetector",
            return_value=SimpleNamespace(describe=lambda: "raw=true scales=1.00"),
        ):
            monitor = DojoAnchorMonitor(
                source=_Source(),
                telemetry=lambda event, fields: events.append((event, fields)),
            )

        def blocked_capture():
            entered.set()
            release.wait(1.0)

        monitor.capture_once = blocked_capture
        returned = monitor.start()
        self.assertIs(returned, monitor)
        self.assertTrue(monitor._thread is not None)
        self.assertTrue(monitor._thread.is_alive())
        self.assertTrue(entered.wait(0.5))
        self.assertTrue(any(event == "DOJO_ANCHOR_MONITOR_STARTED" for event, _ in events))
        release.set()
        monitor.stop()

    def test_install_is_idempotent(self):
        install_anchor_monitor_tracker_compat()
        original_init = DojoAnchorMonitor.__init__
        original_start = DojoAnchorMonitor.start
        install_anchor_monitor_tracker_compat()
        self.assertIs(DojoAnchorMonitor.__init__, original_init)
        self.assertIs(DojoAnchorMonitor.start, original_start)


if __name__ == "__main__":
    unittest.main()
