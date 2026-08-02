from __future__ import annotations


def frame_payload(*, result, native, actions, frame: int, started: float, now: float) -> dict:
    return {
        "event": "PR27_FRAME",
        "t": round(now - started, 4),
        "frame": frame,
        "native_size": [native.source_width, native.source_height],
        "arena": [result.arena_rect.x, result.arena_rect.y, result.arena_rect.width, result.arena_rect.height],
        "state": result.state.value,
        "scene_changed": result.scene_changed,
        "changed_cells": [
            [row, column, round(diff.changed_ratio, 5)]
            for (row, column), diff in result.differences.items()
            if diff.state.value == "CHANGED"
        ],
        "groups": [
            {"group_id": group.group_id, "cells": [[cell.row, cell.column] for cell in group.cells]}
            for group in result.groups
        ],
        "fragments": [
            {
                "fragment_id": fragment.fragment_id,
                "cell": [fragment.cell.row, fragment.cell.column],
                "bbox": list(fragment.native_bbox),
            }
            for fragment in result.fragments
        ],
        "tracks": [
            {
                "track_id": track.track_id,
                "cells": sorted([list(cell) for cell in track.current_cells]),
                "class": track.classification.value,
                "state": track.track_state.value,
                "confidence": round(track.confidence, 4),
            }
            for track in result.tracks
        ],
        "target": None if result.target is None else {
            "track_id": result.target.track_id,
            "cells": sorted([list(cell) for cell in result.target.cells]),
            "direction": result.target.direction,
            "distance_cells": result.target.distance_cells,
            "visible": result.target.visible,
        },
        "action": result.action.value,
        "physical_actions": list(actions),
        "reason": result.reason,
    }
