from __future__ import annotations


def _bbox(value):
    return None if value is None else list(value)


def _point(value):
    return None if value is None else [round(float(value[0]), 2), round(float(value[1]), 2)]


def frame_payload(*, result, native, actions, frame: int, started: float, now: float) -> dict:
    return {
        "event": "PR27_FRAME",
        "version": "PR27.7",
        "t": round(now - started, 4),
        "frame": frame,
        "native_size": [native.source_width, native.source_height],
        "arena": [result.arena_rect.x, result.arena_rect.y, result.arena_rect.width, result.arena_rect.height],
        "state": result.state.value,
        "local_state": result.local_state.value,
        "scene_changed": False,
        "roi_center": _point(result.roi_center),
        "roi_radius_cells": result.roi_radius_cells,
        "roi_processed_cell_count": result.roi_processed_cell_count,
        "ignored_outside_roi_count": result.ignored_outside_roi_count,
        "player_cell": [0, 0],
        "self_track_id": result.player_track_id,
        "self_observation_id": result.self_observation_id,
        "self_role_source": result.self_role_source,
        "self_track_state": result.self_track_state.value,
        "self_confidence": round(result.self_confidence, 4),
        "self_body_bbox": _bbox(result.player_body_bbox),
        "self_body_anchor": _point(result.player_body_anchor),
        "self_predicted_anchor": _point(result.self_predicted_anchor),
        "self_association_score": round(result.self_association_score, 4),
        "self_identity_score": round(result.self_identity_score, 4),
        "player_body_containment_ratio": round(result.player_body_containment_ratio, 4),
        "enemy_track_id": None if result.target is None else result.target.track_id,
        "enemy_observation_id": result.enemy_observation_id,
        "enemy_body_bbox": None if result.target is None else _bbox(result.target.body_bbox),
        "enemy_body_anchor": None if result.target is None else _point(result.target.body_anchor),
        "enemy_relative_cell": None if result.enemy_relative_cell is None else list(result.enemy_relative_cell),
        "enemy_relative_anchor_px": _point(result.enemy_relative_anchor_px),
        "enemy_association_score": round(result.enemy_association_score, 4),
        "enemy_identity_score": round(result.enemy_identity_score, 4),
        "subcell_direction": result.subcell_direction,
        "subcell_direction_confidence": round(result.subcell_direction_confidence, 4),
        "role_conflict": result.role_conflict,
        "role_flip_attempt": result.role_flip_attempt,
        "role_flip_blocked": result.role_flip_blocked,
        "shared_observation_blocked": result.shared_observation_blocked,
        "merged_body_detected": result.merged_body_detected,
        "merged_body_bbox": _bbox(result.merged_body_bbox),
        "self_enemy_iou": round(result.self_enemy_iou, 4),
        "close_candidate_count": result.close_candidate_count,
        "close_reacquire_state": result.close_reacquire_state.value,
        "deadlock_counters": dict(result.deadlock_counters),
        "hit_event": result.hit_event,
        "local_occlusion_detected": result.local_occlusion_detected,
        "local_background_state": {
            f"{row},{column}": state.value
            for (row, column), state in result.local_background_states.items()
        },
        "facing_expected": result.facing_expected,
        "facing_commanded": result.facing_commanded,
        "facing_observed": result.facing_observed,
        "facing_detected": result.facing_detected,
        "facing_template_scores": {
            key: round(float(value), 4)
            for key, value in result.facing_template_scores.items()
        },
        "facing_confirmed": result.facing_confirmed,
        "facing_correction_action": result.facing_correction_action,
        "H_block_reason": result.h_block_reason,
        "recovery_action": result.recovery_action,
        "separation_action": result.separation_action,
        "changed_cells": [
            [row, column, round(difference.changed_ratio, 5)]
            for (row, column), difference in result.differences.items()
            if difference.state.value == "CHANGED"
        ],
        "fragments": [
            {
                "fragment_id": fragment.fragment_id,
                "cell": [fragment.cell.row, fragment.cell.column],
                "bbox": list(fragment.native_bbox),
                "role": fragment.role.value,
                "role_reason": fragment.role_reason,
                "body_score": round(fragment.body_score, 4),
            }
            for fragment in result.fragments
        ],
        "fragment_rejections": dict(result.fragment_rejections),
        "candidate_rejections": list(result.candidate_rejections),
        "association_diagnostics": [dict(item) for item in result.association_diagnostics],
        "observations": [
            {
                "observation_id": observation.observation_id,
                "body_bbox": _bbox(observation.body_bbox),
                "body_anchor": _point(observation.body_anchor),
                "anchor_cell": None if observation.anchor_cell is None else list(observation.anchor_cell),
                "body_confidence": round(observation.body_confidence, 4),
                "reserved_role": observation.reserved_role.value,
                "merged_body": observation.merged_body,
                "role_conflict_reason": observation.role_conflict_reason,
            }
            for observation in result.observations
        ],
        "tracks": [
            {
                "track_id": track.track_id,
                "observation_id": track.observation_id,
                "cells": sorted([list(cell) for cell in track.current_cells]),
                "class": track.classification.value,
                "role": track.effective_role.value,
                "role_locked": track.role_locked,
                "role_source": track.role_source,
                "role_confidence": round(track.role_confidence, 4),
                "role_conflict_reason": track.role_conflict_reason,
                "track_source": track.track_source,
                "state": track.track_state.value,
                "confidence": round(track.confidence, 4),
                "body_bbox": _bbox(track.body_bbox),
                "body_anchor": _point(track.body_anchor),
                "predicted_anchor": _point(track.predicted_anchor),
                "anchor_cell": None if track.anchor_cell is None else list(track.anchor_cell),
                "body_confidence": round(track.body_confidence, 4),
                "association_score": round(track.association_score, 4),
                "identity_score": round(track.identity_score, 4),
                "observations": track.observations,
                "rejection_reason": track.rejection_reason,
            }
            for track in result.tracks
        ],
        "target": None
        if result.target is None
        else {
            "track_id": result.target.track_id,
            "direction": result.target.direction,
            "distance_cells": result.target.distance_cells,
            "visible": result.target.visible,
            "body_bbox": _bbox(result.target.body_bbox),
            "body_anchor": _point(result.target.body_anchor),
            "anchor_cell": None if result.target.anchor_cell is None else list(result.target.anchor_cell),
            "relative_anchor_px": _point(result.target.relative_anchor_px),
        },
        "action": result.action.value,
        "physical_actions": list(actions),
        "combat_r_latched": any(
            action.startswith("R_HELD_COMBAT") or action == "R_DOWN_COMBAT_LATCH"
            for action in actions
        ),
        "timings_ms": {
            key: round(float(value), 3)
            for key, value in result.timings_ms.items()
        },
        "reason": result.reason,
    }
