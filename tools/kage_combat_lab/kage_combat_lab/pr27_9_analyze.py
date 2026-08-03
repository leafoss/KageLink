from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"PR27_9_JSONL_INVALID line={line_number}: {exc}") from exc
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def analyze_rows(rows: list[dict[str, object]]) -> tuple[dict[str, object], dict[str, list[dict[str, object]]], list[str]]:
    self_rows: list[dict[str, object]] = []
    camera_rows: list[dict[str, object]] = []
    trainer_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    track_rows: list[dict[str, object]] = []
    noise_rows: list[dict[str, object]] = []
    flags: list[str] = []
    rejection_counts: Counter[str] = Counter()
    track_frames: dict[int, list[int]] = defaultdict(list)
    total_raw = total_gated = self_preserved = self_lost = 0
    camera_outliers = candidate_bursts = trainer_blind_violations = 0

    for row in rows:
        frame = int(row.get("frame_index", 0))
        self_data = row.get("self") if isinstance(row.get("self"), dict) else {}
        self_state = str(row.get("self_state", ""))
        self_found = bool(row.get("self_body_found", False))
        self_score = float(row.get("self_template_score", 0.0) or 0.0)
        self_preserved += int(self_found)
        self_lost += int(not self_found)
        self_rows.append({
            "frame": frame, "found": self_found, "state": self_state, "score": self_score,
            "template_id": self_data.get("matched_template_id"),
            "missing_frames": self_data.get("missing_frames", 0),
            "protected_mask_pixels": self_data.get("protected_mask_pixels", 0),
        })
        if not self_found:
            flags.append(f"frame {frame:06d}: SELF not confirmed ({self_state}, score={self_score:.3f})")
        elif 0.28 <= self_score < 0.40:
            flags.append(f"frame {frame:06d}: SELF preserved near threshold (score={self_score:.3f})")

        camera = row.get("camera") if isinstance(row.get("camera"), dict) else {}
        rejection = camera.get("rejection_reason")
        raw_dx = float(camera.get("phase_dx", row.get("camera_dx", 0.0)) or 0.0)
        raw_dy = float(camera.get("phase_dy", row.get("camera_dy", 0.0)) or 0.0)
        accepted_dx = float(camera.get("accepted_dx", row.get("camera_dx", 0.0)) or 0.0)
        accepted_dy = float(camera.get("accepted_dy", row.get("camera_dy", 0.0)) or 0.0)
        camera_rows.append({
            "frame": frame, "phase_dx": raw_dx, "phase_dy": raw_dy,
            "flow_dx": camera.get("flow_dx", 0.0), "flow_dy": camera.get("flow_dy", 0.0),
            "accepted_dx": accepted_dx, "accepted_dy": accepted_dy,
            "accepted": camera.get("accepted", False), "rejection_reason": rejection,
            "confidence": row.get("camera_confidence", 0.0),
        })
        if rejection == "CAMERA_SHIFT_REJECTED_STATIONARY_MODE":
            camera_outliers += 1
            flags.append(f"frame {frame:06d}: stationary camera outlier rejected raw=({raw_dx:.1f},{raw_dy:.1f})")
        if (accepted_dx * accepted_dx + accepted_dy * accepted_dy) ** 0.5 > 2.0:
            flags.append(f"frame {frame:06d}: ACCEPTED camera shift above 2 px")

        trainer = row.get("trainer") if isinstance(row.get("trainer"), dict) else {}
        blind = int(trainer.get("entity_detection_mask_pixels", 0) or 0)
        trainer_blind_violations += int(blind > 0)
        trainer_rows.append({
            "frame": frame, "state": trainer.get("state"),
            "identity_score": trainer.get("identity_score", 0.0),
            "observed_bbox": json.dumps(trainer.get("observed_bbox"), ensure_ascii=False),
            "predicted_bbox": json.dumps(trainer.get("predicted_bbox"), ensure_ascii=False),
            "candidate_vetoes": json.dumps(trainer.get("candidate_vetoes", []), ensure_ascii=False),
            "blind_pixels": blind,
        })
        if blind > 0:
            flags.append(f"frame {frame:06d}: Trainer blind mask violation pixels={blind}")

        raw_active = int(row.get("raw_active_pixels", 0) or 0)
        gated_active = int(row.get("noise_gated_active_pixels", 0) or 0)
        total_raw += raw_active
        total_gated += gated_active
        for cell in row.get("cell_activity", []) if isinstance(row.get("cell_activity"), list) else []:
            if isinstance(cell, dict):
                noise_rows.append({
                    "frame": frame, "relative_cell": json.dumps(cell.get("relative_cell")),
                    "raw_changed_ratio": cell.get("raw_changed_ratio", 0.0),
                    "effective_threshold": cell.get("effective_threshold", 0.0),
                    "noise_probability": cell.get("noise_probability", 0.0),
                    "animated_probability": cell.get("animated_probability", 0.0),
                    "passed": cell.get("passed_new_candidate_gate", False),
                    "override": cell.get("override_reason"),
                })

        candidates = row.get("entity_candidates", []) if isinstance(row.get("entity_candidates"), list) else []
        if len(candidates) >= 20:
            candidate_bursts += 1
            flags.append(f"frame {frame:06d}: candidate/component burst count={len(candidates)}")
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            reason = str(candidate.get("rejection_reason") or "ACCEPTED_BODY_CORE")
            rejection_counts[reason] += 1
            candidate_rows.append({
                "frame": frame, "candidate_id": candidate.get("candidate_id"),
                "class": candidate.get("class"),
                "relative_cell": json.dumps(candidate.get("relative_cell")),
                "entity_confidence": candidate.get("entity_confidence", 0.0),
                "humanoid_confidence": candidate.get("humanoid_confidence", 0.0),
                "rejection_reason": candidate.get("rejection_reason"),
            })

        for track in row.get("object_tracks", []) if isinstance(row.get("object_tracks"), list) else []:
            if not isinstance(track, dict):
                continue
            track_id = int(track.get("track_id", -1))
            track_frames[track_id].append(frame)
            track_rows.append({
                "frame": frame, "track_id": track_id, "state": track.get("state"),
                "visible": track.get("visible"), "confirmed": track.get("confirmed"),
                "source": track.get("source"), "relative_cell": json.dumps(track.get("relative_cell")),
                "observations": track.get("observations", 0), "missing_frames": track.get("missing_frames", 0),
                "trainer_score": track.get("trainer_score", 0.0), "self_score": track.get("self_score", 0.0),
                "lineage": json.dumps(track.get("lineage", [])),
            })

    noise_removed = max(0, total_raw - total_gated)
    summary = {
        "frames": len(rows), "self_preserved_frames": self_preserved,
        "self_lost_frames": self_lost,
        "self_preserved_ratio": 0.0 if not rows else self_preserved / len(rows),
        "raw_active_pixels": total_raw, "noise_gated_active_pixels": total_gated,
        "noise_removed_pixels": noise_removed,
        "noise_removed_ratio": 0.0 if total_raw == 0 else noise_removed / total_raw,
        "camera_stationary_outliers_rejected": camera_outliers,
        "candidate_burst_frames": candidate_bursts,
        "trainer_blind_mask_violations": trainer_blind_violations,
        "logical_object_tracks": len(track_frames),
        "rejection_reason_counts": dict(rejection_counts),
    }
    tables = {"self": self_rows, "camera": camera_rows, "trainer": trainer_rows, "candidates": candidate_rows, "tracks": track_rows, "noise": noise_rows}
    return summary, tables, flags


