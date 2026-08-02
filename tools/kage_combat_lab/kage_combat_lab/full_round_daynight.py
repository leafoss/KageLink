from __future__ import annotations

import os
import sys


def extract_post_ok_gate(argv: list[str]) -> tuple[bool, list[str]]:
    from .full_loop import POST_OK_GATE_ARG

    found = POST_OK_GATE_ARG in argv
    return found, [arg for arg in argv if arg != POST_OK_GATE_ARG]


def _consume_transferred_startup_delay(argv: list[str]) -> list[str]:
    seconds = max(
        0.0,
        float(os.environ.get("KAGE_PR26_PRESPAWN_BASELINE_SECONDS", "0") or 0.0),
    )
    result = list(argv)
    if seconds > 0.0 and "--startup-delay" in result:
        index = result.index("--startup-delay")
        if index + 1 < len(result):
            result[index + 1] = "0.0"
    return result


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
    from .precombat_baseline import prime_pre_spawn_baselines
    from .runtime_control_mode import install_runtime_control_mode
    from .runtime_engagement_recovery import install_runtime_engagement_recovery
    from .runtime_facing_patch import install_runtime_facing_patch
    from .runtime_mask_cluster_guard import install_runtime_mask_cluster_guard
    from .runtime_startup_inherited import install_inherited_post_ok_startup
    from .runtime_tile_perception import (
        current_control_mode,
        install_runtime_tile_perception,
    )

    # Install before the occupancy tracker is constructed so every runtime map
    # receives player exclusion and mask-connected cluster rules.
    install_runtime_mask_cluster_guard()
    tile_perception = install_runtime_tile_perception(
        live_bridge_module,
        full_round_module,
    )
    baseline_count = prime_pre_spawn_baselines(sys.argv[1:])
    sys.argv = [sys.argv[0], *_consume_transferred_startup_delay(sys.argv[1:])]
    install_runtime_facing_patch(full_round_module)
    install_inherited_post_ok_startup()
    install_runtime_engagement_recovery(full_round_module)
    # Must remain last. EngagementRecoveryPhysical has direct baseline-R paths;
    # the PR26 validation wrapper must surround them rather than be surrounded.
    install_runtime_control_mode()
    mode = current_control_mode().value
    print("TRAINER: day-64 + night-64 enabled for post-combat return")
    print("POST_OK_GATE: confirmed; child inherits the one outer RIGHT pulse")
    print(
        f"PR26.4 PRESPAWN BASELINE: stored={baseline_count} "
        "physical_input=BLOCKED startup_delay_consumed=true"
    )
    print("ENGAGEMENT: physical authority is controlled by PR26.4 validation mode")
    print(
        "PR26.4 OCCUPANCY: PR24 DANGER creates a mobile identity; "
        f"terrain_examples={tile_perception.terrain_example_count}"
    )
    print(
        "PR26.4 FLOW: slow PR24 prior -> exact pixel mask -> player exclusion -> "
        "edge-connected DANGER_CLUSTER -> FACE_ONLY_LOCK -> pixel approach -> "
        "HOSTILE_CONFIRMED -> COMBAT_LOCK"
    )
    print("PR26.4 AUTHORITY: HOSTILE_CONFIRMED -> COMBAT_LOCK")
    print(
        "PR26.4 PIXEL TRUTH: EXACT_CELL_BASELINE creates occupancy; "
        "CLASS_REFERENCE is weak attention only; bbox_coverage is telemetry"
    )
    print(
        "PR26.4 CLUSTER: CELL_SIZE=64x64; cardinal mask contact only; "
        "humanoid limit=2x3 cells / 6 total; player pixels removed"
    )
    print(
        f"PR26.4 MODE={mode}: PERCEPTION_ONLY blocks TURN/MOVE/R/H; "
        "FACE_ONLY allows TURN only; FULL_COMBAT requires COMBAT_LOCK"
    )
    print(
        "PR26.4 SAFETY: tile-only and negative synthetic candidates have zero "
        "offensive authority"
    )
    return int(full_round_module.main())


if __name__ == "__main__":
    raise SystemExit(main())
