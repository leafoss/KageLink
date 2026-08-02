from __future__ import annotations

import json

from .domain import CELL_SIZE_PX
from .occupancy_model import OccupancyConfig
from .tile_perception import PR24CombatTilePerception, TileClass


def main() -> int:
    perception = PR24CombatTilePerception()
    occupancy = OccupancyConfig.from_environment()
    calibration = json.loads(
        perception.config.calibration_path.read_text(encoding="utf-8")
    )
    danger_examples = sum(
        1
        for example in perception._terrain_examples
        if example.category is TileClass.DANGER
    )
    payload = perception.describe()
    payload.update(
        {
            "cell_size_px": CELL_SIZE_PX,
            "comparison_unit": "INDIVIDUAL_64PX_CELL",
            "cluster_role": "SEARCH_HINT_ONLY",
            "cluster_bbox_authority": False,
            "cluster_direction_authority": False,
            "cluster_identity_authority": False,
            "cluster_hostility_authority": False,
            "cluster_reid_authority": False,
            "cell_owns_baseline_diff_mask_bbox": True,
            "same_cell_equality_is_identity": False,
            "body_component_pixel_overlap_required": True,
            "latched_visual_requires_current_body": True,
            "pixel_cluster_reid_enabled": False,
            "dominant_terrain_fields_rejected": ["43x64", "64x23"],
            "calibrated_offset_x_px": int(calibration.get("offset_x_px", 0)),
            "calibrated_offset_y_px": int(calibration.get("offset_y_px", 0)),
            "danger_examples": danger_examples,
            "danger_confirmed_similarity": 0.90,
            "danger_likely_similarity": 0.82,
            "danger_weak_similarity": 0.72,
            "danger_margin": 0.04,
            "danger_requires_positive_margin": True,
            "danger_is_priority_not_hard_gate": True,
            "initial_acquisition_radius_cells": 3,
            "round_target_latched_until_ko": True,
            "initial_latch_requires_body_bound_cell_change": True,
            "initial_latch_requires_raw_body_identity": True,
            "rawless_cell_change_combat_authority": False,
            "rawless_whole_cell_entity_authority": False,
            "rawless_compact_vertical_role": "ORIENTATION_HINT_ONLY",
            "turn_only_forwarded_to_strategy": False,
            "turn_only_creates_logical_target": False,
            "logical_target_requires_round_target_latch": True,
            "occluded_coast_requires_round_target_latch": True,
            "local_reid_requires_round_target_latch": True,
            "false_logical_target_reset_to_search": True,
            "target_capsule_before_occupancy_filter": True,
            "target_capsule_component_overlap_required": True,
            "progressive_reid_radius_cells": [1, 2, 3],
            "persistent_reid_seconds_after_valid_latch": 90.0,
            "player_runtime_mask": "NARROW_CAPSULE",
            "player_runtime_mask_max_px": [16, 34],
            "pretrainer_capture": "ROBUST_TEMPORAL_MEDIAN",
            "pretrainer_player_removal": "FULL_PRESPAWN_SILHOUETTE_INPAINT",
            "pretrainer_local_d3_exact_baseline_required": True,
            "pretrainer_three_by_three_cell_exclusion": False,
            "class_reference_initial_acquisition_authority": False,
            "memory_only_move_h_authority": False,
            "entity_lock_requires_exact_baseline": True,
            "entity_lock_requires_motion_or_raw_mask_overlap": True,
            "entity_lock_persistence": "2-of-3",
            "fresh_weak_raw_track_exact_pixel_promotion": True,
            "fresh_weak_raw_track_same_cell_only_promotion": False,
            "player_center_candidate_authority": False,
            "true_changed_ratio_suspect": occupancy.suspect_ratio,
            "true_changed_ratio_strong": occupancy.strong_ratio,
            "largest_blob_min": occupancy.blob_area_min,
            "largest_blob_strong": occupancy.blob_area_strong,
            "mask_edge_contact_px": occupancy.mask_edge_contact_px,
            "mask_edge_band_px": occupancy.mask_edge_band_px,
            "player_mask_margin_px_legacy_ignored_by_capsule": (
                occupancy.player_mask_margin_px
            ),
            "cluster_max_width_cells": occupancy.cluster_max_width_cells,
            "cluster_max_height_cells": occupancy.cluster_max_height_cells,
            "cluster_max_cells": occupancy.cluster_max_cells,
            "class_reference_score_cap": occupancy.class_reference_score_cap,
            "class_reference_seed_authority": False,
            "exact_cell_baseline_seed_authority": True,
            "diagonal_cluster_join": False,
            "player_pixels_removed_before_components": True,
            "bbox_coverage_authority": False,
            "baseline_timing": "BEFORE_TRAINER_CLICK",
            "baseline_frozen_during_combat": True,
            "camera_registration": "PHASE_CORRELATION_WITH_TEMPORAL_CONFIRMATION",
            "camera_min_response_for_motion": 0.16,
            "camera_low_response_static_hold_min": 0.035,
            "camera_low_response_static_hold_px": 2.5,
            "camera_static_hold_preserves_exact_baselines": True,
            "camera_meaningful_shift_confirmation_frames": [2, 3],
            "camera_alignment_uncertain_authority": False,
            "camera_low_response_large_jump_authority": False,
            "raw_track_requires_component_overlap": True,
            "selected_lock_hysteresis_frames": 3,
            "contact_combat_lock": "component_body_bound_2_of_3",
            "event_json_snapshot_timing": "EVENT_TRIGGER_FRAME",
            "post_ok_spawn_wait_preserved": True,
            "synthetic_offensive_authority": False,
            "perception_only_physical_authority": False,
            "combat_lock_requires_hostile_confirmed": True,
        }
    )
    print("PR26.16 BASELINE LIVENESS PREFLIGHT: READY")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if CELL_SIZE_PX != 64:
        raise RuntimeError(f"PR26_CELL_SIZE_INVALID:{CELL_SIZE_PX}")
    if danger_examples <= 0:
        raise RuntimeError(
            "PR26_DANGER_EXAMPLES_MISSING: teach at least one PR24 DANGER tile "
            "before semantic affinity validation"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
