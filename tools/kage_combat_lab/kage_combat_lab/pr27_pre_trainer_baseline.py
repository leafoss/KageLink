from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

from .pr27_native_grid import ArenaCropper, CellBaselineStore, NativeGrid64, PR27Config

_INSTALLED = False
_CAPTURED = False
TRAINER_BBOX_ENV = "KAGE_PR27_TRAINER_BBOX"
TRAINER_CENTER_ENV = "KAGE_PR27_TRAINER_CENTER_NORMALIZED"


def baseline_path() -> Path:
    configured = os.environ.get("KAGE_PR27_NATIVE_BASELINE_FILE")
    return Path(configured or "kage_pilot_loop_logs/pr27_native_baseline.npz")


def baseline_duration() -> float:
    return max(1.0, float(os.environ.get("KAGE_PR27_PRESPAWN_BASELINE_SECONDS", "5.0") or 5.0))


def reset_native_baseline_capture() -> None:
    global _CAPTURED
    _CAPTURED = False
    os.environ.pop(TRAINER_BBOX_ENV, None)
    os.environ.pop(TRAINER_CENTER_ENV, None)
    try:
        baseline_path().unlink()
    except OSError:
        pass


def _trainer_bbox_tuple(target) -> tuple[int, int, int, int] | None:
    raw = getattr(target, "bbox", None)
    if raw is None:
        return None
    try:
        values = tuple(int(value) for value in raw)
    except (TypeError, ValueError):
        return None
    if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
        return None
    return values


def _trainer_center_normalized(target) -> tuple[float, float] | None:
    try:
        x = float(getattr(target, "normalized_x"))
        y = float(getattr(target, "normalized_y"))
    except (TypeError, ValueError):
        return None
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return x, y


def capture_native_pre_trainer_baseline() -> int:
    """Capture native pixels and a phase-aligned 64px baseline before spawn."""

    import kage_pilot_live_v03 as live_runtime
    from pc_agent.game_capture import GameCapture

    duration = baseline_duration()
    capture = GameCapture()
    cropper = ArenaCropper()
    config = PR27Config().normalized()
    grid = NativeGrid64()
    phase_calibrated = False
    samples: dict[tuple[int, int], deque[np.ndarray]] = defaultdict(lambda: deque(maxlen=7))
    previous: dict[tuple[int, int], np.ndarray] = {}
    cells_by_key: dict[tuple[int, int], object] = {}
    started = time.monotonic()
    settle_until = started + min(0.75, duration * 0.20)
    frame_shape: tuple[int, int] | None = None
    arena_rect = None
    captures = 0
    player_anchor = None

    print(
        f"PR27_NATIVE_BASELINE start duration={duration:.2f}s "
        "source=BEFORE_TRAINER_CLICK jpeg=false resize=false enemy_spawned=false phase=CALIBRATING"
    )
    try:
        while time.monotonic() - started < duration:
            if bool(live_runtime._f12_pressed()):
                raise RuntimeError("F12_STOP")
            native = capture.capture_native()
            frame = native.bgr
            frame_shape = frame.shape[:2]
            rect, arena = cropper.crop(frame)
            arena_rect = rect
            if not phase_calibrated:
                player_anchor = (
                    arena.shape[1] * config.player_anchor_x_ratio,
                    arena.shape[0] * config.player_anchor_y_ratio,
                )
                phase = NativeGrid64.phase_from_anchor(
                    player_anchor,
                    desired_local=(config.grid_player_local_x, config.grid_player_local_y),
                )
                grid.set_phase(*phase)
                phase_calibrated = True
                print(
                    f"PR27_GRID_PHASE_CALIBRATED x={phase[0]} y={phase[1]} "
                    f"player_anchor=({player_anchor[0]:.1f},{player_anchor[1]:.1f}) "
                    f"local=({config.grid_player_local_x},{config.grid_player_local_y})"
                )
            cells = grid.build(arena.shape)
            cells_by_key = {(cell.row, cell.column): cell for cell in cells}
            if time.monotonic() < settle_until:
                time.sleep(0.04)
                continue
            for cell in cells:
                key = (cell.row, cell.column)
                crop = arena[cell.y : cell.y + cell.height, cell.x : cell.x + cell.width].copy()
                old = previous.get(key)
                previous[key] = crop
                if old is None:
                    continue
                temporal = float(np.mean(np.abs(crop.astype(np.int16) - old.astype(np.int16)))) / 255.0
                if temporal > 0.010:
                    samples[key].clear()
                    continue
                samples[key].append(crop)
            captures += 1
            time.sleep(0.04)
    finally:
        capture.close()

    store = CellBaselineStore()
    for key, bucket in samples.items():
        cell = cells_by_key.get(key)
        if cell is None or len(bucket) < 3:
            continue
        stack = np.stack(tuple(bucket))
        median = np.median(stack, axis=0).astype(np.uint8)
        stability = float(np.mean(np.std(stack.astype(np.float32), axis=0))) / 255.0
        store.set(cell, median, stability_score=stability)

    if len(store) == 0 or frame_shape is None or arena_rect is None or player_anchor is None:
        raise RuntimeError("PR27_NATIVE_BASELINE_EMPTY")

    path = baseline_path()
    metadata: dict[str, object] = {
        "version": "PR27.5",
        "source": "BEFORE_TRAINER_CLICK",
        "jpeg": False,
        "resized": False,
        "cell_size_px": 64,
        "comparison_unit": "INDIVIDUAL_NATIVE_PHASED_CELL",
        "cluster_authority": False,
        "combat_authority": "BODY_ANCHOR_CELL",
        "frame_height": int(frame_shape[0]),
        "frame_width": int(frame_shape[1]),
        "arena_rect": [arena_rect.x, arena_rect.y, arena_rect.width, arena_rect.height],
        "grid_phase_x": grid.phase_x,
        "grid_phase_y": grid.phase_y,
        "grid_player_anchor_local": [config.grid_player_local_x, config.grid_player_local_y],
        "player_anchor_ratio": [config.player_anchor_x_ratio, config.player_anchor_y_ratio],
        "player_anchor_arena": [float(player_anchor[0]), float(player_anchor[1])],
        "captures": captures,
        "stored_cells": len(store),
    }
    trainer_bbox = os.environ.get(TRAINER_BBOX_ENV)
    if trainer_bbox:
        metadata["trainer_bbox"] = [int(value) for value in trainer_bbox.split(",")]
    trainer_center = os.environ.get(TRAINER_CENTER_ENV)
    if trainer_center:
        metadata["trainer_center_normalized"] = [float(value) for value in trainer_center.split(",")]
    store.save_npz(path, metadata=metadata)
    print(
        f"PR27_NATIVE_BASELINE complete captures={captures} stored={len(store)} path={path} "
        f"frame={frame_shape[1]}x{frame_shape[0]} jpeg=false resize=false "
        f"grid_phase=({grid.phase_x},{grid.phase_y})"
    )
    return len(store)


