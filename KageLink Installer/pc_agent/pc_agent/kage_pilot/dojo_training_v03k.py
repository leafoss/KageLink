from __future__ import annotations

from pathlib import Path
import re
import sys

from .dojo_training import (
    DojoTrainingConfig,
    DojoTrainingPhase,
    DojoTrainingService as _BaseDojoTrainingService,
    DojoTrainingSnapshot,
)


class DojoTrainingService(_BaseDojoTrainingService):
    """Stable public facade for source-tree and installed Dojo runtimes.

    Source development keeps the validated Python subprocess path. A frozen
    KageLink.exe launches the sibling ``KagePilotDojo.exe`` helper instead, so
    the same isolated runtime remains usable after installation without relying
    on loose ``.py`` files or a system Python installation.

    Search telemetry also contains fields such as ``completed=2`` for completed
    concentric rings. Those values are not completed Dojo rounds and must never
    update the public service snapshot.
    """

    _COMPLETED_RE = re.compile(
        r"^\s*(?:DOJO_LOOP_(?:FINISHED|STOPPED)|DOJO_FINAL)\b.*\bcompleted=(\d+)\b",
        re.IGNORECASE,
    )

    @property
    def is_frozen_runtime(self) -> bool:
        return bool(getattr(sys, "frozen", False))

    @property
    def packaged_helper_path(self) -> Path:
        return Path(sys.executable).resolve().with_name("KagePilotDojo.exe")

    @property
    def script_path(self) -> Path:
        if self.is_frozen_runtime:
            return self.packaged_helper_path
        return super().script_path

    def build_command(self, config: DojoTrainingConfig) -> list[str]:
        value = config.normalized()
        if self.is_frozen_runtime:
            return [str(self.packaged_helper_path), *value.to_cli_args()]
        return super().build_command(value)

    def runtime_available(self) -> bool:
        return self.script_path.exists()

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
