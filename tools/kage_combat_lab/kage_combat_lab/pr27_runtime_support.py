from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .pr27_native_grid import CombatAction, PR27Config

MIN_MEDITATION_SECONDS = 5.25


class EmergencyStop(RuntimeError):
    pass


def write_log(handle, payload: dict[str, Any], *, flush: bool = False) -> None:
    if handle is None:
        return
    handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    if flush:
        handle.flush()


def bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def control_mode() -> str:
    value = os.environ.get("KAGE_PR27_CONTROL_MODE", "PERCEPTION_ONLY").strip().upper()
    allowed = {"PERCEPTION_ONLY", "FACE_ONLY", "CONTROL_ENABLED"}
    if value not in allowed:
        raise RuntimeError(f"PR27_CONTROL_MODE_INVALID:{value}")
    if value == "CONTROL_ENABLED" and not bool_env("KAGE_PR27_ALLOW_CONTROL", False):
        raise RuntimeError("PR27_CONTROL_LOCKED_PENDING_STABLE_8_FPS_VALIDATION")
    return value


def config_from_env() -> PR27Config:
    return PR27Config(
        pixel_delta_threshold=int(os.environ.get("KAGE_PR27_PIXEL_DELTA", "18")),
        changed_ratio_threshold=float(os.environ.get("KAGE_PR27_CHANGED_RATIO", "0.035")),
        uncertain_ratio_threshold=float(os.environ.get("KAGE_PR27_UNCERTAIN_RATIO", "0.018")),
        minimum_component_area=int(os.environ.get("KAGE_PR27_MIN_COMPONENT_AREA", "28")),
        minimum_fragment_pixels=int(os.environ.get("KAGE_PR27_MIN_FRAGMENT_PIXELS", "28")),
        minimum_observation_pixels=int(os.environ.get("KAGE_PR27_MIN_OBSERVATION_PIXELS", "72")),
        maximum_fragments_per_group=int(os.environ.get("KAGE_PR27_MAX_FRAGMENTS_PER_GROUP", "32")),
        maximum_missing_frames=int(os.environ.get("KAGE_PR27_MAX_MISSING_FRAMES", "3")),
        target_missing_grace_frames=int(os.environ.get("KAGE_PR27_TARGET_MISSING_GRACE", "4")),
        target_focus_radius_cells=int(os.environ.get("KAGE_PR27_TARGET_FOCUS_RADIUS", "3")),
        maximum_active_tracks=int(os.environ.get("KAGE_PR27_MAX_ACTIVE_TRACKS", "18")),
        association_min_score=float(os.environ.get("KAGE_PR27_ASSOCIATION_SCORE", "0.48")),
        target_association_min_score=float(os.environ.get("KAGE_PR27_TARGET_ASSOCIATION_SCORE", "0.40")),
        player_anchor_x_ratio=float(os.environ.get("KAGE_PR27_PLAYER_X_RATIO", "0.50")),
        player_anchor_y_ratio=float(os.environ.get("KAGE_PR27_PLAYER_Y_RATIO", "0.54")),
        player_anchor_radius_px=float(os.environ.get("KAGE_PR27_PLAYER_RADIUS", "58")),
        enemy_confirm_frames=int(os.environ.get("KAGE_PR27_ENEMY_CONFIRM_FRAMES", "5")),
        attack_distance_cells=int(os.environ.get("KAGE_PR27_ATTACK_DISTANCE", "1")),
        roi_radius_cells=int(os.environ.get("KAGE_PR27_ROI_RADIUS_CELLS", "4")),
        local_occlusion_min_changed_cells=int(os.environ.get("KAGE_PR27_LOCAL_OCCLUSION_MIN_CELLS", "10")),
        local_occlusion_row_span_cells=int(os.environ.get("KAGE_PR27_LOCAL_OCCLUSION_ROW_SPAN", "6")),
        local_occlusion_max_frames=int(os.environ.get("KAGE_PR27_LOCAL_OCCLUSION_MAX_FRAMES", "6")),
        local_background_learning_frames=int(os.environ.get("KAGE_PR27_LOCAL_BACKGROUND_LEARN_FRAMES", "5")),
        facing_confirm_frames=int(os.environ.get("KAGE_PR27_FACING_CONFIRM_FRAMES", "2")),
        facing_correction_cooldown_frames=int(os.environ.get("KAGE_PR27_FACING_COOLDOWN_FRAMES", "1")),
        hit_displacement_px=float(os.environ.get("KAGE_PR27_HIT_DISPLACEMENT_PX", "10")),
        self_association_min_score=float(os.environ.get("KAGE_PR27_SELF_ASSOCIATION_SCORE", "0.56")),
        self_identity_min_score=float(os.environ.get("KAGE_PR27_SELF_IDENTITY_SCORE", "0.34")),
        self_size_ratio_min=float(os.environ.get("KAGE_PR27_SELF_SIZE_RATIO", "0.48")),
        self_ambiguity_margin=float(os.environ.get("KAGE_PR27_SELF_AMBIGUITY_MARGIN", "0.08")),
        self_prediction_frames=int(os.environ.get("KAGE_PR27_SELF_PREDICTION_FRAMES", "10")),
        merged_body_iou_threshold=float(os.environ.get("KAGE_PR27_MERGED_IOU", "0.08")),
        merged_body_area_ratio=float(os.environ.get("KAGE_PR27_MERGED_AREA_RATIO", "1.28")),
        merged_anchor_distance_px=float(os.environ.get("KAGE_PR27_MERGED_ANCHOR_PX", "12")),
        subcell_direction_threshold_px=float(os.environ.get("KAGE_PR27_SUBCELL_DIRECTION_PX", "4")),
        close_enemy_distance_px=float(os.environ.get("KAGE_PR27_CLOSE_ENEMY_PX", "96")),
        close_reacquire_confirm_frames=int(os.environ.get("KAGE_PR27_CLOSE_REACQUIRE_FRAMES", "2")),
        close_idle_soft_frames=int(os.environ.get("KAGE_PR27_CLOSE_IDLE_SOFT_FRAMES", "3")),
        close_idle_turn_frames=int(os.environ.get("KAGE_PR27_CLOSE_IDLE_TURN_FRAMES", "5")),
        close_idle_drop_frames=int(os.environ.get("KAGE_PR27_CLOSE_IDLE_DROP_FRAMES", "8")),
        separation_pulse_ms=int(os.environ.get("KAGE_PR27_SEPARATION_PULSE_MS", "60")),
        separation_cooldown_frames=int(os.environ.get("KAGE_PR27_SEPARATION_COOLDOWN_FRAMES", "6")),
        facing_template_min_score=float(os.environ.get("KAGE_PR27_FACING_TEMPLATE_SCORE", "0.72")),
        facing_template_margin=float(os.environ.get("KAGE_PR27_FACING_TEMPLATE_MARGIN", "0.04")),
        facing_motion_min_px=float(os.environ.get("KAGE_PR27_FACING_MOTION_PX", "3")),
        hit_appearance_similarity=float(os.environ.get("KAGE_PR27_HIT_APPEARANCE_SIMILARITY", "0.60")),
    ).normalized()


