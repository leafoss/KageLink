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
            "calibrated_offset_x_px": int(calibration.get("offset_x_px", 0)),
            "calibrated_offset_y_px": int(calibration.get("offset_y_px", 0)),
            "danger_examples": danger_examples,
            "danger_candidate_confidence": occupancy.danger_confidence,
            "danger_strong_confidence": occupancy.danger_strong_confidence,
            "true_changed_ratio_suspect": occupancy.suspect_ratio,
            "true_changed_ratio_strong": occupancy.strong_ratio,
            "largest_blob_min": occupancy.blob_area_min,
            "largest_blob_strong": occupancy.blob_area_strong,
            "mask_edge_contact_px": occupancy.mask_edge_contact_px,
            "mask_edge_band_px": occupancy.mask_edge_band_px,
            "player_mask_margin_px": occupancy.player_mask_margin_px,
            "cluster_max_width_cells": occupancy.cluster_max_width_cells,
            "cluster_max_height_cells": occupancy.cluster_max_height_cells,
            "cluster_max_cells": occupancy.cluster_max_cells,
            "class_reference_score_cap": occupancy.class_reference_score_cap,
            "class_reference_seed_authority": False,
            "exact_cell_baseline_seed_authority": True,
            "diagonal_cluster_join": False,
            "player_pixels_removed_before_components": True,
            "bbox_coverage_authority": False,
            "synthetic_offensive_authority": False,
            "perception_only_physical_authority": False,
        }
    )
    print("PR26.4 MASK-CONNECTED OCCUPANCY PREFLIGHT: READY")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if CELL_SIZE_PX != 64:
        raise RuntimeError(f"PR26_CELL_SIZE_INVALID:{CELL_SIZE_PX}")
    if danger_examples <= 0:
        raise RuntimeError(
            "PR26_DANGER_EXAMPLES_MISSING: teach at least one PR24 DANGER tile "
            "before arming physical hostility validation"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
