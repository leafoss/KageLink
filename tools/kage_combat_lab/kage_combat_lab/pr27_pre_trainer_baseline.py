from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

from .pr27_native_grid import ArenaCropper, CellBaselineStore, NativeGrid64

_INSTALLED = False
_CAPTURED = False


def baseline_path() -> Path:
    configured = os.environ.get("KAGE_PR27_NATIVE_BASELINE_FILE")
    return Path(configured or "kage_pilot_loop_logs/pr27_native_baseline.npz")


def baseline_duration() -> float:
    return max(
        1.0,
        float(os.environ.get("KAGE_PR27_PRESPAWN_BASELINE_SECONDS", "5.0") or 5.0),
    )


def reset_native_baseline_capture() -> None:
    global _CAPTURED
    _CAPTURED = False
    try:
        baseline_path().unlink()
    except OSError:
        pass


def capture_native_pre_trainer_baseline() -> int:
    """Capture original DreamSeeker client pixels before trainer click/enemy spawn."""

    import kage_pilot_live_v03 as live_runtime
    from pc_agent.game_capture import GameCapture

    duration = baseline_duration()
    capture = GameCapture()
    cropper = ArenaCropper()
    grid = NativeGrid64()
    samples: dict[tuple[int, int], deque[np.ndarray]] = defaultdict(lambda: deque(maxlen=7))
    previous: dict[tuple[int, int], np.ndarray] = {}
    cells_by_key = {}
    started = time.monotonic()
    settle_until = started + min(0.75, duration * 0.20)
    frame_shape: tuple[int, int] | None = None
    arena_rect = None
    captures = 0

    print(
        f"PR27_NATIVE_BASELINE start duration={duration:.2f}s "
        "source=BEFORE_TRAINER_CLICK jpeg=false resize=false enemy_spawned=false"
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

    if len(store) == 0 or frame_shape is None or arena_rect is None:
        raise RuntimeError("PR27_NATIVE_BASELINE_EMPTY")

    path = baseline_path()
    metadata = {
        "version": "PR27.1",
        "source": "BEFORE_TRAINER_CLICK",
        "jpeg": False,
        "resized": False,
        "cell_size_px": 64,
        "comparison_unit": "INDIVIDUAL_NATIVE_CELL",
        "cluster_authority": False,
        "frame_height": int(frame_shape[0]),
        "frame_width": int(frame_shape[1]),
        "arena_rect": [arena_rect.x, arena_rect.y, arena_rect.width, arena_rect.height],
        "captures": captures,
        "stored_cells": len(store),
    }
    store.save_npz(path, metadata=metadata)
    print(
        f"PR27_NATIVE_BASELINE complete captures={captures} stored={len(store)} "
        f"path={path} frame={frame_shape[1]}x{frame_shape[0]} jpeg=false resize=false"
    )
    return len(store)


def install_native_pre_trainer_baseline_capture() -> None:
    """Bridge the inherited outer trainer search to the new native baseline capture."""

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
    print("PR27 OUTER BRIDGE: native pre-trainer baseline armed")


__all__ = [
    "baseline_path",
    "capture_native_pre_trainer_baseline",
    "install_native_pre_trainer_baseline_capture",
    "reset_native_baseline_capture",
]
