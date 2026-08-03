from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import cv2

from .pr27_async_debug import AsyncDebugWriter
from .pr27_fixed_grid import DEFAULT_FIXED_GRID, PR278CalibrationMismatch
from .pr27_fixed_perception import FixedPerceptionSystem
from .pr27_trainer_mask import output_bbox_to_native


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    return max(minimum, int(os.environ.get(name, str(default))))


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _parse_output_bbox(value: str | None):
    if not value:
        return None
    try:
        values = tuple(int(part.strip()) for part in value.split(","))
    except ValueError:
        return None
    if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
        return None
    return output_bbox_to_native(values)


def _debug_paths(log_path: Path) -> dict[str, Path]:
    root = (log_path.parent / "pr27_8_debug" / log_path.stem).resolve()
    return {
        "root": root,
        "original": root / "original",
        "overlay": root / "overlay",
        "roi": root / "roi",
        "raw_difference": root / "raw_difference",
        "compensated_residual": root / "compensated_residual",
        "animated_background": root / "animated_background",
        "bodies": root / "bodies",
    }


def _enqueue_result(writer: AsyncDebugWriter, paths: dict[str, Path], result) -> None:
    stem = f"frame_{result.frame_index:06d}"
    writer.enqueue(result.original_bgr, paths["original"] / f"{stem}.png")
    writer.enqueue(result.overlay_bgr, paths["overlay"] / f"{stem}.png")
    fixed = result.fixed_self_bbox
    radius = 4 * 64
    roi = result.overlay_bgr[
        max(0, fixed.top - radius) : min(result.overlay_bgr.shape[0], fixed.bottom + radius),
        max(0, fixed.left - radius) : min(result.overlay_bgr.shape[1], fixed.right + radius),
    ]
    writer.enqueue(roi, paths["roi"] / f"{stem}.png")
    writer.enqueue(result.raw_difference_mask, paths["raw_difference"] / f"{stem}.png")
    writer.enqueue(result.compensated_residual_mask, paths["compensated_residual"] / f"{stem}.png")
    writer.enqueue(result.animated_background_mask, paths["animated_background"] / f"{stem}.png")
    writer.enqueue(result.body_mask, paths["bodies"] / f"{stem}.png")


