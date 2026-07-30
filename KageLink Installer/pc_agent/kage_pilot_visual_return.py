"""Canonical KageLink visual-position and Trainer-return adapter.

Public entry points and packaging specs import this stable module. The physically
validated compatibility provider remains encapsulated behind this boundary until
real Windows/BYOND stress testing authorizes a provider extraction.
"""

from __future__ import annotations

from pathlib import Path
import sys


def _extract_position_state_argument(argv: list[str]) -> Path | None:
    result: Path | None = None
    cleaned: list[str] = [argv[0]] if argv else []
    index = 1
    while index < len(argv):
        value = str(argv[index])
        if value == "--position-state":
            if index + 1 >= len(argv):
                raise SystemExit("--position-state requires a path")
            result = Path(argv[index + 1])
            index += 2
            continue
        if value.startswith("--position-state="):
            result = Path(value.split("=", 1)[1])
            index += 1
            continue
        cleaned.append(value)
        index += 1
    argv[:] = cleaned
    return result


def main() -> int:
    position_path = _extract_position_state_argument(sys.argv)

    from pc_agent.kage_pilot.visual_position_guard import install_visual_position_guard

    install_visual_position_guard()

    import kage_pilot_live_v0351_round as runtime
    from pc_agent.kage_pilot.dojo_position_bridge import restore_tracker_state

    if position_path is not None:
        original_init = runtime.ClosedLoopVisualRecoveryEngine.__init__

        def bridged_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            restored = restore_tracker_state(
                self.position,
                position_path,
                delete_after_load=True,
            )
            snapshot = self.position.snapshot()
            runtime._telemetry(
                "DOJO_POSITION_BRIDGE_RESTORED" if restored else "DOJO_POSITION_BRIDGE_FAILED",
                {
                    "path": str(position_path),
                    "x": f"{snapshot.x:.4f}",
                    "y": f"{snapshot.y:.4f}",
                    "state": snapshot.state.value,
                    "confidence": f"{snapshot.confidence:.3f}",
                    "keyframes": snapshot.keyframes,
                },
            )

        runtime.ClosedLoopVisualRecoveryEngine.__init__ = bridged_init

    return runtime.main()


__all__ = ["main"]
