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
    install_target_integrity_tracking()
    # Final visual invariant: a latched identity cannot migrate to a wall/floor
    # component. Same-cell is only a search location; current body overlap is
    # mandatory before a visual continuation may update target geometry.
    install_visual_target_authority()
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
    print("POST_OK_GATE: confirmed; baseline was captured before trainer click and spawn wait completed")
    print(
        f"PR26.15 CLEAN BASELINE: stored={baseline_count} "
        "source=BEFORE_TRAINER_CLICK player_core=INPAINTED "
        "comparison_unit=INDIVIDUAL_64PX_CELL frozen_during_combat=true"
    )
    print("ENGAGEMENT: physical authority is controlled by PR26.15 validation mode")
    print(
        "PR26.15 CELL AUTHORITY: every 64x64 cell owns its baseline, diff mask, "
        "changed ratio, component bbox and body association"
    )
    print(
        "PR26.15 CLUSTER ROLE: clusters are search hints only; aggregate cluster bbox, "
        "foot, direction, identity, hostility and ReID have zero authority"
    )
    print(
        "PR26.15 SAME-CELL SAFETY: sharing one 64px cell is not identity; the raw/Target "
        "Capsule body must overlap the changed pixels of that specific component"
    )
    print(
        "PR26.15 CURRENT BODY: a latched target may update visible geometry only when "
        "the current frame contains a raw body or confirmed Target Capsule ReID"
    )
    print(
        "PR26.15 TERRAIN REJECTION: dominant 43x64, 64x23 and other high-ratio cell "
        "fields are wall/floor evidence and cannot inherit the hostile identity"
    )
    print(
        "PR26.15 CAMERA STABILITY: low-response jumps are rejected; meaningful "
        "translations require consistent observations before moving frozen baselines"
    )
    print(
        "PR26.15 ORIENTATION SEPARATION: TURN_ONLY is an isolated physical hint and "
        "is never forwarded as a clean combat candidate"
    )
    print(
        "PR26.15 LOGICAL TARGET: GridFocusStrategy receives candidates only after a "
        "same-component raw body binding created HOSTILE_CONFIRMED and COMBAT_LOCK"
    )
    print(
        "PR26.15 REID INVARIANT: OCCLUDED_COAST and REID_LOCAL require a valid "
        "round latch; pixel clusters only select search cells and cannot restore identity"
    )
    print(
        "PR26.15 BODY BINDING: raw detector or Target Capsule must overlap the actual "
        "changed component; anchor-cell equality alone has zero authority"
    )
    print(
        "PR26.15 PLAYER OVERLAP: runtime exclusion is a narrow capsule rather than a "
        "destructive rectangle; side and upper enemy pixels remain visible"
    )
    print(
        "PR26.15 SEARCH RADIUS: initial acquisition and all reacquisition remain "
        "inside Chebyshev D<=3 from the player"
    )
    print(
        "PR26.15 ROUND TARGET: the first body-bound COMBAT_LOCK latches one hostile "
        "identity until KO; terrain components cannot replace its visual geometry"
    )
    print(
        "PR26.15 REPLAY: first successful source capture is written before observer "
        "processing; MP4/AVI/PNG fallback remains enabled"
    )
    print(
        "PR26.15 EVENT JSON: occupancy, decision and candidate snapshots are frozen "
        "on the event trigger frame rather than overwritten at round close"
    )
    print(
        "PR26.15 DIAGNOSTICS: complete child console, recorder bootstrap/final JSON "
        "and round_result.json are always written"
    )
    print(
        "PR26.15 TARGET CAPSULE: raw candidates are enriched before cell association; "
        "confirmed capsule ReID expands progressively D1 -> D2 -> D3"
    )
    print(
        "PR26.15 MEMORY SAFETY: CONTACT_MEMORY, REID_PENDING and OUTSIDE_D3 preserve "
        "a legitimately latched identity while MOVE/H remain physically blocked"
    )
    print(
        "PR26.15 AUTHORITY: COMPONENT_PIXEL_OVERLAP -> CURRENT_BODY -> "
        "HOSTILE_CONFIRMED -> COMBAT_LOCK -> ROUND_TARGET_LATCHED -> facing + chase + H"
    )
    print(
        f"PR26.15 MODE={mode}: PERCEPTION_ONLY blocks TURN/MOVE/R/H; "
        "FACE_ONLY allows TURN only; FULL_COMBAT requires current visual body confirmation"
    )
    # tile-only and negative synthetic candidates have zero offensive authority
    print(
        "PR26.15 SAFETY: camera uncertainty, TURN_ONLY, terrain cells, pixel-only ReID, "
        "memory without current body and negative synthetic candidates have zero offense"
    )

    with RoundRuntimeDiagnostics() as diagnostics:
        exit_code = int(full_round_module.main())
        diagnostics.finish(exit_code)
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
