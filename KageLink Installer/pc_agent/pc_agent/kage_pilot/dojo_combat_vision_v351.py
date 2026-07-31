from __future__ import annotations

from typing import Any, Iterable

import cv2
import numpy as np

from .combat_target_v351 import current_combat_command


def _point(value: Any) -> tuple[float, float] | None:
    try:
        x, y = value
        return float(x), float(y)
    except Exception:
        return None


def _box(value: Any) -> tuple[int, int, int, int] | None:
    try:
        x, y, width, height = value
        width = int(round(float(width)))
        height = int(round(float(height)))
        if width <= 0 or height <= 0:
            return None
        return int(round(float(x))), int(round(float(y))), width, height
    except Exception:
        return None


def _arena_rect(frame: np.ndarray, state: Any) -> tuple[int, int, int, int]:
    height, width = frame.shape[:2]
    try:
        x0, y0, x1, y1 = (
            int(round(float(value))) for value in getattr(state, "arena_rect")
        )
    except Exception:
        return 0, 0, width, height
    return (
        max(0, min(width - 1, x0)),
        max(0, min(height - 1, y0)),
        max(x0 + 1, min(width, x1)),
        max(y0 + 1, min(height, y1)),
    )


def _text(
    image: np.ndarray,
    value: object,
    x: int,
    y: int,
    *,
    scale: float = 0.34,
    color: tuple[int, int, int] = (245, 245, 245),
) -> None:
    text = str(value or "-")
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


def _dashed_rectangle(
    image: np.ndarray,
    left: int,
    top: int,
    right: int,
    bottom: int,
    color: tuple[int, int, int],
    *,
    dash: int = 7,
) -> None:
    for x in range(left, right, dash * 2):
        cv2.line(image, (x, top), (min(right, x + dash), top), color, 2)
        cv2.line(image, (x, bottom), (min(right, x + dash), bottom), color, 2)
    for y in range(top, bottom, dash * 2):
        cv2.line(image, (left, y), (left, min(bottom, y + dash)), color, 2)
        cv2.line(image, (right, y), (right, min(bottom, y + dash)), color, 2)


def _direction_endpoint(
    origin: tuple[int, int],
    direction: str,
    length: int = 42,
) -> tuple[int, int]:
    x, y = origin
    return {
        "LEFT": (x - length, y),
        "RIGHT": (x + length, y),
        "UP": (x, y - length),
        "DOWN": (x, y + length),
    }.get(str(direction), origin)


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
        int(round(offset_x + float(point[0]) * scale)),
        int(round(offset_y + float(point[1]) * scale)),
    )


