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
    from pc_agent.kage_pilot.dojo_position_bridge import (
        restore_tracker_state,
        save_tracker_state,
    )
    from pc_agent.kage_pilot.position_map_continuity import merge_nonorigin_keyframes

    if position_path is not None:
        original_init = runtime.ClosedLoopVisualRecoveryEngine.__init__
        original_set_anchor = runtime.ClosedLoopVisualRecoveryEngine._set_visual_anchor

        def bridged_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            restored = restore_tracker_state(
                self.position,
                position_path,
                delete_after_load=False,
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

        def preserving_set_anchor(self, frame_bgr, observer_state):
            preserved = tuple(self.position.keyframes)
            original_set_anchor(self, frame_bgr, observer_state)
            merge_nonorigin_keyframes(self.position, preserved)

        runtime.ClosedLoopVisualRecoveryEngine.__init__ = bridged_init
        runtime.ClosedLoopVisualRecoveryEngine._set_visual_anchor = preserving_set_anchor

    result = 1
    try:
        result = int(runtime.main())
        return result
    finally:
        if position_path is None:
            return
        try:
            import kage_pilot_live_v03e_round as round_runtime

            engine = getattr(round_runtime, "_ACTIVE_RECOVERY_ENGINE", None)
            position = getattr(engine, "position", None)
            if position is not None:
                save_tracker_state(position, position_path)
                snapshot = position.snapshot()
                runtime._telemetry(
                    "DOJO_SESSION_MAP_SAVED",
                    {
                        "path": str(position_path),
                        "x": f"{snapshot.x:.4f}",
                        "y": f"{snapshot.y:.4f}",
                        "state": snapshot.state.value,
                        "keyframes": snapshot.keyframes,
                        "return_code": result,
                    },
                )
        except Exception as error:
            runtime._telemetry(
                "DOJO_SESSION_MAP_SAVE_FAILED",
                {"error": f"{type(error).__name__}:{error}"},
            )


__all__ = ["main"]
