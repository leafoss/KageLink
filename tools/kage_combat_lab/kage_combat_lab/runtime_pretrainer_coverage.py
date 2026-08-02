from __future__ import annotations

import json
import math
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .domain import CELL_SIZE_PX, GridCell


_INSTALLED = False


def _full_player_mask(
    shape: tuple[int, int],
    *,
    cell_bbox: tuple[int, int, int, int],
    player_center: tuple[float, float],
) -> np.ndarray:
    """Mask the complete pre-spawn player only while building the floor baseline.

    No enemy exists during this capture, so a broad silhouette is safe here. It
    is deliberately not reused as the runtime enemy-overlap mask.
    """

    height, width = int(shape[0]), int(shape[1])
    left, top, _, _ = (int(value) for value in cell_bbox)
    center_x = int(round(float(player_center[0]) - float(left)))
    center_y = int(round(float(player_center[1]) - float(top) - 2.0))
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.ellipse(mask, (center_x, center_y), (19, 29), 0.0, 0.0, 360.0, 255, -1)
    cv2.ellipse(mask, (center_x, center_y + 22), (18, 8), 0.0, 0.0, 360.0, 255, -1)
    return cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)


def robust_cell_baseline(samples: list[np.ndarray]) -> tuple[np.ndarray, float]:
    if not samples:
        raise ValueError("PR26_BASELINE_SAMPLES_EMPTY")
    stack = np.stack(samples).astype(np.float32)
    median = np.median(stack, axis=0)
    deviation = float(np.median(np.mean(np.abs(stack - median), axis=(1, 2, 3)))) / 255.0
    return median.astype(np.uint8), deviation


def _player_cell(observer: Any, player_center: tuple[float, float]) -> GridCell:
    origin = getattr(observer, "grid_origin", (0.0, 0.0))
    return GridCell(
        math.floor((float(player_center[0]) - float(origin[0])) / CELL_SIZE_PX),
        math.floor((float(player_center[1]) - float(origin[1])) / CELL_SIZE_PX),
    )


