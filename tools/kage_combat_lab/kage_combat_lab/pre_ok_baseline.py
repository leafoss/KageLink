from __future__ import annotations

import json
import os
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from .domain import CELL_SIZE_PX, GridCell
from .runtime_cell_change_authority import player_capsule_mask
from .tile_perception import PR24CombatTilePerception, TileClass


_INSTALLED = False
_CAPTURED = False


def _duration() -> float:
    return max(
        0.0,
        float(os.environ.get("KAGE_PR26_PRESPAWN_BASELINE_SECONDS", "0") or 0.0),
    )


def _path() -> Path:
    configured = os.environ.get("KAGE_PR26_PREOK_BASELINE_FILE")
    return Path(configured or "kage_pilot_loop_logs/pr26_pre_ok_baseline.npz")


def reset_pre_ok_baseline_capture() -> None:
    global _CAPTURED
    _CAPTURED = False
    try:
        _path().unlink()
    except OSError:
        pass


def _player_rect(player_center: tuple[float, float]) -> tuple[int, int, int, int]:
    center_x, center_y = (float(value) for value in player_center)
    width, height = 22, 42
    return (
        int(round(center_x - width / 2.0)),
        int(round(center_y - height / 2.0)),
        width,
        height,
    )


def inpaint_player_core_from_cell(
    crop: np.ndarray,
    *,
    cell_bbox: tuple[int, int, int, int],
    player_rect: tuple[int, int, int, int],
) -> tuple[np.ndarray, bool]:
    """Reconstruct only the player core while retaining a 64px cell baseline."""

    left, top, width, height = (int(value) for value in cell_bbox)
    if crop.shape[:2] != (height, width):
        return crop.copy(), False
    mask = player_capsule_mask(
        crop.shape[:2],
        cell_left=left,
        cell_top=top,
        player_rect=player_rect,
    )
    if not np.any(mask):
        return crop.copy(), False
    return cv2.inpaint(crop, mask, 3.0, cv2.INPAINT_TELEA), True


def _capture() -> int:
    duration = _duration()
    if duration <= 0.0:
        raise RuntimeError("PR26_PREOK_BASELINE_DURATION_MISSING")

    import kage_pilot_live_v03 as live_runtime

    from pc_agent.kage_pilot.entity_observer import decode_jpeg
    from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
    from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
        PersistentBackgroundWaterAwareEntityTracker,
    )
    from pc_agent.kage_pilot.recorder import WindowsGameFrameSource

    perception = PR24CombatTilePerception()
    config = V03ObserverConfig(
        background_cell_size=float(CELL_SIZE_PX),
        dynamic_background_enabled=True,
    ).normalized()
    observer = live_runtime.ParticleSafeGridTargetObserver(
        config,
        tile_size=float(CELL_SIZE_PX),
        show_grid=False,
    )
    observer.tracker = PersistentBackgroundWaterAwareEntityTracker(config)
    source = WindowsGameFrameSource()
    calibration = json.loads(
        perception.config.calibration_path.read_text(encoding="utf-8")
    )
    full_origin = (
        float(calibration.get("offset_x_px", 0)),
        float(calibration.get("offset_y_px", 0)),
    )

    started = time.monotonic()
    deadline = started + duration
    settle = min(1.0, duration * 0.25)
    samples: dict[GridCell, deque[np.ndarray]] = {}
    previous: dict[GridCell, np.ndarray] = {}
    evidence = None
    captures = 0
    inpainted_cells: set[GridCell] = set()

    print(
        f"PR26_PREOK_BASELINE start duration={duration:.2f}s "
        "dialog=OPEN enemy=NOT_SPAWNED physical_input=BLOCKED"
    )
    while time.monotonic() < deadline:
        if bool(live_runtime._f12_pressed()):
            raise RuntimeError("F12_STOP")
        now = time.monotonic()
        captured = source.capture()
        frame = decode_jpeg(bytes(captured.jpeg))
        state = observer.process(frame, timestamp=now)
        arena_x, arena_y, _, _ = (int(value) for value in state.arena_rect)
        observer.grid_origin_x = (
            full_origin[0] - float(arena_x)
        ) % CELL_SIZE_PX
        observer.grid_origin_y = (
            full_origin[1] - float(arena_y)
        ) % CELL_SIZE_PX
        if now - started < settle:
            time.sleep(0.04)
            continue
        if evidence is None:
            evidence = perception.scan(
                frame_bgr=frame,
                state=state,
                observer=observer,
            )
            print(
                f"PR26_PREOK_GRID_READY cells={len(evidence)} "
                f"after_settle={now-started:.2f}s"
            )

        arena = frame[
            arena_y : arena_y + int(state.arena_rect[3]),
            arena_x : arena_x + int(state.arena_rect[2]),
        ]
        player_rect = _player_rect(
            (
                float(state.player_center[0]),
                float(state.player_center[1]),
            )
        )
        for item in evidence.values():
            # The old 3x3 exclusion created a permanent blind cross around the
            # player. Every 64px cell is now retained; only the compact player
            # core is reconstructed inside cells it actually intersects.
            if item.category in {
                TileClass.DANGER,
                TileClass.IGNORE_DYNAMIC,
            }:
                continue
            left, top, width, height = (int(value) for value in item.bbox)
            crop = arena[top : top + height, left : left + width].copy()
            if crop.shape[:2] != (CELL_SIZE_PX, CELL_SIZE_PX):
                continue
            clean_crop, inpainted = inpaint_player_core_from_cell(
                crop,
                cell_bbox=(left, top, width, height),
                player_rect=player_rect,
            )
            if inpainted:
                inpainted_cells.add(item.cell)
            old = previous.get(item.cell)
            previous[item.cell] = clean_crop.copy()
            if old is None:
                continue
            temporal = float(
                np.mean(
                    np.abs(clean_crop.astype(np.int16) - old.astype(np.int16))
                )
            ) / 255.0
            if temporal > 0.012:
                samples.pop(item.cell, None)
                continue
            bucket = samples.setdefault(
                item.cell,
                deque(maxlen=5),
            )
            bucket.append(clean_crop)
        captures += 1
        time.sleep(0.05)

    baselines = {
        cell: np.median(np.stack(tuple(bucket)), axis=0).astype(np.uint8)
        for cell, bucket in samples.items()
        if len(bucket) >= 5
    }
    if not baselines:
        raise RuntimeError("PR26_PREOK_BASELINE_EMPTY")
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        f"cell_{cell.x}_{cell.y}": image
        for cell, image in baselines.items()
    }
    payload["metadata"] = np.asarray(
        json.dumps(
            {
                "version": "PR26.13",
                "cell_size": CELL_SIZE_PX,
                "captures": captures,
                "stored": len(baselines),
                "captured_before_ok": True,
                "comparison_unit": "INDIVIDUAL_64PX_CELL",
                "cluster_authority": False,
                "player_core_inpainted_cells": [
                    [cell.x, cell.y]
                    for cell in sorted(
                        inpainted_cells,
                        key=lambda value: (value.y, value.x),
                    )
                ],
            }
        )
    )
    np.savez_compressed(path, **payload)
    print(
        f"PR26_PREOK_BASELINE complete captures={captures} stored={len(baselines)} "
        f"inpainted={len(inpainted_cells)} path={path} "
        "dialog=OPEN enemy=NOT_SPAWNED"
    )
    return len(baselines)


