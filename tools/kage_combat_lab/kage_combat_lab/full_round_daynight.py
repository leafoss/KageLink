from __future__ import annotations

import os
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
    from .pre_trainer_baseline import load_pre_trainer_baselines
    from .runtime_camera_compensation import install_runtime_camera_compensation
    from .runtime_control_mode import install_runtime_control_mode
    from .runtime_engagement_recovery import install_runtime_engagement_recovery
    from .runtime_entity_hardening import install_runtime_entity_hardening
    from .runtime_facing_patch import install_runtime_facing_patch
    from .runtime_mask_cluster_guard import install_runtime_mask_cluster_guard
    from .runtime_semantic_entity import install_semantic_entity_priority
    from .runtime_startup_inherited import install_inherited_post_ok_startup
    from .runtime_tile_perception import (
        current_control_mode,
        install_runtime_tile_perception,
    )

    # PR24 is a slow semantic prior. The camera-compensated pixel tracker is the
    # fast authority and must not be forced back to a full 474-example scan on
    # nearly every physical frame.
    os.environ.setdefault("KAGE_PR26_PR24_INTERVAL_SECONDS", "2.0")

    install_runtime_mask_cluster_guard()
    install_semantic_entity_priority()
    install_runtime_entity_hardening()
    install_runtime_camera_compensation()
    tile_perception = install_runtime_tile_perception(
        live_bridge_module,
        full_round_module,
    )
    baseline_count = load_pre_trainer_baselines()
    install_runtime_facing_patch(full_round_module)
    install_inherited_post_ok_startup()
    install_runtime_engagement_recovery(full_round_module)
    install_runtime_control_mode()
    mode = current_control_mode().value
    print("TRAINER: day-64 + night-64 retained for outer request and FULL_COMBAT post-KO")
    print("POST_OK_GATE: confirmed; baseline was captured before trainer click and spawn wait completed")
    print(
        f"PR26.7 CLEAN BASELINE: stored={baseline_count} "
        "source=BEFORE_TRAINER_CLICK frozen_during_combat=true"
    )
    print("ENGAGEMENT: physical authority is controlled by PR26.7 validation mode")
    print(
        "PR26.7 CAMERA: absolute phase registration aligns the frozen world baseline "
        "to the current screen; uncertain alignment blocks all authority"
    )
    print(
        "PR26.7 OCCUPANCY: DANGER requires semantic margin; DANGER_WEAK is ranking "
        f"telemetry only; terrain_examples={tile_perception.terrain_example_count}"
    )
    print(
        "PR26.7 FLOW: camera registration -> exact pixel mask -> player exclusion -> "
        "artifact rejection -> raw-mask entity confirmation -> sticky lock -> COMBAT_LOCK"
    )
    print(
        "PR26.7 AUTHORITY: autonomous approach OR selected raw-confirmed contact 2-of-3 "
        "-> HOSTILE_CONFIRMED -> COMBAT_LOCK"
    )
    print(
        "PR26.7 ARTIFACTS: proportional horizontal bands and multi-cell edge columns "
        "cannot become entities"
    )
    print(
        "PR26.7 CONTINUITY: raw IDs require bbox/mask overlap and never authorize "
        "teleportation; selected lock switches only after a 3-frame challenger"
    )
    print(
        "PR26.7 PIXEL TRUTH: EXACT_CELL_BASELINE is camera-aligned and frozen; "
        "CLASS_REFERENCE remains weak attention only"
    )
    print(
        "PR26.7 CLUSTER: CELL_SIZE=64x64; cardinal mask contact only; "
        "humanoid limit=2x3 cells / 6 total; player pixels removed"
    )
    print(
        f"PR26.7 MODE={mode}: PERCEPTION_ONLY blocks TURN/MOVE/R/H; "
        "FACE_ONLY allows TURN only; FULL_COMBAT requires COMBAT_LOCK"
    )
    # tile-only and negative synthetic candidates have zero offensive authority
    print(
        "PR26.7 SAFETY: camera uncertainty blocks authority; tile-only and negative "
        "synthetic candidates have zero offensive authority"
    )
    return int(full_round_module.main())


if __name__ == "__main__":
    raise SystemExit(main())