def main() -> int:
    import kage_pilot_live_v03 as live_runtime
    import kage_pilot_live_v03k_round as validated_round
    from pc_agent.game_capture import GameCapture

    _previous_name, remaining = validated_round._extract_internal_args(sys.argv[1:])
    args = live_runtime.build_parser().parse_args(remaining)
    mode = os.environ.get("KAGE_PR27_CONTROL_MODE", "PERCEPTION_ONLY").strip().upper()
    if mode != "PERCEPTION_ONLY" or _bool_env("KAGE_PR27_ALLOW_CONTROL", False):
        print("PR27_8_PHYSICAL_DISABLED_PENDING_PERCEPTION_ACCEPTANCE")
        return 2

    log_path = Path(args.log or "kage_pilot_loop_logs/pr27_8_round.jsonl").resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    debug_paths = _debug_paths(log_path)
    for path in debug_paths.values():
        path.mkdir(parents=True, exist_ok=True)
    save_debug = _bool_env("KAGE_PR278_SAVE_DEBUG_FRAMES", True)
    save_every = _int_env("KAGE_PR278_SAVE_EVERY_FRAMES", 1)
    queue_size = _int_env("KAGE_PR278_DEBUG_QUEUE_SIZE", 32, 4)
    writer = AsyncDebugWriter(max_queue=queue_size) if save_debug else None
    target_fps = max(1.0, min(12.0, float(os.environ.get("KAGE_PR278_TARGET_FPS", "6"))))
    interval = 1.0 / target_fps
    trainer_bbox = _parse_output_bbox(os.environ.get("KAGE_PR278_TRAINER_BBOX_OUTPUT"))
    pre_spawn_path = Path(
        os.environ.get(
            "KAGE_PR278_PRE_SPAWN_FILE",
            str(log_path.parent / "pr27_8_pre_spawn_scene.png"),
        )
    ).resolve()

    print("KAGE COMBAT LAB - PR27.8 FIXED SELF CELL PERCEPTION", flush=True)
    print("PR27_8_PHYSICAL_INPUT=DISABLED", flush=True)
    print("PR27_8_GRID native=1920x1037 cell=64 offset=(0,21) self_abs=(6,15)", flush=True)
    print("PR27_8_FIXED_SELF_BBOX=[960,405,1024,469)", flush=True)
    print(f"PR27_LOG_PATH={log_path}", flush=True)
    print(f"PR27_DEBUG_PATH={debug_paths['root']}", flush=True)
    print(f"PR27_ORIGINAL_FRAME_PATH={debug_paths['original']}", flush=True)
    print(f"PR27_OVERLAY_FRAME_PATH={debug_paths['overlay']}", flush=True)
    print(f"PR27_8_PRE_SPAWN_PATH={pre_spawn_path}", flush=True)
    print(f"PR27_8_TRAINER_BBOX_NATIVE={trainer_bbox}", flush=True)

    system = FixedPerceptionSystem(strict_native=True)
    if pre_spawn_path.exists():
        pre_spawn = cv2.imread(str(pre_spawn_path), cv2.IMREAD_COLOR)
        if pre_spawn is not None:
            try:
                DEFAULT_FIXED_GRID.validate_native_shape(pre_spawn.shape)
                system.self_detector.observe(pre_spawn)
                system.previous_frame = pre_spawn.copy()
                camera_mask = system._camera_exclusion_mask(pre_spawn, trainer_bbox)
                system.camera.observe(pre_spawn, exclusion_mask=camera_mask)
                print("PR27_8_PRE_SPAWN_LOADED=true", flush=True)
            except PR278CalibrationMismatch as exc:
                print(f"PR27_8_PRE_SPAWN_REJECTED error={exc}", flush=True)

    capture = GameCapture()
    started = time.monotonic()
    frames = 0
    self_confirmed = 0
    self_lost = 0
    blocked = 0
    failure: Exception | None = None
    log_handle = log_path.open("w", encoding="utf-8", buffering=65536)
    try:
        while time.monotonic() - started < max(1.0, float(args.seconds)):
            loop_started = time.monotonic()
            if bool(live_runtime._f12_pressed()):
                print("PR27_8_F12_STOP", flush=True)
                break
            native = capture.capture_native()
            try:
                result = system.process_native(native.bgr, trainer_bbox=trainer_bbox)
            except PR278CalibrationMismatch as exc:
                mismatch_path = debug_paths["root"] / "calibration_mismatch.png"
                cv2.imwrite(str(mismatch_path), native.bgr)
                print(f"PR27_CALIBRATION_MISMATCH evidence={mismatch_path} error={exc}", flush=True)
                return 3
            payload = result.to_json_dict()
            log_handle.write(json.dumps(payload, ensure_ascii=False, default=lambda value: value.item() if hasattr(value, "item") else str(value)) + "\n")
            log_handle.flush()
            if writer is not None and frames % save_every == 0:
                _enqueue_result(writer, debug_paths, result)
            self_confirmed += int(result.self_observation.found)
            self_lost += int(not result.self_observation.found)
            blocked += int(result.action_block_reason != "PERCEPTION_ONLY_NO_PHYSICAL_INPUT")
            if frames == 0 or frames % max(1, round(target_fps)) == 0:
                print(
                    "PR27_8_FRAME "
                    f"frame={frames:05d} self={result.self_observation.state.value} "
                    f"self_found={result.self_observation.found} "
                    f"camera=({result.camera_motion.dx_px:.1f},{result.camera_motion.dy_px:.1f}) "
                    f"camera_conf={result.camera_motion.confidence:.3f} "
                    f"candidates={len(result.candidates)} "
                    f"hostiles={sum(track.hostility_state.value == 'HOSTILE_CONFIRMED' for track in result.hostility_tracks)} "
                    f"planned={result.planned_action} blocked={result.action_block_reason}",
                    flush=True,
                )
            frames += 1
            remaining = interval - (time.monotonic() - loop_started)
            if remaining > 0:
                time.sleep(remaining)
    except Exception as exc:
        failure = exc
        print(f"PR27_8_RUNTIME_FAILED type={type(exc).__name__} error={exc}", flush=True)
    finally:
        log_handle.close()
        capture.close()
        if writer is not None:
            writer.close(timeout=8.0)
        saved = 0 if writer is None else writer.saved_frames
        dropped = 0 if writer is None else writer.dropped_frames
        print(f"PR27_LOG_SAVED={log_path.exists()}", flush=True)
        print(f"PR27_DEBUG_SAVED_FRAMES={saved}", flush=True)
        print(f"PR27_DEBUG_DROPPED_FRAMES={dropped}", flush=True)
        print(f"PR27_DEBUG_PATH={debug_paths['root']}", flush=True)

    if failure is not None:
        return 1
    print(
        f"PR27_8_PERCEPTION_COMPLETE frames={frames} self_confirmed={self_confirmed} "
        f"self_lost={self_lost} planned_actions_blocked={blocked}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
