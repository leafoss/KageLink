from __future__ import annotations

import sys


def extract_post_ok_gate(argv: list[str]) -> tuple[bool, list[str]]:
    from .full_loop import POST_OK_GATE_ARG

    found = POST_OK_GATE_ARG in argv
    return found, [arg for arg in argv if arg != POST_OK_GATE_ARG]


def main() -> int:
    from .dojo_multitemplate import install_day_night_dojo_detector
    from .runtime_trainer_suspension import suspend_trainer_detector_for_validation

    detector_class = install_day_night_dojo_detector()
    suspend_trainer_detector_for_validation(detector_class)

    post_ok_confirmed, remaining = extract_post_ok_gate(sys.argv[1:])
    sys.argv = [sys.argv[0], *remaining]
    if not post_ok_confirmed:
        raise RuntimeError(
            "START_FACE_RIGHT_REQUIRES_POST_OK_GATE: the facing-authority round "
            "must be launched by FullLoop after dialog/OK/spawn"
        )

    from . import full_round as full_round_module
    from . import live_bridge as live_bridge_module
    from .pre_ok_baseline import load_pre_ok_baselines
    from .runtime_control_mode import install_runtime_control_mode
    from .runtime_engagement_recovery import install_runtime_engagement_recovery
    from .runtime_facing_patch import install_runtime_facing_patch
    from .runtime_mask_cluster_guard import install_runtime_mask_cluster_guard
    from .runtime_semantic_entity import install_semantic_entity_priority
    from .runtime_startup_inherited import install_inherited_post_ok_startup
    from .runtime_tile_perception import (
        current_control_mode,
        install_runtime_tile_perception,
    )

    # Install before the occupancy tracker is constructed so every runtime map
    # receives player exclusion, mask-connected clustering and semantic affinity.
    install_runtime_mask_cluster_guard()
    install_semantic_entity_priority()
    tile_perception = install_runtime_tile_perception(
        live_bridge_module,
        full_round_module,
    )
    baseline_count = load_pre_ok_baselines()
    install_runtime_facing_patch(full_round_module)
    install_inherited_post_ok_startup()
    install_runtime_engagement_recovery(full_round_module)
    # Must remain last. EngagementRecoveryPhysical has direct baseline-R paths;
    # the PR26 validation wrapper must surround them rather than be surrounded.
    install_runtime_control_mode()
    mode = current_control_mode().value
    print("TRAINER: day-64 + night-64 retained for outer request and FULL_COMBAT post-KO")
    print("POST_OK_GATE: confirmed; baseline was captured before OK and spawn wait completed")
    print(
        f"PR26.5 PRE-OK BASELINE: stored={baseline_count} "
        "source=BEFORE_DIALOG_OK enemy_not_spawned=true"
    )
    print("ENGAGEMENT: physical authority is controlled by PR26.5 validation mode")
    print(
        "PR26.5 OCCUPANCY: DANGER is a strong priority, not a hard acquisition gate; "
        f"terrain_examples={tile_perception.terrain_example_count}"
    )
    print(
        "PR26.5 FLOW: exact pixel mask -> player exclusion -> edge-connected cluster -> "
        "DANGER_LOCK or persistent ENTITY_LOCK -> passive approach -> COMBAT_LOCK"
    )
    print(
        "PR26.5 SEMANTICS: UNKNOWN preserves danger_similarity, floor_similarity and "
        "danger_margin as CONFIRMED/LIKELY/WEAK prior"
    )
    print(
        "PR26.5 PIXEL TRUTH: EXACT_CELL_BASELINE creates occupancy; "
        "CLASS_REFERENCE remains weak attention only"
    )
    print(
        "PR26.5 CLUSTER: CELL_SIZE=64x64; cardinal mask contact only; "
        "humanoid limit=2x3 cells / 6 total; player pixels removed"
    )
    print(
        f"PR26.5 MODE={mode}: PERCEPTION_ONLY blocks TURN/MOVE/R/H; "
        "FACE_ONLY allows TURN only; FULL_COMBAT requires COMBAT_LOCK"
    )
    print(
        "PR26.5 SAFETY: tile-only and negative synthetic candidates have zero "
        "offensive authority"
    )
    return int(full_round_module.main())


if __name__ == "__main__":
    raise SystemExit(main())
