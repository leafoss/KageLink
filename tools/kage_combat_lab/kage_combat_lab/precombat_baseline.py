from __future__ import annotations

import json
import math
import os
import time
from typing import Iterable

from .domain import CELL_SIZE_PX, CandidateObservation, GridCell, ObservationKind


def _baseline_seconds() -> float:
    raw = os.environ.get("KAGE_PR26_PRESPAWN_BASELINE_SECONDS", "0")
    return max(0.0, float(raw or 0.0))


def prime_pre_spawn_baselines(argv: Iterable[str]) -> int:
    """Use the former outer spawn wait as a no-input baseline capture window."""

    duration = _baseline_seconds()
    if duration <= 0.0:
        print("PR26_PRESPAWN_BASELINE skipped duration=0")
        return 0

    import kage_pilot_live_v03 as live_runtime

    from pc_agent.kage_pilot.entity_observer import decode_jpeg
    from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
    from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
        PersistentBackgroundWaterAwareEntityTracker,
    )
    from pc_agent.kage_pilot.recorder import WindowsGameFrameSource

    from . import runtime_tile_perception as runtime_module

    gate = runtime_module.current_hostility_gate()
    perception = getattr(runtime_module, "_RUNTIME", None)
    if gate is None or perception is None:
        raise RuntimeError("PR26_PRESPAWN_RUNTIME_NOT_INSTALLED")

    args = live_runtime.build_parser().parse_args(list(argv))
    observer_config = V03ObserverConfig(
        player_x=args.player_x,
        player_y=args.player_y,
        player_exclusion_radius=max(args.player_box_width, args.player_box_height) / 2.0,
        player_box_width=args.player_box_width,
        player_box_height=args.player_box_height,
        enemy_threshold=args.target_acquire,
        target_acquire_threshold=args.target_acquire,
        target_keep_threshold=args.target_keep,
        track_ttl_seconds=max(0.5, float(args.track_ttl)),
        track_match_distance=max(20.0, float(args.match_distance)),
        dynamic_background_enabled=True,
        background_similarity=args.background_similarity,
        background_min_dense_hits=args.background_min_hits,
        background_min_age=args.background_min_age,
        background_cell_size=float(CELL_SIZE_PX),
        reacquire_ttl=max(6.0, float(args.reacquire_ttl)),
        reacquire_distance=max(128.0, float(args.reacquire_distance)),
        reacquire_similarity=args.reacquire_similarity,
    ).normalized()
    observer = live_runtime.ParticleSafeGridTargetObserver(
        observer_config,
        tile_size=float(CELL_SIZE_PX),
        contact_lock_seconds=max(4.0, float(args.contact_lock_seconds)),
        show_grid=False,
        contact_confirm_frames=max(2, int(args.contact_confirm_frames)),
    )
    observer.tracker = PersistentBackgroundWaterAwareEntityTracker(observer_config)
    source = WindowsGameFrameSource()

    calibration = json.loads(
        perception.config.calibration_path.read_text(encoding="utf-8")
    )
    full_origin = (
        float(calibration.get("offset_x_px", 0)),
        float(calibration.get("offset_y_px", 0)),
    )
    settle_seconds = min(1.5, duration * 0.35)
    started = time.monotonic()
    deadline = started + duration
    evidence = None
    captures = 0
    baseline_events = 0

    print(
        f"PR26_PRESPAWN_BASELINE start duration={duration:.2f}s "
        "physical_input=BLOCKED"
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
        if now - started < settle_seconds:
            time.sleep(0.05)
            continue
        if evidence is None:
            evidence = perception.scan(
                frame_bgr=frame,
                state=state,
                observer=observer,
            )
            print(
                f"PR26_PRESPAWN_GRID_READY cells={len(evidence)} "
                f"after_settle={now - started:.2f}s"
            )

        origin = (float(observer.grid_origin_x), float(observer.grid_origin_y))
        player = (float(state.player_center[0]), float(state.player_center[1]))
        player_cell = GridCell(
            math.floor((player[0] - origin[0]) / CELL_SIZE_PX),
            math.floor((player[1] - origin[1]) / CELL_SIZE_PX),
        )
        excluded = frozenset(
            GridCell(player_cell.x + dx, player_cell.y + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        )
        player_mask = CandidateObservation(
            track_id=0,
            anchor_cell=player_cell,
            kind=ObservationKind.CONTAMINATED_ACTIVITY,
            visible=True,
            body_like=False,
            confidence=1.0,
            cells_touched=excluded,
            foot_point=player,
            background_probability=1.0,
        )
        _, ready = gate.map.observe(
            frame=frame,
            state=state,
            candidates=(player_mask,),
            evidence=evidence,
            danger_fresh=True,
        )
        for cell in ready:
            baseline_events += 1
            print(
                f"PR26_PRESPAWN_BASELINE_READY cell={cell} "
                "diff_source=EXACT_CELL_BASELINE"
            )
        captures += 1
        time.sleep(0.08)

    stored = len(gate.map.exact_baselines)
    print(
        f"PR26_PRESPAWN_BASELINE complete captures={captures} "
        f"new={baseline_events} stored={stored} physical_input=BLOCKED"
    )
    return stored


__all__ = ["prime_pre_spawn_baselines"]
