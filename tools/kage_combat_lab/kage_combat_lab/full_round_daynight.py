from __future__ import annotations

import sys


def extract_post_ok_gate(argv: list[str]) -> tuple[bool, list[str]]:
    from .full_loop import POST_OK_GATE_ARG

    found = POST_OK_GATE_ARG in argv
    return found, [arg for arg in argv if arg != POST_OK_GATE_ARG]


def main() -> int:
    from .dojo_multitemplate import install_day_night_dojo_detector

    install_day_night_dojo_detector()

    post_ok_confirmed, remaining = extract_post_ok_gate(sys.argv[1:])
    sys.argv = [sys.argv[0], *remaining]
    if not post_ok_confirmed:
        raise RuntimeError(
            "START_FACE_RIGHT_REQUIRES_POST_OK_GATE: the facing-authority round "
            "must be launched by FullLoop after dialog/OK/spawn"
        )

    from . import full_round as full_round_module
    from . import live_bridge as live_bridge_module
    from .runtime_control_mode import install_runtime_control_mode
    from .runtime_engagement_recovery import install_runtime_engagement_recovery
    from .runtime_facing_patch import install_runtime_facing_patch
    from .runtime_startup_inherited import install_inherited_post_ok_startup
    from .runtime_tile_perception import (
        current_control_mode,
        install_runtime_tile_perception,
    )

    tile_perception = install_runtime_tile_perception(
        live_bridge_module,
        full_round_module,
    )
    install_runtime_facing_patch(full_round_module)
    install_inherited_post_ok_startup()
    install_runtime_control_mode()
    install_runtime_engagement_recovery(full_round_module)
    mode = current_control_mode().value
    print("TRAINER: day-64 + night-64 enabled for post-combat return")
    print("POST_OK_GATE: confirmed; child inherits the one outer RIGHT pulse")
    print("ENGAGEMENT: physical authority is controlled by PR26.3 validation mode")
    print(
        "PR26.3 OCCUPANCY: PR24 DANGER creates a mobile identity; "
        f"terrain_examples={tile_perception.terrain_example_count}"
    )
    print(
        "PR26.3 FLOW: slow PR24 prior -> real pixel diff -> occupied cells -> "
        "DANGER_CLUSTER -> mobile propagation -> FACE_ONLY_LOCK -> pixel approach -> "
        "HOSTILE_CONFIRMED -> COMBAT_LOCK"
    )
    print("PR26.3 AUTHORITY: HOSTILE_CONFIRMED -> COMBAT_LOCK")
    print(
        "PR26.3 PIXEL TRUTH: true_changed_ratio requires EXACT_CELL_BASELINE or "
        "CLASS_REFERENCE; bbox_coverage_ratio is telemetry only"
    )
    print(
        f"PR26.3 MODE={mode}: PERCEPTION_ONLY blocks TURN/MOVE/R/H; "
        "FACE_ONLY allows TURN only; FULL_COMBAT requires COMBAT_LOCK"
    )
    print(
        "PR26.3 SAFETY: tile-only and negative synthetic candidates have zero "
        "offensive authority"
    )
    return int(full_round_module.main())


if __name__ == "__main__":
    raise SystemExit(main())
