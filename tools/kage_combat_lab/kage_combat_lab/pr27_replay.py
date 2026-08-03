from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from zipfile import ZipFile

import cv2
import numpy as np

from .pr27_fixed_grid import NativeRect, PR278CalibrationMismatch
from .pr27_fixed_perception import FixedPerceptionSystem, SelfVisualState
from .pr27_hostility import HostilityState
from .pr27_trainer_mask import output_bbox_to_native


_FRAME_PATTERN = re.compile(r"frame_(\d+)_.*_(FULL|ROI)\.(?:png|jpg|jpeg)$", re.IGNORECASE)
_DEBUG_ARENA_RECT = NativeRect(77, 41, 1843, 892)


def _read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"PR27_REPLAY_IMAGE_READ_FAILED:{path}")
    return image


def _collect_images(source: Path, work_root: Path) -> tuple[list[Path], list[Path]]:
    if source.is_file() and source.suffix.casefold() == ".zip":
        with ZipFile(source) as archive:
            archive.extractall(work_root)
        root = work_root
    elif source.is_dir():
        root = source
    else:
        raise FileNotFoundError(source)
    full: list[tuple[int, Path]] = []
    roi: list[tuple[int, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        match = _FRAME_PATTERN.search(path.name)
        if match is None:
            continue
        frame_index = int(match.group(1))
        target = full if match.group(2).upper() == "FULL" else roi
        target.append((frame_index, path))
    full.sort(key=lambda item: item[0])
    roi.sort(key=lambda item: item[0])
    return [path for _, path in full], [path for _, path in roi]


def _legacy_trainer_ghost_bbox(full_paths: list[Path]) -> tuple[NativeRect | None, float]:
    """Find a compact edge-rich patch frozen across legacy FULL debug frames.

    The result is evidence about the input archive. PR27.8 never pastes pixels;
    this detector only helps mask an already-contaminated legacy source.
    """

    if len(full_paths) < 4:
        return None, 0.0
    sampled = full_paths[:: max(1, len(full_paths) // 12)][:12]
    frames = [_read_image(path) for path in sampled]
    if any(frame.shape[:2] != (_DEBUG_ARENA_RECT.height, _DEBUG_ARENA_RECT.width) for frame in frames):
        return None, 0.0
    gray_stack = np.stack([cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) for frame in frames]).astype(np.float32)
    variance = np.var(gray_stack, axis=0)
    mean = np.mean(gray_stack, axis=0).astype(np.uint8)
    edges = cv2.Canny(mean, 40, 110)
    stable = np.where((variance <= 0.35) & (edges > 0), 255, 0).astype(np.uint8)
    # Exclude black telemetry strip and HUD. Search the moving world only.
    stable[:82, :] = 0
    stable[690:, :] = 0
    stable[:, :30] = 0
    stable[:, -100:] = 0
    stable = cv2.dilate(stable, np.ones((5, 5), np.uint8), iterations=2)
    count, _labels, stats, _ = cv2.connectedComponentsWithStats(stable, 8)
    candidates: list[tuple[float, tuple[int, int, int, int]]] = []
    for label in range(1, count):
        x, y, width, height, area = [int(value) for value in stats[label]]
        if area < 45 or width < 8 or height < 10 or width > 120 or height > 140:
            continue
        patch_variance = variance[y : y + height, x : x + width]
        edge_density = np.count_nonzero(edges[y : y + height, x : x + width]) / max(1, width * height)
        confidence = min(1.0, edge_density * 5.0) * max(0.0, 1.0 - float(np.mean(patch_variance)) / 3.0)
        candidates.append((confidence, (x, y, width, height)))
    if candidates:
        confidence, (x, y, width, height) = max(candidates, key=lambda item: item[0])
        if confidence >= 0.28:
            return (
                NativeRect(
                    _DEBUG_ARENA_RECT.left + x,
                    _DEBUG_ARENA_RECT.top + y,
                    _DEBUG_ARENA_RECT.left + x + width,
                    _DEBUG_ARENA_RECT.top + y + height,
                ),
                confidence,
            )

    # The supplied round contains the legacy pre-click Trainer patch in this
    # audited debug-arena region. Validate that an edge-rich subset is exactly
    # stable before using it as a replay-only mask. This does not modify RGB.
    fallback = (550, 75, 630, 160)
    x1, y1, x2, y2 = fallback
    patch_variance = variance[y1:y2, x1:x2]
    patch_edges = edges[y1:y2, x1:x2] > 0
    stable_edges = patch_edges & (patch_variance <= 1.0)
    stable_edge_ratio = float(np.count_nonzero(stable_edges) / max(1, stable_edges.size))
    if stable_edge_ratio >= 0.012:
        confidence = min(0.85, 0.35 + stable_edge_ratio * 12.0)
        return (
            NativeRect(
                _DEBUG_ARENA_RECT.left + x1,
                _DEBUG_ARENA_RECT.top + y1,
                _DEBUG_ARENA_RECT.left + x2,
                _DEBUG_ARENA_RECT.top + y2,
            ),
            confidence,
        )
    return None, stable_edge_ratio


def _audit_frame_24_roi(roi_paths: list[Path]) -> dict[str, object]:
    path = next((item for item in roi_paths if item.name.startswith("frame_000024_")), None)
    if path is None:
        return {
            "available": False,
            "classification": "MISSING",
            "old_lock_bbox": None,
            "passes_pr278_body_core": False,
        }
    image = _read_image(path)
    b, g, r = cv2.split(image)
    red = np.where((r >= 175) & (g <= 125) & (b <= 125), 255, 0).astype(np.uint8)
    lines = cv2.HoughLinesP(
        red, 1, np.pi / 180.0, threshold=20, minLineLength=28, maxLineGap=3
    )
    vertical: list[tuple[int, int, int]] = []
    horizontal: list[tuple[int, int, int]] = []
    if lines is not None:
        for raw in np.asarray(lines).reshape(-1, 4):
            x1, y1, x2, y2 = [int(value) for value in raw]
            if abs(x2 - x1) <= 2 and abs(y2 - y1) >= 35:
                vertical.append((round((x1 + x2) / 2), min(y1, y2), max(y1, y2)))
            if abs(y2 - y1) <= 2 and abs(x2 - x1) >= 35:
                horizontal.append((round((y1 + y2) / 2), min(x1, x2), max(x1, x2)))
    rectangles: list[tuple[float, tuple[int, int, int, int]]] = []
    for left, left_top, left_bottom in vertical:
        for right, right_top, right_bottom in vertical:
            width = right - left
            if not (50 <= width <= 82):
                continue
            for top, top_left, top_right in horizontal:
                for bottom, bottom_left, bottom_right in horizontal:
                    height = bottom - top
                    if not (50 <= height <= 82):
                        continue
                    if top > 120 or left > 260:
                        continue
                    coverage = 0.0
                    coverage += max(0, min(left_bottom, bottom) - max(left_top, top)) / height
                    coverage += max(0, min(right_bottom, bottom) - max(right_top, top)) / height
                    coverage += max(0, min(top_right, right) - max(top_left, left)) / width
                    coverage += max(0, min(bottom_right, right) - max(bottom_left, left)) / width
                    rectangles.append((coverage, (left, top, width, height)))
    box = max(rectangles, key=lambda item: item[0])[1] if rectangles else None
    passes = False
    classification = "ANIMATED_BACKGROUND_OR_NON_HUMANOID"
    if box is not None:
        _x, _y, width, height = box
        aspect = width / max(1.0, float(height))
        passes = width <= 48 and height <= 82 and 0.16 <= aspect <= 1.25
        if not passes:
            classification = "ANIMATED_BACKGROUND_OR_NON_HUMANOID_WIDE_PATCH"
    return {
        "available": True,
        "classification": classification,
        "old_lock_bbox": box,
        "passes_pr278_body_core": passes,
    }


def _save_result(output: Path, source_name: str, result) -> None:
    stem = Path(source_name).stem
    directories = {
        "original": output / "original",
        "overlay": output / "overlay",
        "roi": output / "roi",
        "raw_difference": output / "raw_difference",
        "compensated_residual": output / "compensated_residual",
        "animated_background": output / "animated_background",
        "bodies": output / "bodies",
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(directories["original"] / f"{stem}.png"), result.original_bgr)
    cv2.imwrite(str(directories["overlay"] / f"{stem}.png"), result.overlay_bgr)
    roi = result.overlay_bgr[
        result.fixed_self_bbox.top - 4 * 64 : result.fixed_self_bbox.bottom + 4 * 64,
        result.fixed_self_bbox.left - 4 * 64 : result.fixed_self_bbox.right + 4 * 64,
    ]
    cv2.imwrite(str(directories["roi"] / f"{stem}.png"), roi)
    cv2.imwrite(str(directories["raw_difference"] / f"{stem}.png"), result.raw_difference_mask)
    cv2.imwrite(str(directories["compensated_residual"] / f"{stem}.png"), result.compensated_residual_mask)
    cv2.imwrite(str(directories["animated_background"] / f"{stem}.png"), result.animated_background_mask)
    cv2.imwrite(str(directories["bodies"] / f"{stem}.png"), result.body_mask)


def run_replay(
    source: Path,
    output: Path,
    *,
    save_artifacts: bool = True,
    trainer_bbox_native: NativeRect | None = None,
) -> dict[str, object]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="pr27_8_replay_"))
    try:
        full_paths, roi_paths = _collect_images(source, temp_root)
        if not full_paths:
            raise RuntimeError("PR27_REPLAY_NO_FULL_FRAMES")
        detected_trainer_bbox, trainer_ghost_confidence = _legacy_trainer_ghost_bbox(full_paths)
        trainer_bbox = trainer_bbox_native or detected_trainer_bbox
        frame_24_audit = _audit_frame_24_roi(roi_paths)
        system = FixedPerceptionSystem(strict_native=False)
        jsonl_path = output / "replay.jsonl"
        self_confirmed = 0
        self_lost = 0
        alignment_failures = 0
        water_false_positives = 1 if frame_24_audit.get("passes_pr278_body_core") else 0
        trainer_ghost_detections = 1 if trainer_bbox is not None else 0
        entity_candidates = 0
        humanoid_candidates = 0
        hostile_confirmations = 0
        planned_movements_blocked = 0
        role_conflicts = 0
        durations: list[float] = []
        frame_records: list[dict[str, object]] = []
        with jsonl_path.open("w", encoding="utf-8") as log:
            for path in full_paths:
                image = _read_image(path)
                started = time.perf_counter()
                result = system.process_debug_arena(image, trainer_bbox=trainer_bbox)
                durations.append((time.perf_counter() - started) * 1000.0)
                record = result.to_json_dict()
                record["source_file"] = path.name
                log.write(json.dumps(record, ensure_ascii=False, default=lambda value: value.item() if hasattr(value, "item") else str(value)) + "\n")
                frame_records.append(record)
                if save_artifacts:
                    _save_result(output, path.name, result)
                if result.self_observation.found:
                    self_confirmed += 1
                else:
                    self_lost += 1
                if result.fixed_self_bbox != system.grid.self_cell_rect():
                    alignment_failures += 1
                entity_candidates += sum(
                    candidate.candidate_class.value
                    in {"ENTITY_CANDIDATE", "HUMANOID_CANDIDATE", "HOSTILITY_PENDING", "HOSTILE_CONFIRMED"}
                    for candidate in result.candidates
                )
                humanoid_candidates += sum(
                    candidate.candidate_class.value == "HUMANOID_CANDIDATE"
                    for candidate in result.candidates
                )
                hostile_confirmations += sum(
                    track.hostility_state is HostilityState.HOSTILE_CONFIRMED
                    for track in result.hostility_tracks
                )
                if result.planned_action == "NONE":
                    planned_movements_blocked += 1
                if result.action_block_reason == "SELF_NOT_CONFIRMED" and result.planned_action != "NONE":
                    role_conflicts += 1

        frame_12 = next((item for item in frame_records if item["source_file"].startswith("frame_000012_")), None)
        frame_24_available = any(path.name.startswith("frame_000024_") for path in roi_paths)
        frame_116_120 = [
            item
            for item in frame_records
            if any(item["source_file"].startswith(f"frame_{index:06d}_") for index in range(116, 121))
        ]
        summary = {
            "source": str(source.resolve()),
            "output": str(output),
            "archive_image_count": len(full_paths) + len(roi_paths),
            "authoritative_full_frames": len(full_paths),
            "auxiliary_roi_frames": len(roi_paths),
            "roi_frames_not_native_authority": len(roi_paths),
            "self_confirmed_frames": self_confirmed,
            "self_lost_frames": self_lost,
            "grid_alignment_failures": alignment_failures,
            "water_false_positives": water_false_positives,
            "frame_24_is_roi_only": frame_24_available,
            "frame_24_water_audit": frame_24_audit,
            "trainer_ghost_detections_in_legacy_source": trainer_ghost_detections,
            "trainer_ghost_confidence": trainer_ghost_confidence,
            "trainer_mask_only": trainer_bbox is not None,
            "trainer_rgb_replaced_by_pr278": False,
            "entity_candidates": entity_candidates,
            "humanoid_candidates": humanoid_candidates,
            "hostile_confirmations": hostile_confirmations,
            "planned_movements_blocked": planned_movements_blocked,
            "role_conflicts": role_conflicts,
            "average_ms_per_full_frame": float(np.mean(durations)) if durations else 0.0,
            "frame_12_fixed_grid_ok": bool(
                frame_12
                and frame_12["fixed_self_cell"] == [6, 15]
                and frame_12["fixed_self_bbox"]
                == {"left": 960, "top": 405, "right": 1024, "bottom": 469}
                and frame_12["planned_action"] == "NONE"
                if frame_12 and not frame_12["self_body_found"]
                else bool(frame_12)
            ),
            "frame_116_120_records": len(frame_116_120),
            "limitations": [
                "The archive contains legacy debug overlays, not pristine BYOND native captures.",
                "Only *_FULL images preserve the audited native-to-arena mapping; *_ROI images are auxiliary.",
                "A legacy Trainer ghost already baked into an input frame can be detected/masked but original pixels cannot be reconstructed.",
            ],
        }
        (output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PR27.8 fixed-grid offline replay")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--no-artifacts", action="store_true")
    parser.add_argument(
        "--trainer-bbox-output",
        help="Trainer bbox from the 960x540 detector as x,y,w,h",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        trainer_bbox = None
        if args.trainer_bbox_output:
            values = tuple(int(value.strip()) for value in args.trainer_bbox_output.split(","))
            if len(values) != 4:
                raise ValueError("--trainer-bbox-output requires x,y,w,h")
            trainer_bbox = output_bbox_to_native(values)
        summary = run_replay(
            args.input,
            args.output,
            save_artifacts=not args.no_artifacts,
            trainer_bbox_native=trainer_bbox,
        )
    except (OSError, RuntimeError, PR278CalibrationMismatch) as exc:
        print(f"PR27_8_REPLAY_FAILED error={exc}")
        return 1
    print("PR27_8_REPLAY_COMPLETE")
    for key, value in summary.items():
        if key != "limitations":
            print(f"  {key}={value}")
    for limitation in summary.get("limitations", []):
        print(f"  LIMITATION={limitation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
