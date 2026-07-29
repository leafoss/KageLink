from __future__ import annotations

from pathlib import Path
import re

from .dojo_training import (
    DojoTrainingConfig,
    DojoTrainingPhase,
    DojoTrainingService as _BaseDojoTrainingService,
    DojoTrainingSnapshot,
)


class DojoTrainingService(_BaseDojoTrainingService):
    """Stable Kage Pilot facade over the canonical non-versioned loop.

    The service keeps summary-only completed-round telemetry. Search telemetry
    also contains fields such as ``completed=2`` for completed concentric rings;
    those values are not completed Dojo rounds and must not update the public
    service snapshot.
    """

    _COMPLETED_RE = re.compile(
        r"^\s*(?:DOJO_LOOP_(?:FINISHED|STOPPED)|DOJO_FINAL)\b.*\bcompleted=(\d+)\b",
        re.IGNORECASE,
    )

    @property
    def script_path(self) -> Path:
        return self.project_dir / "kage_pilot_loop.py"

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
