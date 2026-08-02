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
            "cell_owns_baseline_diff_mask_bbox": True,
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
            "rawless_cell_change_combat_authority": False,
            "target_capsule_before_occupancy_filter": True,
            "target_capsule_same_cell_overlap_required": True,
            "progressive_reid_radius_cells": [1, 2, 3],
            "persistent_reid_seconds": 90.0,
            "player_runtime_mask": "NARROW_CAPSULE",
            "player_runtime_mask_max_px": [16, 34],
            "pretrainer_player_core_inpainted": True,
            "pretrainer_three_by_three_cell_exclusion": False,
            "memory_only_move_h_authority": False,
            "entity_lock_requires_exact_baseline": True,
            "entity_lock_requires_motion_or_raw_mask_overlap": True,
            "entity_lock_persistence": "2-of-3",
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
            "camera_registration": "phase_correlation_translation",
            "camera_alignment_uncertain_authority": False,
            "raw_track_requires_component_overlap": True,
            "selected_lock_hysteresis_frames": 3,
            "contact_combat_lock": "same_cell_body_bound_2_of_3",
            "post_ok_spawn_wait_preserved": True,
            "synthetic_offensive_authority": False,
            "perception_only_physical_authority": False,
            "combat_lock_requires_hostile_confirmed": True,
        }
    )
    print("PR26.13 PER-CELL CHANGE AUTHORITY PREFLIGHT: READY")
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