def install_native_pre_trainer_baseline_capture() -> None:
    """Bridge inherited trainer search to PR27.5 native phased baseline capture."""

    global _INSTALLED
    if _INSTALLED:
        return
    from pc_agent.kage_pilot import dojo_fight_v03i
    original = dojo_fight_v03i.search_trainer_until_visible
    if getattr(original, "_pr27_native_baseline_bridge", False):
        _INSTALLED = True
        return

    def search_then_capture(*args, **kwargs):
        global _CAPTURED
        target = original(*args, **kwargs)
        bbox = _trainer_bbox_tuple(target)
        center = _trainer_center_normalized(target)
        if bbox is not None:
            os.environ[TRAINER_BBOX_ENV] = ",".join(str(value) for value in bbox)
        else:
            os.environ.pop(TRAINER_BBOX_ENV, None)
        if center is not None:
            os.environ[TRAINER_CENTER_ENV] = f"{center[0]:.8f},{center[1]:.8f}"
            print(f"PR27_TRAINER_EXCLUSION_RESERVED normalized_center=({center[0]:.5f},{center[1]:.5f}) bbox={bbox}")
        else:
            os.environ.pop(TRAINER_CENTER_ENV, None)
            print(f"PR27_TRAINER_EXCLUSION_FALLBACK bbox={bbox}")
        if not _CAPTURED:
            capture_native_pre_trainer_baseline()
            _CAPTURED = True
            print(
                "PR27_NATIVE_BASELINE_READY phase=BEFORE_TRAINER_CLICK "
                f"trainer_bbox={getattr(target, 'bbox', None)}"
            )
        return target

    search_then_capture._pr27_native_baseline_bridge = True
    dojo_fight_v03i.search_trainer_until_visible = search_then_capture
    _INSTALLED = True
    print("PR27.5 OUTER BRIDGE: native phased baseline and normalized trainer centre armed")


__all__ = [
    "TRAINER_BBOX_ENV", "TRAINER_CENTER_ENV", "baseline_path",
    "capture_native_pre_trainer_baseline", "install_native_pre_trainer_baseline_capture",
    "reset_native_baseline_capture",
]
