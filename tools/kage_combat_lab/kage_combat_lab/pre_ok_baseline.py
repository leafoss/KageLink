from __future__ import annotations

import json
import math
import os
import time
from collections import deque
from pathlib import Path

import numpy as np

from .domain import CELL_SIZE_PX, GridCell
from .tile_perception import PR24CombatTilePerception, TileClass


_INSTALLED = False
_CAPTURED = False


def _duration() -> float:
    return max(0.0, float(os.environ.get("KAGE_PR26_PRESPAWN_BASELINE_SECONDS", "0") or 0.0))


def _path() -> Path:
    configured = os.environ.get("KAGE_PR26_PREOK_BASELINE_FILE")
    return Path(configured or "kage_pilot_loop_logs/pr26_pre_ok_baseline.npz")


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
    calibration = json.loads(perception.config.calibration_path.read_text(encoding="utf-8"))
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
    state = None
    captures = 0

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
        observer.grid_origin_x = (full_origin[0] - float(arena_x)) % CELL_SIZE_PX
        observer.grid_origin_y = (full_origin[1] - float(arena_y)) % CELL_SIZE_PX
        if now - started < settle:
            time.sleep(0.04)
            continue
        if evidence is None:
            evidence = perception.scan(frame_bgr=frame, state=state, observer=observer)
            print(f"PR26_PREOK_GRID_READY cells={len(evidence)} after_settle={now-started:.2f}s")

        origin = (float(observer.grid_origin_x), float(observer.grid_origin_y))
        player = (float(state.player_center[0]), float(state.player_center[1]))
        player_cell = GridCell(
            math.floor((player[0] - origin[0]) / CELL_SIZE_PX),
            math.floor((player[1] - origin[1]) / CELL_SIZE_PX),
        )
        excluded = {
            GridCell(player_cell.x + dx, player_cell.y + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        }
        arena = frame[arena_y : arena_y + int(state.arena_rect[3]), arena_x : arena_x + int(state.arena_rect[2])]
        for item in evidence.values():
            if item.cell in excluded or item.category in {
                TileClass.DANGER,
                TileClass.PLAYER,
                TileClass.IGNORE_DYNAMIC,
            }:
                continue
            left, top, width, height = item.bbox
            crop = arena[top : top + height, left : left + width].copy()
            if crop.shape[:2] != (CELL_SIZE_PX, CELL_SIZE_PX):
                continue
            old = previous.get(item.cell)
            previous[item.cell] = crop.copy()
            if old is None:
                continue
            temporal = float(
                np.mean(
                    np.abs(
                        crop.astype(np.int16) - old.astype(np.int16)
                    )
                )
            ) / 255.0
            if temporal > 0.012:
                samples.pop(item.cell, None)
                continue
            bucket = samples.setdefault(item.cell, deque(maxlen=5))
            bucket.append(crop)
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
                "version": "PR26.5",
                "cell_size": CELL_SIZE_PX,
                "captures": captures,
                "stored": len(baselines),
                "captured_before_ok": True,
            }
        )
    )
    np.savez_compressed(path, **payload)
    print(
        f"PR26_PREOK_BASELINE complete captures={captures} stored={len(baselines)} "
        f"path={path} dialog=OPEN enemy=NOT_SPAWNED"
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
        f"PR26_PREOK_BASELINE_LOADED stored={count} source=BEFORE_DIALOG_OK "
        "enemy_not_spawned=true"
    )
    return count


def install_pre_ok_baseline_capture() -> None:
    """Wrap the validated OK click so baseline capture occurs before spawning the enemy."""

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
    print("PR26.5 PRE-OK BASELINE HOOK: armed before validated dialog OK click")


__all__ = ["install_pre_ok_baseline_capture", "load_pre_ok_baselines"]
