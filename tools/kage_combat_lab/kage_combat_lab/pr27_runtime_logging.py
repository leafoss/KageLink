from __future__ import annotations


def _bbox(value):
    return None if value is None else list(value)


def _point(value):
    return None if value is None else [round(float(value[0]),2),round(float(value[1]),2)]


def frame_payload(*,result,native,actions,frame:int,started:float,now:float)->dict:
    return {
        "event":"PR27_FRAME",
        "t":round(now-started,4),
        "frame":frame,
        "native_size":[native.source_width,native.source_height],
        "arena":[result.arena_rect.x,result.arena_rect.y,result.arena_rect.width,result.arena_rect.height],
        "state":result.state.value,
        "local_state":result.local_state.value,
        "scene_changed":False,
        "roi_center":_point(result.roi_center),
        "roi_radius_cells":result.roi_radius_cells,
        "roi_processed_cell_count":result.roi_processed_cell_count,
        "ignored_outside_roi_count":result.ignored_outside_roi_count,
        "player_cell":[0,0],
        "player_body_bbox":_bbox(result.player_body_bbox),
        "player_body_anchor":_point(result.player_body_anchor),
        "player_body_containment_ratio":round(result.player_body_containment_ratio,4),
        "enemy_relative_cell":None if result.enemy_relative_cell is None else list(result.enemy_relative_cell),
        "local_occlusion_detected":result.local_occlusion_detected,
        "local_background_state":{
            f"{row},{column}":state.value for (row,column),state in result.local_background_states.items()
        },
        "facing_expected":result.facing_expected,
        "facing_detected":result.facing_detected,
        "facing_confirmed":result.facing_confirmed,
        "facing_correction_action":result.facing_correction_action,
        "changed_cells":[
            [row,column,round(diff.changed_ratio,5)]
            for (row,column),diff in result.differences.items() if diff.state.value=="CHANGED"
        ],
        "fragments":[{
            "fragment_id":fragment.fragment_id,
            "cell":[fragment.cell.row,fragment.cell.column],
            "bbox":list(fragment.native_bbox),
            "role":fragment.role.value,
            "role_reason":fragment.role_reason,
            "body_score":round(fragment.body_score,4),
        } for fragment in result.fragments],
        "fragment_rejections":dict(result.fragment_rejections),
        "candidate_rejections":list(result.candidate_rejections),
        "observations":[{
            "observation_id":observation.observation_id,
            "body_bbox":_bbox(observation.body_bbox),
            "body_anchor":_point(observation.body_anchor),
            "anchor_cell":None if observation.anchor_cell is None else list(observation.anchor_cell),
            "body_confidence":round(observation.body_confidence,4),
        } for observation in result.observations],
        "tracks":[{
            "track_id":track.track_id,
            "cells":sorted([list(cell) for cell in track.current_cells]),
            "class":track.classification.value,
            "state":track.track_state.value,
            "confidence":round(track.confidence,4),
            "body_bbox":_bbox(track.body_bbox),
            "body_anchor":_point(track.body_anchor),
            "anchor_cell":None if track.anchor_cell is None else list(track.anchor_cell),
            "body_confidence":round(track.body_confidence,4),
            "observations":track.observations,
            "rejection_reason":track.rejection_reason,
        } for track in result.tracks],
        "target":None if result.target is None else {
            "track_id":result.target.track_id,
            "direction":result.target.direction,
            "distance_cells":result.target.distance_cells,
            "visible":result.target.visible,
            "body_bbox":_bbox(result.target.body_bbox),
            "body_anchor":_point(result.target.body_anchor),
            "anchor_cell":None if result.target.anchor_cell is None else list(result.target.anchor_cell),
        },
        "action":result.action.value,
        "physical_actions":list(actions),
        "combat_r_latched":any(action.startswith("R_HELD_COMBAT") or action=="R_DOWN_COMBAT_LATCH" for action in actions),
        "timings_ms":{key:round(float(value),3) for key,value in result.timings_ms.items()},
        "reason":result.reason,
    }