def install_pretrainer_baseline_coverage() -> None:
    """Replace the fragile reset-on-animation capture with a robust median.

    The physical PR26.15 run stored 72/84 cells and left the two spawn/player
    cells without exact baselines. This capture keeps every complete 64px cell,
    removes the full player only during pre-spawn capture, and always retains the
    local D<=3 neighborhood used for combat acquisition.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    from . import pre_ok_baseline as baseline_module

    def robust_capture() -> int:
        duration = max(0.0, float(os.environ.get("KAGE_PR26_PRESPAWN_BASELINE_SECONDS", "0") or 0.0))
        if duration <= 0.0:
            raise RuntimeError("PR26_PREOK_BASELINE_DURATION_MISSING")

        import kage_pilot_live_v03 as live_runtime

        from pc_agent.kage_pilot.entity_observer import decode_jpeg
        from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
        from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
            PersistentBackgroundWaterAwareEntityTracker,
        )
        from pc_agent.kage_pilot.recorder import WindowsGameFrameSource
        from .tile_perception import PR24CombatTilePerception

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
        samples: dict[GridCell, list[np.ndarray]] = defaultdict(list)
        evidence = None
        captures = 0
        last_player_cell: GridCell | None = None

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
            arena_x, arena_y, arena_width, arena_height = (
                int(value) for value in state.arena_rect
            )
            observer.grid_origin_x = (full_origin[0] - float(arena_x)) % CELL_SIZE_PX
            observer.grid_origin_y = (full_origin[1] - float(arena_y)) % CELL_SIZE_PX
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
                arena_y : arena_y + arena_height,
                arena_x : arena_x + arena_width,
            ]
            player_center = (
                float(state.player_center[0]),
                float(state.player_center[1]),
            )
            last_player_cell = _player_cell(observer, player_center)
            for item in evidence.values():
                left, top, width, height = (int(value) for value in item.bbox)
                crop = arena[top : top + height, left : left + width].copy()
                if crop.shape[:2] != (CELL_SIZE_PX, CELL_SIZE_PX):
                    continue
                player_mask = _full_player_mask(
                    crop.shape[:2],
                    cell_bbox=(left, top, width, height),
                    player_center=player_center,
                )
                if np.any(player_mask):
                    crop = cv2.inpaint(crop, player_mask, 3.0, cv2.INPAINT_TELEA)
                samples[item.cell].append(crop)
            captures += 1
            time.sleep(0.04)

        if evidence is None or last_player_cell is None:
            raise RuntimeError("PR26_PREOK_BASELINE_CAPTURE_INCOMPLETE")

        baselines: dict[GridCell, np.ndarray] = {}
        deviations: dict[GridCell, float] = {}
        forced_local: list[GridCell] = []
        minimum_samples = max(3, min(5, captures))
        for cell, values in samples.items():
            if len(values) < minimum_samples:
                continue
            baseline, deviation = robust_cell_baseline(values)
            deviations[cell] = deviation
            local = cell.chebyshev_distance(last_player_cell) <= 3
            if local:
                forced_local.append(cell)
            # Median capture is safe for the static dojo. Local acquisition cells
            # are mandatory even when sprite animation raises temporal deviation.
            if local or deviation <= 0.12:
                baselines[cell] = baseline

        required_local = {
            item.cell
            for item in evidence.values()
            if item.cell.chebyshev_distance(last_player_cell) <= 3
        }
        for cell in sorted(required_local - baselines.keys(), key=lambda value: (value.y, value.x)):
            values = samples.get(cell, [])
            if len(values) >= 3:
                baselines[cell], deviations[cell] = robust_cell_baseline(values)
                forced_local.append(cell)

        missing_local = sorted(
            required_local - baselines.keys(),
            key=lambda value: (value.y, value.x),
        )
        if missing_local:
            raise RuntimeError(
                "PR26_PRETRAINER_LOCAL_BASELINE_MISSING:"
                + ",".join(f"({cell.x},{cell.y})" for cell in missing_local)
            )
        if not baselines:
            raise RuntimeError("PR26_PREOK_BASELINE_EMPTY")

        path: Path = baseline_module._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, np.ndarray] = {
            f"cell_{cell.x}_{cell.y}": image
            for cell, image in baselines.items()
        }
        payload["metadata"] = np.asarray(
            json.dumps(
                {
                    "version": "PR26.16",
                    "cell_size": CELL_SIZE_PX,
                    "captures": captures,
                    "stored": len(baselines),
                    "captured_before_ok": True,
                    "comparison_unit": "INDIVIDUAL_64PX_CELL",
                    "cluster_authority": False,
                    "player_removed_during_capture": "FULL_PRESPAWN_SILHOUETTE",
                    "player_cell": [last_player_cell.x, last_player_cell.y],
                    "required_local_cells": len(required_local),
                    "stored_local_cells": len(required_local & baselines.keys()),
                    "forced_local_cells": [
                        [cell.x, cell.y]
                        for cell in sorted(set(forced_local), key=lambda value: (value.y, value.x))
                    ],
                    "median_deviation": {
                        f"{cell.x},{cell.y}": round(float(value), 6)
                        for cell, value in deviations.items()
                    },
                }
            )
        )
        np.savez_compressed(path, **payload)
        print(
            f"PR26_PREOK_BASELINE complete captures={captures} stored={len(baselines)} "
            f"local={len(required_local & baselines.keys())}/{len(required_local)} "
            f"path={path} dialog=OPEN enemy=NOT_SPAWNED"
        )
        print(
            "PR26_PRETRAINER_BASELINE_COVERAGE "
            f"stored={len(baselines)}/{len(evidence)} "
            f"local_D3={len(required_local & baselines.keys())}/{len(required_local)} "
            "authority=EXACT_CELL_BASELINE"
        )
        return len(baselines)

    baseline_module._capture = robust_capture
    _INSTALLED = True
    print(
        "PR26.16 PRETRAINER COVERAGE: robust median retains every usable 64px cell; "
        "the full player is removed only during pre-spawn capture; local D<=3 exact "
        "baseline coverage is mandatory"
    )


__all__ = [
    "install_pretrainer_baseline_coverage",
    "robust_cell_baseline",
]