def write_report(output: Path, summary: dict[str, object], tables: dict[str, list[dict[str, object]]], flags: list[str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "flagged_frames.txt").write_text("\n".join(flags) + ("\n" if flags else ""), encoding="utf-8")
    _write_csv(output / "self_timeline.csv", ["frame", "found", "state", "score", "template_id", "missing_frames", "protected_mask_pixels"], tables["self"])
    _write_csv(output / "camera_timeline.csv", ["frame", "phase_dx", "phase_dy", "flow_dx", "flow_dy", "accepted_dx", "accepted_dy", "accepted", "rejection_reason", "confidence"], tables["camera"])
    _write_csv(output / "trainer_timeline.csv", ["frame", "state", "identity_score", "observed_bbox", "predicted_bbox", "candidate_vetoes", "blind_pixels"], tables["trainer"])
    _write_csv(output / "candidate_timeline.csv", ["frame", "candidate_id", "class", "relative_cell", "entity_confidence", "humanoid_confidence", "rejection_reason"], tables["candidates"])
    _write_csv(output / "track_lineage.csv", ["frame", "track_id", "state", "visible", "confirmed", "source", "relative_cell", "observations", "missing_frames", "trainer_score", "self_score", "lineage"], tables["tracks"])
    _write_csv(output / "noise_by_cell.csv", ["frame", "relative_cell", "raw_changed_ratio", "effective_threshold", "noise_probability", "animated_probability", "passed", "override"], tables["noise"])
    lines = [
        "# PR27.9 perception analysis", "", f"- Frames: {summary['frames']}",
        f"- SELF preserved ratio: {float(summary['self_preserved_ratio']) * 100.0:.2f}%",
        f"- Noise removed: {float(summary['noise_removed_ratio']) * 100.0:.2f}%",
        f"- Stationary camera outliers rejected: {summary['camera_stationary_outliers_rejected']}",
        f"- Trainer blind-mask violations: {summary['trainer_blind_mask_violations']}",
        f"- Logical object tracks: {summary['logical_object_tracks']}", "", "## Rejection reasons", "",
    ]
    for reason, count in sorted(dict(summary["rejection_reason_counts"]).items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {reason}: {count}")
    lines.extend(["", "## Flagged frames", ""])
    lines.extend(f"- {flag}" for flag in flags[:200])
    (output / "analysis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze PR27.9 perception JSONL")
    parser.add_argument("--jsonl", required=True, type=Path)
    parser.add_argument("--debug-dir", type=Path, default=None)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = _read_jsonl(args.jsonl)
    summary, tables, flags = analyze_rows(rows)
    write_report(args.output, summary, tables, flags)
    print(f"PR27_9_ANALYSIS_COMPLETE frames={len(rows)} output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
