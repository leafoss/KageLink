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
    root = (log_path.parent / "pr27_9_debug" / log_path.stem).resolve()
    names = (
        "original",
        "overlay",
        "roi",
        "raw_difference",
        "noise_probability",
        "noise_gated_difference",
        "camera_static_terrain",
        "compensated_residual",
        "animated_background",
        "object_proposals",
        "body_core",
        "self_protected_mask",
        "trainer_identity_matches",
    )
    paths = {name: root / name for name in names}
    paths["root"] = root
    return paths


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
    if result.noise_gate is not None:
        writer.enqueue(result.noise_gate.noise_probability_mask, paths["noise_probability"] / f"{stem}.png")
        writer.enqueue(result.noise_gate.proposal_mask, paths["noise_gated_difference"] / f"{stem}.png")
    if result.camera_static_terrain_mask is not None:
        writer.enqueue(result.camera_static_terrain_mask, paths["camera_static_terrain"] / f"{stem}.png")
    writer.enqueue(result.compensated_residual_mask, paths["compensated_residual"] / f"{stem}.png")
    writer.enqueue(result.animated_background_mask, paths["animated_background"] / f"{stem}.png")
    if result.object_proposal_mask is not None:
        writer.enqueue(result.object_proposal_mask, paths["object_proposals"] / f"{stem}.png")
    writer.enqueue(result.body_mask, paths["body_core"] / f"{stem}.png")
    if result.self_protected_mask is not None:
        writer.enqueue(result.self_protected_mask, paths["self_protected_mask"] / f"{stem}.png")
    if result.trainer_identity_match_mask is not None:
        writer.enqueue(result.trainer_identity_match_mask, paths["trainer_identity_matches"] / f"{stem}.png")


