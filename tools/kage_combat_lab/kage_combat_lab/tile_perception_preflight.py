from __future__ import annotations

import json

from .hostility_gate import HostilityGateConfig
from .tile_perception import PR24CombatTilePerception, TileClass


def main() -> int:
    perception = PR24CombatTilePerception()
    gate = HostilityGateConfig.from_environment()
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
            "calibrated_offset_x_px": int(calibration.get("offset_x_px", 0)),
            "calibrated_offset_y_px": int(calibration.get("offset_y_px", 0)),
            "danger_examples": danger_examples,
            "danger_candidate_confidence": gate.danger_candidate_confidence,
            "danger_strong_confidence": gate.danger_strong_confidence,
            "changed_ratio_suspect": gate.changed_ratio_suspect,
            "changed_ratio_strong": gate.changed_ratio_strong,
            "largest_blob_min": gate.largest_blob_min,
            "largest_blob_strong": gate.largest_blob_strong,
            "entity_persistence_frames": gate.persistence_frames,
            "non_aggressive_seconds": gate.stable_non_aggressive_seconds,
            "synthetic_offensive_authority": False,
            "visual_lock_requires_positive_track": True,
            "combat_lock_requires_hostile_confirmed": True,
        }
    )
    print("PR26.1 HOSTILITY GATE PREFLIGHT: READY")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if danger_examples <= 0:
        raise RuntimeError(
            "PR26_DANGER_EXAMPLES_MISSING: teach at least one PR24 DANGER tile "
            "before arming physical hostility validation"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
