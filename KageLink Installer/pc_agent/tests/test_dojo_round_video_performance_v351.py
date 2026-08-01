from __future__ import annotations

import threading
import time
import unittest

from pc_agent.kage_pilot.dojo_round_video_performance_v351 import (
    install_round_video_performance_guard,
)


class _SlowRecorder:
    def __init__(self) -> None:
        self._closed = False
        self.fps = 8.0
        self.calls = 0
        self.events: list[tuple[str, dict[str, object]]] = []
        self.recorded = threading.Event()

    def _emit(self, event: str, fields: dict[str, object]) -> None:
        self.events.append((event, fields))

    def record(self, frame_bgr, state, observer, *, raw_candidates=(), engine=None):
        del frame_bgr, state, observer, raw_candidates, engine
        time.sleep(0.20)
        self.calls += 1
        self.recorded.set()
        return True

    def close(self, reason: str = "runtime_exit"):
        self._closed = True
        return reason


class DojoRoundVideoPerformanceV351Tests(unittest.TestCase):
    def test_rendering_and_encoding_leave_the_perception_thread(self):
        recorder = _SlowRecorder()
        install_round_video_performance_guard(recorder, target_fps=4.0)

        started = time.monotonic()
        queued = recorder.record(
            bytearray(b"frame"),
            object(),
            object(),
            raw_candidates=(),
            engine=None,
        )
        elapsed = time.monotonic() - started

        self.assertTrue(queued)
        self.assertLess(elapsed, 0.10)
        self.assertTrue(recorder.recorded.wait(timeout=1.0))
        recorder.close("unit_test")
        self.assertEqual(recorder.calls, 1)
        self.assertTrue(
            any(event == "DOJO_ROUND_VIDEO_PERFORMANCE_GUARD" for event, _ in recorder.events)
        )
        self.assertTrue(
            any(event == "DOJO_ROUND_VIDEO_PERFORMANCE_SUMMARY" for event, _ in recorder.events)
        )


if __name__ == "__main__":
    unittest.main()