def _combat_snapshot(observer: Any):
    method = getattr(observer, "combat_snapshot", None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:
        return None


def _rejected(observer: Any) -> tuple[Any, ...]:
    tracker = getattr(observer, "tracker", None)
    return tuple(getattr(tracker, "rejected_candidates", ()) or ())


def _authoritative_track(state: Any):
    target_id = getattr(state, "target_id", None)
    if target_id is None:
        return None
    return next(
        (
            track
            for track in tuple(getattr(state, "tracks", ()) or ())
            if int(getattr(track, "track_id", 0) or 0) == int(target_id)
        ),
        None,
    )


def _grid_details(observer: Any, state: Any) -> tuple[str, str, str]:
    tile = float(getattr(observer, "tile_size", 0.0) or 0.0)
    try:
        origin_x, origin_y = getattr(observer, "grid_origin")
        origin = f"{float(origin_x):.1f},{float(origin_y):.1f}"
    except Exception:
        origin = "-"

    target = _authoritative_track(state)
    metrics = None
    if target is not None:
        try:
            metrics = observer.metrics_for(int(getattr(target, "track_id", 0) or 0))
        except Exception:
            metrics = None
    if metrics is None:
        cells = "PLAYER=- TARGET=- d=-"
    else:
        player_cell = getattr(metrics, "player_cell", "-")
        target_cell = getattr(metrics, "cell", "-")
        distance = getattr(metrics, "grid_distance", "-")
        cells = f"PLAYER={player_cell} TARGET={target_cell} d={distance}"

    rejection = getattr(observer, "_last_body_rejection", None)
    if rejection:
        body_gate = f"reject track={rejection[0]} reason={rejection[1]}"
    elif target is not None:
        body_gate = f"accepted track={int(getattr(target, 'track_id', 0) or 0)}"
    else:
        body_gate = "no authoritative body"
    return f"cell={tile:.1f}px origin={origin} anchor=FEET", cells, body_gate


def _draw_physical_anchors(
    image: np.ndarray,
    frame_bgr: np.ndarray,
    state: Any,
    observer: Any,
    transform: tuple[float, int, int],
) -> None:
    x0, y0, _, _ = _arena_rect(frame_bgr, state)
    player_anchor = None
    method = getattr(observer, "_player_anchor", None)
    if callable(method):
        try:
            player_anchor = _point(method(state))
        except Exception:
            player_anchor = None
    if player_anchor is None:
        player_anchor = _point(getattr(state, "player_center", None))
    if player_anchor is not None:
        mapped = _map_point((x0 + player_anchor[0], y0 + player_anchor[1]), transform)
        cv2.drawMarker(image, mapped, (255, 255, 255), cv2.MARKER_CROSS, 14, 2)
        _text(image, "PLAYER FEET", mapped[0] + 7, mapped[1] + 12, scale=0.27)

    target = _authoritative_track(state)
    if target is None:
        return
    target_anchor = None
    target_method = getattr(observer, "_track_anchor", None)
    if callable(target_method):
        try:
            target_anchor = _point(target_method(target))
        except Exception:
            target_anchor = None
    if target_anchor is None:
        bbox = _box(getattr(target, "bbox", None))
        if bbox is not None:
            x, y, width, height = bbox
            target_anchor = (x + width * 0.50, y + height * 0.90)
    if target_anchor is not None:
        mapped = _map_point((x0 + target_anchor[0], y0 + target_anchor[1]), transform)
        cv2.drawMarker(image, mapped, (0, 220, 255), cv2.MARKER_TILTED_CROSS, 14, 2)
        _text(image, "TARGET FEET", mapped[0] + 7, mapped[1] + 12, scale=0.27, color=(0, 220, 255))


def annotate_combat_diagnostics(
    canvas: np.ndarray,
    frame_bgr: np.ndarray,
    state: Any,
    observer: Any,
    *,
    raw_candidates: Iterable[Any] = (),
) -> np.ndarray:
    """Add logical-target diagnostics without changing perception input or state."""

    snapshot = _combat_snapshot(observer)
    if snapshot is None or canvas is None or canvas.size == 0:
        return canvas

    image = canvas.copy()
    x0, y0, _, _ = _arena_rect(frame_bgr, state)
    transform = _display_transform(frame_bgr)
    scale = transform[0]
    player = _point(getattr(state, "player_center", None))
    player_full = None
    if player is not None:
        player_full = _map_point((x0 + player[0], y0 + player[1]), transform)

    _draw_physical_anchors(image, frame_bgr, state, observer, transform)

    predicted = _point(snapshot.predicted_position)
    last_known = _point(snapshot.last_known_position)
    size = _point(snapshot.target_size)
    predicted_full = None
    if predicted is not None:
        predicted_full = _map_point((x0 + predicted[0], y0 + predicted[1]), transform)
        width = (
            int(round(size[0] * scale))
            if size is not None
            else int(round(36 * scale))
        )
        height = (
            int(round(size[1] * scale))
            if size is not None
            else int(round(52 * scale))
        )
        left = predicted_full[0] - width // 2
        top = predicted_full[1] - height // 2
        _dashed_rectangle(
            image,
            left,
            top,
            left + width,
            top + height,
            (245, 180, 40),
        )
        cv2.circle(
            image,
            predicted_full,
            max(1, int(round(float(snapshot.local_rebind_radius) * scale))),
            (150, 80, 240),
            1,
        )
        _text(
            image,
            f"PREDICTED / PREVISTO  CT#{snapshot.combat_target_id or '-'}",
            left,
            max(14, top - 4),
            color=(245, 180, 40),
        )

    if player_full is not None and predicted_full is not None:
        cv2.line(image, player_full, predicted_full, (200, 120, 250), 1)
        direction_end = _direction_endpoint(
            player_full,
            snapshot.last_contact_direction,
        )
        cv2.arrowedLine(
            image,
            player_full,
            direction_end,
            (40, 230, 230),
            2,
            tipLength=0.28,
        )

    trail = []
    for value in tuple(snapshot.trail or ()):
        point = _point(value)
        if point is not None:
            trail.append(_map_point((x0 + point[0], y0 + point[1]), transform))
    for first, second in zip(trail, trail[1:]):
        cv2.line(image, first, second, (100, 210, 250), 1)

    for rejected in _rejected(observer)[:12]:
        bbox = _box(getattr(rejected, "bbox", None))
        reason = str(getattr(rejected, "reason", "REJECTED"))
        if bbox is None:
            continue
        x, y, width, height = bbox
        left, top = _map_point((x0 + x, y0 + y), transform)
        mapped_right, mapped_bottom = _map_point(
            (x0 + x + width, y0 + y + height),
            transform,
        )
        cv2.rectangle(
            image,
            (left, top),
            (mapped_right, mapped_bottom),
            (80, 80, 235),
            1,
        )
        _text(
            image,
            f"REJECTED / REJEITADO: {reason}",
            left,
            max(13, top - 2),
            scale=0.29,
            color=(100, 100, 245),
        )

    tracker = getattr(observer, "tracker", None)
    raw_count = int(
        getattr(tracker, "raw_candidate_count", len(tuple(raw_candidates or ()))) or 0
    )
    filtered_count = int(
        getattr(tracker, "filtered_candidate_count", raw_count) or 0
    )
    rejected_count = len(_rejected(observer))
    state_tracks = tuple(getattr(state, "tracks", ()) or ())
    flow = getattr(state, "global_flow", None)
    flow_dx = float(getattr(flow, "dx", 0.0) or 0.0)
    flow_dy = float(getattr(flow, "dy", 0.0) or 0.0)
    flow_points = int(getattr(flow, "points", 0) or 0)
    command = current_combat_command(snapshot.combat_target_id)
    last_text = (
        "-" if last_known is None else f"{last_known[0]:.0f},{last_known[1]:.0f}"
    )
    predicted_text = (
        "-" if predicted is None else f"{predicted[0]:.0f},{predicted[1]:.0f}"
    )
    grid_text, cells_text, body_gate_text = _grid_details(observer, state)

    cv2.rectangle(image, (0, 540), (646, 719), (9, 12, 10), -1)
    lines = (
        (
            f"COMBAT TARGET / ALVO #{snapshot.combat_target_id or '-'}   "
            f"VISUAL TRACK #{snapshot.current_visual_track_id or '-'}"
        ),
        (
            f"STATE / ESTADO {snapshot.target_state}   "
            f"CONF {snapshot.confidence:.2f}   AGE {snapshot.target_age:.1f}s"
        ),
        (
            f"LAST SEEN / VISTO frames={snapshot.frames_since_last_seen} "
            f"time={snapshot.time_since_last_seen:.2f}s"
        ),
        f"LAST / ULTIMO {last_text}   PREDICTED / PREVISTO {predicted_text}",
        (
            f"DIRECTION / DIRECAO {snapshot.last_contact_direction}   "
            f"MOVE MODE {snapshot.movement_mode}"
        ),
        f"CURRENT COMMAND / COMANDO {command}",
        f"GRID / GRADE {grid_text}",
        f"CELLS / CELULAS {cells_text}",
        f"BODY GATE / CORPO {body_gate_text}",
        (
            f"CANDIDATES raw={raw_count} filtered={filtered_count} "
            f"rejected={rejected_count} tracks={len(state_tracks)}"
        ),
        f"CAMERA FLOW dx={flow_dx:+.2f} dy={flow_dy:+.2f} points={flow_points}",
    )
    for index, line in enumerate(lines):
        _text(image, line, 10, 552 + index * 15, scale=0.285)
    return image


def install_combat_vision_bridge():
    from . import dojo_vision_lab_v351 as lab

    if bool(getattr(lab, "_kagelink_v351_combat_vision_installed", False)):
        return lab.render_round_frame
    original = lab.render_round_frame

    def render_with_combat_diagnostics(
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
        return annotate_combat_diagnostics(
            canvas,
            frame_bgr,
            state,
            observer,
            raw_candidates=raw_candidates,
        )

    lab.render_round_frame = render_with_combat_diagnostics
    lab._kagelink_v351_combat_vision_installed = True
    return render_with_combat_diagnostics


__all__ = ["annotate_combat_diagnostics", "install_combat_vision_bridge"]
