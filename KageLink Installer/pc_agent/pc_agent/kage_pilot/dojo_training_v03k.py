from __future__ import annotations

import re

from .dojo_training import (
    DojoTrainingConfig,
    DojoTrainingPhase,
    DojoTrainingService as _BaseDojoTrainingService,
    DojoTrainingSnapshot,
)


class DojoTrainingService(_BaseDojoTrainingService):
    """Stable facade with summary-only completed-round telemetry.

    Search telemetry also contains fields such as ``completed=2`` for completed
    concentric rings. Those values are not completed Dojo rounds and must never
    update the public service snapshot.
    """

    _COMPLETED_RE = re.compile(
        r"^\s*(?:DOJO_LOOP_(?:FINISHED|STOPPED)|DOJO_FINAL)\b.*\bcompleted=(\d+)\b",
        re.IGNORECASE,
    )

    @classmethod
    def phase_for_line(cls, line: str, current: DojoTrainingPhase) -> DojoTrainingPhase:
        text = str(line or "").casefold()
        if "dojo_loop_finished" in text or "dojo_loop_stopped" in text:
            return DojoTrainingPhase.STOPPED
        if "dojo_final" in text and "phase=stopped" in text:
            return DojoTrainingPhase.STOPPED
        return super().phase_for_line(line, current)


__all__ = [
    "DojoTrainingConfig",
    "DojoTrainingPhase",
    "DojoTrainingService",
    "DojoTrainingSnapshot",
]