def load_pre_ok_baselines() -> int:
    from . import runtime_tile_perception as runtime_module

    gate = runtime_module.current_hostility_gate()
    if gate is None:
        raise RuntimeError("PR26_PREOK_RUNTIME_NOT_INSTALLED")
    path = _path()
    if not path.is_file():
        raise RuntimeError(f"PR26_PREOK_BASELINE_FILE_MISSING:{path}")
    count = 0
    with np.load(path, allow_pickle=False) as archive:
        for name in archive.files:
            if not name.startswith("cell_"):
                continue
            _, x, y = name.split("_", 2)
            image = archive[name]
            if image.shape[:2] != (CELL_SIZE_PX, CELL_SIZE_PX):
                continue
            gate.map.exact_baselines[GridCell(int(x), int(y))] = image.copy()
            count += 1
    if count <= 0:
        raise RuntimeError("PR26_PREOK_BASELINE_LOAD_EMPTY")
    try:
        path.unlink()
    except OSError:
        pass
    print(
        f"PR26_PREOK_BASELINE_LOADED stored={count} "
        "source=BEFORE_DIALOG_OK enemy_not_spawned=true"
    )
    return count


def install_pre_ok_baseline_capture() -> None:
    """Wrap validated OK so baseline capture occurs before enemy spawn."""

    global _INSTALLED
    if _INSTALLED:
        return

    from pc_agent.kage_pilot import dojo_fight_v03f, dojo_fight_v03i

    def wrap(module) -> None:
        original = module.click_first_option_ok
        if getattr(original, "_pr26_pre_ok_wrapped", False):
            return

        def capture_then_click(match):
            global _CAPTURED
            if not _CAPTURED:
                _capture()
                _CAPTURED = True
            return original(match)

        capture_then_click._pr26_pre_ok_wrapped = True
        module.click_first_option_ok = capture_then_click

    wrap(dojo_fight_v03f)
    wrap(dojo_fight_v03i)
    _INSTALLED = True
    print(
        "PR26.5 PRE-OK BASELINE HOOK: armed before validated dialog OK click"
    )


__all__ = [
    "inpaint_player_core_from_cell",
    "install_pre_ok_baseline_capture",
    "load_pre_ok_baselines",
    "reset_pre_ok_baseline_capture",
]
