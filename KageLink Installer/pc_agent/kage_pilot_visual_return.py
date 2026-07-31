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

    from pc_agent.kage_pilot.dojo_resolution_bridge_v351 import (
        install_resolution_independent_dojo,
        install_runtime_geometry_bridge,
        restore_tracker_state_resolution_safe,
    )
    from pc_agent.kage_pilot.dojo_resolution_gate_compat_v351 import (
        install_resolution_gate_slots_compat,
    )
    from pc_agent.kage_pilot.dojo_resolution_scope_compat_v351 import (
        activate_round_resolution_detector,
        install_resolution_scope_compat,
    )
    from pc_agent.kage_pilot.visual_position_guard import install_visual_position_guard

    install_resolution_independent_dojo()
    install_resolution_scope_compat()
    install_resolution_gate_slots_compat()
    install_visual_position_guard()

    import kage_pilot_live_v0351_round as runtime

    activate_round_resolution_detector()

    from pc_agent.kage_pilot.combat_strategy_runtime_v351 import (
        emit_runtime_provenance,
        install_combat_strategy_runtime,
    )
    from pc_agent.kage_pilot.dojo_chakra_recovery_bridge_v351 import (
        install_chakra_recovery_bridge,
    )
    from pc_agent.kage_pilot.dojo_combat_strategy_vision_v351 import (
        install_combat_strategy_vision,
    )
    from pc_agent.kage_pilot.dojo_meditation_timeout_v351 import (
        ensure_safe_meditation_timeout,
        install_meditation_timeout_bridge,
    )
    from pc_agent.kage_pilot.dojo_position_bridge import save_tracker_state
    from pc_agent.kage_pilot.dojo_resource_quantization_v351 import (
        install_resource_quantization_bridge,
    )
    from pc_agent.kage_pilot.dojo_round_video_performance_v351 import (
        install_round_video_performance_guard,
    )
    from pc_agent.kage_pilot.dojo_runtime_guard_v351 import install_runtime_guard
    from pc_agent.kage_pilot.dojo_vision_lab_v351 import install_runtime_lab
    from pc_agent.kage_pilot.position_map_continuity import merge_nonorigin_keyframes

    # Migrate the old 120-second setting before the guard reads it. The physical
    # round-5 capture showed Y becoming eligible only at the end of that window.
    ensure_safe_meditation_timeout(telemetry=runtime._telemetry)

    # Combat is installed once through an explicit strategy factory. The historical
    # compatibility chain remains available as the class base, but no second combat
    # bridge or hardening subclass may silently replace the selected strategy.
    install_combat_strategy_runtime(runtime)

    # Install every non-combat gameplay bridge first. The final recorder observes only
    # the already-processed round input and never changes controls or detector state.
    install_runtime_guard(runtime)
    install_meditation_timeout_bridge(runtime)
    install_runtime_geometry_bridge(runtime)
    install_resource_quantization_bridge(runtime)
    install_chakra_recovery_bridge(runtime)

    # Strategy diagnostics wrap only the rendering function. They expose the exact
    # spatial authority without changing observations, decisions or controls.
    install_combat_strategy_vision()
    recorder = install_runtime_lab(runtime)
    install_round_video_performance_guard(recorder, target_fps=2.0)

    # Record the concrete classes after every bridge has finished. This proves which
    # observer/tracker/strategy/engine/planner the packaged round will instantiate.
    emit_runtime_provenance(runtime)

    if position_path is not None:
        original_init = runtime.ClosedLoopVisualRecoveryEngine.__init__
        original_set_anchor = runtime.ClosedLoopVisualRecoveryEngine._set_visual_anchor

        def bridged_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            restored = restore_tracker_state_resolution_safe(
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
                    "cell_size": f"{self.position.cell_size:.3f}",
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
        if position_path is not None:
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
                            "cell_size": f"{position.cell_size:.3f}",
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