def main() -> int:
    import kage_pilot_live_v03 as live_runtime
    import kage_pilot_live_v03k_round as validated_round
    from pc_agent.game_capture import GameCapture

    _previous_name, remaining = validated_round._extract_internal_args(sys.argv[1:])
    args = live_runtime.build_parser().parse_args(remaining)
    mode = os.environ.get("KAGE_PR27_CONTROL_MODE", "PERCEPTION_ONLY").strip().upper()
    if mode != "PERCEPTION_ONLY" or _bool_env("KAGE_PR27_ALLOW_CONTROL", False):
        print("PR27_9_PHYSICAL_DISABLED_PENDING_PERCEPTION_ACCEPTANCE")
        return 2

    log_path = Path(args.log or "kage_pilot_loop_logs/pr27_9_round.jsonl").resolve()
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
    trainer_score = float(os.environ.get("KAGE_PR279_TRAINER_SCORE", "0"))
    trainer_identity_path = Path(
        os.environ.get(
            "KAGE_PR279_TRAINER_IDENTITY_SCENE",
            str(log_path.parent / "pr27_9_trainer_pre_click.png"),
        )
    ).resolve()
    pre_spawn_path = Path(
        os.environ.get(
            "KAGE_PR278_PRE_SPAWN_FILE",
            str(log_path.parent / "pr27_9_pre_spawn_scene.png"),
        )
    ).resolve()

    print("KAGE COMBAT LAB - PR27.9 NOISE-AWARE OBJECT PERCEPTION", flush=True)
    print("PR27_9_PHYSICAL_INPUT=DISABLED", flush=True)
    print("PR27_9_GRID native=1920x1037 cell=64 offset=(0,21) self_abs=(6,15)", flush=True)
    print("PR27_9_FIXED_SELF_BBOX=[960,405,1024,469)", flush=True)
    print("PR27_9_NEW_CANDIDATE_GATE=0.12", flush=True)
    print(f"PR27_LOG_PATH={log_path}", flush=True)
    print(f"PR27_DEBUG_PATH={debug_paths['root']}", flush=True)
    print(f"PR27_ORIGINAL_FRAME_PATH={debug_paths['original']}", flush=True)
    print(f"PR27_OVERLAY_FRAME_PATH={debug_paths['overlay']}", flush=True)
    print(f"PR27_9_PRE_SPAWN_PATH={pre_spawn_path}", flush=True)
    print(f"PR27_9_TRAINER_IDENTITY_PATH={trainer_identity_path}", flush=True)
    print(f"PR27_9_TRAINER_BBOX_NATIVE={trainer_bbox}", flush=True)

    system = FixedPerceptionSystem(strict_native=True)
    if trainer_bbox is not None and trainer_identity_path.exists():
        identity_frame = cv2.imread(str(trainer_identity_path), cv2.IMREAD_COLOR)
        if identity_frame is not None:
            try:
                DEFAULT_FIXED_GRID.validate_native_shape(identity_frame.shape)
                system.set_trainer_identity(
                    identity_frame,
                    trainer_bbox,
                    detector_score=trainer_score,
                    detector_mode="PRE_CLICK_DETECTOR_CAPTURE",
                )
                print("PR27_9_TRAINER_IDENTITY_READY=true", flush=True)
            except (PR278CalibrationMismatch, ValueError) as exc:
                print(f"PR27_9_TRAINER_IDENTITY_REJECTED error={exc}", flush=True)
    else:
        print("PR27_9_TRAINER_IDENTITY_READY=false reason=PRE_CLICK_EVIDENCE_UNAVAILABLE", flush=True)

    if pre_spawn_path.exists():
        pre_spawn = cv2.imread(str(pre_spawn_path), cv2.IMREAD_COLOR)
        if pre_spawn is not None:
            try:
                DEFAULT_FIXED_GRID.validate_native_shape(pre_spawn.shape)
                system.set_pre_spawn(pre_spawn)
                system.self_detector.observe(pre_spawn)
                system.previous_frame = pre_spawn.copy()
                system.camera.observe(pre_spawn, stationary_mode=True)
                print("PR27_9_PRE_SPAWN_LOADED=true", flush=True)
            except PR278CalibrationMismatch as exc:
                print(f"PR27_9_PRE_SPAWN_REJECTED error={exc}", flush=True)

    capture = GameCapture()
    started = time.monotonic()
    frames = 0
    self_preserved = 0
    self_lost = 0
    blocked = 0
    failure: Exception | None = None
    total_raw_pixels = 0
    total_gated_pixels = 0
    camera_outliers = 0
    max_body_tracks = 0
    max_opponent_tracks = 0
    log_handle = log_path.open("w", encoding="utf-8", buffering=65536)
    try:
        while time.monotonic() - started < max(1.0, float(args.seconds)):
            loop_started = time.monotonic()
            if bool(live_runtime._f12_pressed()):
                print("PR27_9_F12_STOP", flush=True)
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
            self_preserved += int(result.self_observation.found)
            self_lost += int(not result.self_observation.found)
            blocked += int(result.action_block_reason != "PERCEPTION_ONLY_NO_PHYSICAL_INPUT")
            total_raw_pixels += int(payload.get("raw_active_pixels", 0))
            total_gated_pixels += int(payload.get("noise_gated_active_pixels", 0))
            camera_outliers += int(result.camera_motion.shift_rejection_reason == "CAMERA_SHIFT_REJECTED_STATIONARY_MODE")
            body_tracks = sum(track.confirmed for track in result.object_tracks)
            opponent_tracks = sum(
                track.hostility_state.value in {"OPPONENT_CANDIDATE", "HOSTILITY_PENDING", "HOSTILE_CONFIRMED"}
                for track in result.hostility_tracks
            )
            max_body_tracks = max(max_body_tracks, body_tracks)
            max_opponent_tracks = max(max_opponent_tracks, opponent_tracks)
            if frames == 0 or frames % max(1, round(target_fps)) == 0:
                rejected = payload.get("rejection_reason_counts", {})
                print(
                    "PR27_9_FRAME "
                    f"frame={frames:05d} self={result.self_observation.state.value} "
                    f"self_score={result.self_observation.template_score:.3f} "
                    f"camera_raw=({result.camera_motion.phase_dx:.1f},{result.camera_motion.phase_dy:.1f}) "
                    f"camera_accepted=({result.camera_motion.dx_px:.1f},{result.camera_motion.dy_px:.1f}) "
                    f"camera_rejection={result.camera_motion.shift_rejection_reason or '-'} "
                    f"raw_pixels={payload.get('raw_active_pixels', 0)} "
                    f"gated_pixels={payload.get('noise_gated_active_pixels', 0)} "
                    f"raw_components={payload.get('raw_components', 0)} "
                    f"body_tracks={body_tracks} opponents={opponent_tracks} "
                    f"hostiles={sum(track.hostility_state.value == 'HOSTILE_CONFIRMED' for track in result.hostility_tracks)} "
                    f"trainer={result.trainer_evidence.state.value} blind_pixels=0 "
                    f"rejections={rejected} planned={result.planned_action} blocked={result.action_block_reason}",
                    flush=True,
                )
            frames += 1
            remaining_sleep = interval - (time.monotonic() - loop_started)
            if remaining_sleep > 0:
                time.sleep(remaining_sleep)
    except Exception as exc:
        failure = exc
        print(f"PR27_9_RUNTIME_FAILED type={type(exc).__name__} error={exc}", flush=True)
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
    removed_ratio = 0.0 if total_raw_pixels == 0 else (total_raw_pixels - total_gated_pixels) / total_raw_pixels
    print(
        f"PR27_9_PERCEPTION_COMPLETE frames={frames} self_preserved={self_preserved} "
        f"self_lost={self_lost} noise_removed={removed_ratio:.3f} "
        f"camera_outliers_rejected={camera_outliers} max_body_tracks={max_body_tracks} "
        f"max_opponent_tracks={max_opponent_tracks} planned_actions_blocked={blocked}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
