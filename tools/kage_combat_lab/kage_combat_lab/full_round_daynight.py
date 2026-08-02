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
    from .runtime_acquisition_liveness import (
        install_exact_cell_acquisition_recovery,
        install_static_camera_liveness,
    )
    from .runtime_camera_compensation import install_runtime_camera_compensation
    from .runtime_cell_change_authority import install_cell_change_authority
    from .runtime_combat_target_memory import (
        install_combat_target_continuity_physical_gate,
        install_combat_target_continuity_tracking,
    )
    from .runtime_control_mode import install_runtime_control_mode
    from .runtime_engagement_recovery import install_runtime_engagement_recovery
    from .runtime_entity_hardening import install_runtime_entity_hardening
    from .runtime_facing_patch import install_runtime_facing_patch
    from .runtime_mask_cluster_guard import install_runtime_mask_cluster_guard
    from .runtime_near_enemy_focus import (
        install_near_enemy_focus_physical_gate,
        install_near_enemy_focus_tracking,
    )
    from .runtime_round_diagnostics import (
        RoundRuntimeDiagnostics,
        install_round_runtime_diagnostics,
    )
    from .runtime_semantic_entity import install_semantic_entity_priority
    from .runtime_startup_inherited import install_inherited_post_ok_startup
    from .runtime_target_integrity import (
        install_event_snapshot_integrity,
        install_target_integrity_physical_gate,
        install_target_integrity_tracking,
    )
    from .runtime_tile_perception import (
        current_control_mode,
        install_runtime_tile_perception,
    )
    from .runtime_visual_target_authority import install_visual_target_authority

    os.environ.setdefault("KAGE_PR26_PR24_INTERVAL_SECONDS", "4.0")

    install_runtime_mask_cluster_guard()
    install_semantic_entity_priority()
    install_runtime_entity_hardening()
    install_runtime_camera_compensation()
    install_near_enemy_focus_tracking()
    install_combat_target_continuity_tracking()
    install_cell_change_authority()
    # Patch CameraStabilityGate before target-integrity creates its live instance.
    install_static_camera_liveness()
    install_target_integrity_tracking()
    install_visual_target_authority()
    # Final acquisition rule: exact changed pixels may promote a weak fresh raw
    # track, but same-cell equality, player-center tracks and terrain remain blocked.
    install_exact_cell_acquisition_recovery()
    install_runtime_tile_perception(
        live_bridge_module,
        full_round_module,
    )
    install_event_snapshot_integrity()
    baseline_count = load_pre_trainer_baselines()
    install_runtime_facing_patch(full_round_module)
    install_inherited_post_ok_startup()
    install_runtime_engagement_recovery(full_round_module)
    install_runtime_control_mode()
    install_near_enemy_focus_physical_gate()
    install_combat_target_continuity_physical_gate()
    install_target_integrity_physical_gate()
    install_round_runtime_diagnostics()

    mode = current_control_mode().value
    print("TRAINER: day-64 + night-64 retained for outer request and FULL_COMBAT post-KO")
    print("POST_OK_GATE: confirmed; robust baseline was captured before trainer click and spawn wait completed")
    print(
        f"PR26.16 CLEAN BASELINE: stored={baseline_count} "
        "source=BEFORE_TRAINER_CLICK player=FULL_PRESPAWN_INPAINT "
        "local_D3_coverage=MANDATORY comparison_unit=INDIVIDUAL_64PX_CELL"
    )
    print("ENGAGEMENT: physical authority is controlled by PR26.16 validation mode")
    print(
        "PR26.16 CELL AUTHORITY: every 64x64 cell owns its baseline, diff mask, "
        "component bbox and current-body association; clusters are search hints only"
    )
    print(
        "PR26.16 BASELINE COVERAGE: local D<=3 cells around the pre-spawn player are "
        "mandatory exact baselines; semantic class references have zero acquisition authority"
    )
    print(
        "PR26.16 CAMERA LIVENESS: low correlation with displacement <=2.5px holds the "
        "accepted viewport and keeps exact baselines alive"
    )
    print(
        "PR26.16 FRESH BODY RECOVERY: a weak raw track may be promoted only when its "
        "bbox/foot overlaps changed pixels from that exact cell baseline"
    )
    print(
        "PR26.16 SELF SAFETY: raw tracks centered on the known player, same-cell-only "
        "matches, dominant terrain fields and pixel-only ReID have zero target authority"
    )
    print(
        "PR26.16 CURRENT BODY: a latched target may update visible geometry only from "
        "a current raw body or confirmed Target Capsule ReID"
    )
    print(
        "PR26.16 CAMERA MOTION: meaningful viewport translations still require temporal "
        "confirmation; low-confidence large jumps remain blocked"
    )
    print(
        "PR26.16 ORIENTATION SEPARATION: TURN_ONLY remains outside GridFocusStrategy "
        "and cannot create a logical target, chase, H or ReID"
    )
    print(
        "PR26.16 LOGICAL TARGET: EXACT_COMPONENT_OVERLAP -> CURRENT_BODY -> "
        "HOSTILE_CONFIRMED -> COMBAT_LOCK -> ROUND_TARGET_LATCHED"
    )
    print(
        "PR26.16 REID: only a valid round latch may enter OCCLUDED_COAST/REID_LOCAL; "
        "Target Capsule searches D1 -> D2 -> D3 while MOVE/H remain blocked"
    )
    print(
        "PR26.16 TERRAIN SAFETY: 43x64, 64x23, saturated cells, top/UI bands and "
        "raw-less fields cannot inherit or create hostile identity"
    )
    print(
        "PR26.16 REPLAY/DIAGNOSTICS: complete replay, trigger-frame JSON, child console "
        "and round_result.json remain enabled"
    )
    print(
        f"PR26.16 MODE={mode}: PERCEPTION_ONLY blocks TURN/MOVE/R/H; "
        "FACE_ONLY allows TURN only; FULL_COMBAT requires current visual body confirmation"
    )
    # tile-only and negative synthetic candidates have zero offensive authority

    with RoundRuntimeDiagnostics() as diagnostics:
        exit_code = int(full_round_module.main())
        diagnostics.finish(exit_code)
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