class PR27PhysicalInput:
    """Physical boundary with an absolute combat-long R latch."""

    def __init__(self, controller, *, sleep_fn) -> None:
        self.controller = controller
        self.sleep_fn = sleep_fn
        self.active = False
        self.mode = "PERCEPTION_ONLY"
        self.attack_streak = 0
        self.last_h_at = -1e9
        self.h_cooldown_seconds = max(0.5, float(os.environ.get("KAGE_PR27_H_COOLDOWN", "1.75")))
        self.attack_confirm_frames = max(2, int(os.environ.get("KAGE_PR27_ATTACK_CONFIRM_FRAMES", "2")))
        self.separation_pulse_seconds = min(
            0.100,
            max(0.030, float(os.environ.get("KAGE_PR27_SEPARATION_PULSE_MS", "60")) / 1000.0),
        )
        self.combat_r_latched = False

    def _hold_r(self) -> None:
        if self.mode == "CONTROL_ENABLED":
            self.controller.apply_keys(("r",))
            self.combat_r_latched = True

    def activate(self, *, mode: str) -> tuple[str, ...]:
        self.mode = str(mode).strip().upper()
        self.controller.repeat_keys = {"r"}
        self.controller.activate()
        self.controller.release_all()
        self.active = True
        self.attack_streak = 0
        self.last_h_at = -1e9
        self.combat_r_latched = False
        if self.mode == "CONTROL_ENABLED":
            self._hold_r()
            return ("R_DOWN_COMBAT_LATCH",)
        return ("INPUT_ARMED_SAFE",)

    @staticmethod
    def _direction(action: CombatAction) -> str | None:
        for suffix, key in (("LEFT", "left"), ("RIGHT", "right"), ("UP", "up"), ("DOWN", "down")):
            if action.value.endswith(suffix):
                return key
        return None

    def execute(self, action: CombatAction, *, mode: str) -> tuple[str, ...]:
        if not self.active:
            raise RuntimeError("PR27_INPUT_NOT_ACTIVE")
        normalized_mode = str(mode).strip().upper()
        if normalized_mode != self.mode:
            raise RuntimeError(f"PR27_INPUT_MODE_CHANGED:{self.mode}->{normalized_mode}")

        if normalized_mode == "PERCEPTION_ONLY":
            self.attack_streak = 0
            self.controller.release_all()
            return ("PR27_INPUT_BLOCKED",)

        direction = self._direction(action)
        if normalized_mode == "FACE_ONLY":
            self.attack_streak = 0
            if direction is None:
                self.controller.release_all()
                return ("FACE_ONLY_WAIT",)
            return self._turn_face_only(direction)

        self._hold_r()
        if action is CombatAction.NONE:
            self.attack_streak = 0
            return ("R_HELD_COMBAT",)

        if action is CombatAction.ATTACK:
            self.attack_streak += 1
            if self.attack_streak < self.attack_confirm_frames:
                return ("R_HELD_COMBAT", f"H_WAIT_CONFIRM_{self.attack_streak}/{self.attack_confirm_frames}")
            now = time.monotonic()
            remaining = self.h_cooldown_seconds - (now - self.last_h_at)
            if remaining > 0.0:
                return ("R_HELD_COMBAT", f"H_COOLDOWN_{remaining:.2f}S")
            self.controller.apply_keys(("h", "r"))
            self.sleep_fn(0.080)
            self._hold_r()
            self.last_h_at = time.monotonic()
            return ("R_HELD_COMBAT", "H_80MS")

        self.attack_streak = 0
        if direction is not None and action.value.startswith("CHASE_"):
            self.controller.apply_keys(tuple(sorted(("r", direction))))
            self.sleep_fn(0.075)
            self._hold_r()
            return ("R_HELD_COMBAT", f"CHASE_{direction.upper()}_75MS")

        if direction is not None and action.value.startswith("TURN_"):
            self.controller.apply_keys(tuple(sorted(("r", direction))))
            self.sleep_fn(0.060)
            self._hold_r()
            return ("R_HELD_COMBAT", f"TURN_{direction.upper()}_60MS")

        if direction is not None and action.value.startswith("SEPARATE_"):
            self.controller.apply_keys(tuple(sorted(("r", direction))))
            self.sleep_fn(self.separation_pulse_seconds)
            self._hold_r()
            milliseconds = int(round(self.separation_pulse_seconds * 1000.0))
            return ("R_HELD_COMBAT", f"SEPARATE_{direction.upper()}_{milliseconds}MS", "H_BLOCKED_SEPARATION")

        self._hold_r()
        return ("R_HELD_COMBAT",)

    def _turn_face_only(self, direction: str) -> tuple[str, ...]:
        self.controller.release_all()
        self.controller.apply_keys((direction,))
        self.sleep_fn(0.060)
        self.controller.release_all()
        return (f"TURN_{direction.upper()}_60MS",)

    def end_combat(self, reason: str = "COMBAT_END") -> tuple[str, ...]:
        if self.mode == "CONTROL_ENABLED" and self.combat_r_latched:
            self.controller.release_all()
            self.combat_r_latched = False
            self.attack_streak = 0
            print(f"PR27_R_LATCH event=R_UP_COMBAT_END reason={reason}", flush=True)
            return ("R_UP_COMBAT_END", str(reason))
        return ("INPUT_ALREADY_RELEASED", str(reason))

    def close(self) -> None:
        try:
            self.end_combat("CLEANUP")
            self.controller.release_all()
        finally:
            self.active = False
            self.attack_streak = 0
            self.combat_r_latched = False


def create_log(args, module_file: str):
    if args.log is not None:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        return args.log.open("w", encoding="utf-8", buffering=65536), args.log.parent, args.log.stem
    report_root = Path(module_file).resolve().parents[1] / "reports"
    report_root.mkdir(parents=True, exist_ok=True)
    stem = f"pr27_round_{time.strftime('%Y%m%d_%H%M%S')}"
    return (report_root / f"{stem}.jsonl").open("w", encoding="utf-8", buffering=65536), report_root, stem
