from __future__ import annotations

from typing import Any, Iterable

import cv2
import numpy as np

from .combat_strategy_runtime_v351 import current_runtime_command
from .grid_geometry_v351 import current_grid_geometry


def _text(
    image: np.ndarray,
    value: object,
    x: int,
    y: int,
    *,
    scale: float = 0.30,
    color: tuple[int, int, int] = (245, 245, 245),
) -> None:
    text = str(value)
    cv2.putText(
        image,
        text,
        (int(x), int(y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        float(scale),
        (0, 0, 0),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        (int(x), int(y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        float(scale),
        color,
        1,
        cv2.LINE_AA,
    )


def _snapshot(observer: Any):
    method = getattr(observer, "combat_snapshot", None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:
        return None


def _starvation(observer: Any) -> dict[str, object]:
    strategy = getattr(observer, "combat_strategy", None)
    method = getattr(strategy, "lock_starvation_status", None)
    if not callable(method):
        return {}
    try:
        value = method()
        return dict(value) if isinstance(value, dict) else {}
    except Exception:
        return {}


def _raw_visual_target(observer: Any):
    observations = tuple(getattr(observer, "_last_strategy_observations", ()) or ())
    selected = next((item for item in observations if bool(item.base_selected)), None)
    if selected is None:
        return None
    return selected


def _arena_offset(state: Any) -> tuple[float, float]:
    try:
        x0, y0, _, _ = state.arena_rect
        return float(x0), float(y0)
    except Exception:
        return 0.0, 0.0


def _display_transform(frame: np.ndarray) -> tuple[float, int, int]:
    height, width = frame.shape[:2]
    scale = min(960.0 / max(1, width), 540.0 / max(1, height))
    target_width = int(round(width * scale))
    target_height = int(round(height * scale))
    return scale, (960 - target_width) // 2, (540 - target_height) // 2


def _map_point(
    point: tuple[float, float],
    transform: tuple[float, int, int],
) -> tuple[int, int]:
    scale, offset_x, offset_y = transform
    return (
        int(round(offset_x + point[0] * scale)),
        int(round(offset_y + point[1] * scale)),
    )


def _draw_foot_anchors(
    image: np.ndarray,
    frame_bgr: np.ndarray,
    state: Any,
    observer: Any,
) -> None:
    transform = _display_transform(frame_bgr)
    offset_x, offset_y = _arena_offset(state)

    player_method = getattr(observer, "_player_anchor", None)
    if callable(player_method):
        try:
            point = player_method(state)
            mapped = _map_point(
                (offset_x + float(point[0]), offset_y + float(point[1])),
                transform,
            )
            cv2.drawMarker(image, mapped, (255, 255, 255), cv2.MARKER_CROSS, 14, 2)
            _text(image, "PLAYER FEET", mapped[0] + 7, mapped[1] + 11, scale=0.26)
        except Exception:
            pass

    target_id = getattr(state, "target_id", None)
    track = next(
        (
            item
            for item in tuple(getattr(state, "tracks", ()) or ())
            if int(getattr(item, "track_id", 0) or 0) == int(target_id or -1)
        ),
        None,
    )
    target_method = getattr(observer, "_track_anchor", None)
    if track is not None and callable(target_method):
        try:
            point = target_method(track)
            mapped = _map_point(
                (offset_x + float(point[0]), offset_y + float(point[1])),
                transform,
            )
            cv2.drawMarker(image, mapped, (0, 220, 255), cv2.MARKER_TILTED_CROSS, 14, 2)
            _text(
                image,
                "CLEAN TARGET FEET",
                mapped[0] + 7,
                mapped[1] + 11,
                scale=0.26,
                color=(0, 220, 255),
            )
        except Exception:
            pass


def annotate_strategy_diagnostics(
    canvas: np.ndarray,
    frame_bgr: np.ndarray,
    state: Any,
    observer: Any,
    *,
    raw_candidates: Iterable[Any] = (),
) -> np.ndarray:
    snapshot = _snapshot(observer)
    if snapshot is None or canvas is None or canvas.size == 0:
        return canvas

    image = canvas.copy()
    _draw_foot_anchors(image, frame_bgr, state, observer)

    tracker = getattr(observer, "tracker", None)
    raw_count = int(
        getattr(tracker, "raw_candidate_count", len(tuple(raw_candidates or ()))) or 0
    )
    filtered_count = int(getattr(tracker, "filtered_candidate_count", raw_count) or 0)
    rejected_count = len(tuple(getattr(tracker, "rejected_candidates", ()) or ()))
    command = current_runtime_command(snapshot.combat_target_id)
    starvation = _starvation(observer)
    raw_target = _raw_visual_target(observer)
    geometry = current_grid_geometry()

    clean_age = (
        "-"
        if snapshot.clean_last_seen < 0.0
        else f"{max(0.0, float(state.timestamp) - snapshot.clean_last_seen):.2f}s"
    )
    activity_age = (
        "-"
        if snapshot.any_activity_last_seen < 0.0
        else f"{max(0.0, float(state.timestamp) - snapshot.any_activity_last_seen):.2f}s"
    )
    raw_target_text = "-"
    raw_target_cell = "-"
    raw_target_class = "-"
    if raw_target is not None:
        raw_target_text = str(raw_target.track_id)
        raw_target_cell = str(raw_target.anchor_cell)
        raw_target_class = str(raw_target.classification)
    lock_status = (
        "LOCKED"
        if snapshot.combat_target_id is not None
        else "STARVED"
        if int(starvation.get("consecutive_frames", 0) or 0) >= 8
        else "ATTENTION"
        if snapshot.attention_cell is not None
        else "NONE"
    )
    grid_mode = geometry.mode if geometry is not None else "-"
    cell_size = geometry.cell_size if geometry is not None else "-"

    cv2.rectangle(image, (0, 540), (1040, 719), (9, 12, 10), -1)
    lines = (
        f"STRATEGY {snapshot.strategy}   COMBAT PHASE {snapshot.combat_phase}",
        f"PERCEPTION SCOPE {snapshot.perception_scope}   LOCK STATUS {lock_status}",
        f"GRID MODE {grid_mode}   CELL SIZE {cell_size}px RAW   SOURCE game_mode",
        f"PLAYER CELL {snapshot.player_cell}   CONFIRMED TARGET CELL {snapshot.confirmed_target_cell}",
        f"PREDICTED TARGET CELL {snapshot.predicted_target_cell}",
        f"RAW TARGET #{raw_target_text} CELL {raw_target_cell} CLASS {raw_target_class}",
        f"ATTENTION CELL {snapshot.attention_cell}   HITS {snapshot.attention_hits}",
        f"LOCK STARVATION FRAMES {starvation.get('consecutive_frames', 0)}",
        f"BODY GATE RESULT {starvation.get('body_gate_result', raw_target_class)}",
        f"PENDING REBIND CELL {snapshot.pending_rebind_cell}   HITS {snapshot.pending_rebind_hits}",
        f"CLEAN LAST SEEN age={clean_age}   ANY ACTIVITY age={activity_age}",
        f"CONTAMINATION {snapshot.contamination}   MELEE VISUAL AUTHORITY {snapshot.melee_visual_authority}",
        f"TRACK CREATION {'ENABLED' if snapshot.track_creation_enabled else 'DISABLED'}",
        f"TARGET #{snapshot.combat_target_id or '-'} VISUAL #{snapshot.current_visual_track_id or '-'} STATE {snapshot.target_state}",
        f"MOVE MODE {snapshot.movement_mode}   DIRECTION {snapshot.last_contact_direction}",
        f"CURRENT COMMAND {command}",
        f"CANDIDATES raw={raw_count} filtered={filtered_count} rejected={rejected_count}",
    )
    for index, line in enumerate(lines):
        _text(image, line, 10, 551 + index * 10, scale=0.225)
    return image


def install_combat_strategy_vision():
    from . import dojo_vision_lab_v351 as lab

    if bool(getattr(lab, "_kagelink_combat_strategy_vision_installed", False)):
        return lab.render_round_frame
    original = lab.render_round_frame

    def render_with_strategy_diagnostics(
        frame_bgr,
        state,
        observer,
        *,
        raw_candidates=(),
        engine=None,
        round_number=None,
        sequence=0,
        elapsed=0.0,
    ):
        canvas = original(
            frame_bgr,
            state,
            observer,
            raw_candidates=raw_candidates,
            engine=engine,
            round_number=round_number,
            sequence=sequence,
            elapsed=elapsed,
        )
        return annotate_strategy_diagnostics(
            canvas,
            frame_bgr,
            state,
            observer,
            raw_candidates=raw_candidates,
        )

    lab.render_round_frame = render_with_strategy_diagnostics
    lab._kagelink_combat_strategy_vision_installed = True
    return render_with_strategy_diagnostics


__all__ = ["annotate_strategy_diagnostics", "install_combat_strategy_vision"]
