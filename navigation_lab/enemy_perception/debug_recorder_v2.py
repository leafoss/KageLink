from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .async_debug_writer import AsyncDebugWriter
from .models import FramePerception


class DebugRecorder:
    REQUIRED_IMAGES = (
        "00_raw_window.png", "01_grid_overlay.png", "02_background_composite.png",
        "03_difference_composite.png", "04_mask_composite.png", "05_components_overlay.png",
        "06_entities_overlay.png", "07_tracking_overlay.png", "08_hostility_overlay.png",
    )
    CRITICAL_EVENTS = {
        "player_source_changed", "player_lost", "semantic_entity_detected",
        "residual_entity_detected", "entity_created", "entity_moved",
        "distance_decreased", "hostility_state_changed", "attack_recommended",
        "background_cluster_created", "structural_mismatch", "processing_error",
    }

    def __init__(self, root: Path, session_id: str, enabled: bool = True,
                 max_frames: int | None = None, debug_mode: str = "full",
                 debug_stride: int = 5, async_writes: bool = False) -> None:
        mode = str(debug_mode).strip().lower()
        if mode not in {"full", "balanced", "off"}:
            raise ValueError("debug_mode must be Full, Balanced or Off")
        if not enabled:
            mode = "off"
        self.debug_mode = mode
        self.enabled = mode != "off"
        self.session_id = session_id
        self.debug_root = Path(root)
        self.session_root = self.debug_root / session_id
        self.frames_root = self.session_root / "frames"
        self.max_frames = max_frames
        self.debug_stride = max(1, int(debug_stride))
        self.started_at = datetime.now(timezone.utc)
        self.writer = AsyncDebugWriter() if self.enabled and async_writes else None
        self.stats: dict[str, Any] = {
            "total_frames": 0, "settled_frames": 0, "moving_frames": 0,
            "frames_without_player": 0, "frames_without_background_reference": 0,
            "overlays_detected": 0, "entities_created": 0, "tracks_created": 0,
            "semantic_candidates": 0, "residual_candidates": 0,
            "frames_with_diagnostic_difference": 0, "mobile_entities": 0,
            "unknown_entities": 0, "possible_enemies": 0, "probable_enemies": 0,
            "confirmed_enemies": 0, "processing_errors": 0,
            "full_debug_frames": 0, "processing_times": [],
        }
        if self.enabled:
            self.frames_root.mkdir(parents=True, exist_ok=True)
            (self.session_root / "errors.log").touch(exist_ok=True)
            (self.debug_root / "LATEST_SESSION.txt").write_text(str(self.session_root), encoding="utf-8")
            (self.session_root / "OPEN_THIS_FOLDER.txt").write_text(str(self.session_root), encoding="utf-8")
            self._atomic_json(self.session_root / "session.json", {
                "session_id": session_id, "status": "running", "debug_enabled": True,
                "debug_mode": self.debug_mode, "debug_stride": self.debug_stride,
                "session_path": str(self.session_root), "started_at": self.started_at.isoformat(),
            })

    def _requires_full_images(self, result: FramePerception) -> bool:
        return self.debug_mode == "full" or result.frame_index % self.debug_stride == 0 or any(
            event.get("event") in self.CRITICAL_EVENTS for event in result.events
        )

    @staticmethod
    def _write_images(frame_dir: Path, entities_dir: Path, names: tuple[str, ...],
                      images: dict[str, Any], entities: list[Any]) -> None:
        import cv2
        import numpy as np
        raw = images.get("00_raw_window.png")
        fallback = np.zeros((64, 64, 3), np.uint8) if raw is None else raw
        for name in names:
            image = images.get(name, fallback)
            if image is None or not cv2.imwrite(str(frame_dir / name), image):
                raise OSError(f"failed_to_write:{name}")
        for entity in entities:
            if not entity.track_id:
                continue
            prefix = entities_dir / entity.track_id
            cv2.imwrite(str(prefix.with_name(prefix.name + "_crop.png")), entity.region.crop)
            cv2.imwrite(str(prefix.with_name(prefix.name + "_mask.png")), entity.region.mask)
            cv2.imwrite(str(prefix.with_name(prefix.name + "_difference.png")), entity.region.difference)
            DebugRecorder._atomic_json(prefix.with_suffix(".json"), entity.to_dict())

    def record_frame(self, result: FramePerception, images: dict[str, Any]) -> None:
        if not self.enabled:
            return
        if self.max_frames is not None and self.stats["total_frames"] >= self.max_frames:
            raise StopIteration("maximum debug frame count reached")
        frame_dir = self.frames_root / f"frame_{result.frame_index:06d}"
        entities_dir = frame_dir / "entities"
        entities_dir.mkdir(parents=True, exist_ok=True)
        full = self._requires_full_images(result)
        names = self.REQUIRED_IMAGES if full else ("01_grid_overlay.png",)
        self.stats["full_debug_frames"] += int(full)
        self._atomic_json(frame_dir / "frame.json", result.to_dict())
        with (self.session_root / "events.jsonl").open("a", encoding="utf-8") as handle:
            for event in result.events:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        copied = {name: image.copy() if hasattr(image, "copy") else image
                  for name, image in images.items() if name in names}
        entities = list(result.entities) if full else []
        if self.writer:
            self.writer.submit(self._write_images, frame_dir, entities_dir, tuple(names), copied, entities)
        else:
            self._write_images(frame_dir, entities_dir, tuple(names), copied, entities)
        self._accumulate(result)

    def _accumulate(self, result: FramePerception) -> None:
        s = self.stats
        s["total_frames"] += 1
        s["settled_frames"] += int(result.frame_state.get("settled", False))
        s["moving_frames"] += int(not result.frame_state.get("settled", False))
        s["frames_without_player"] += int(not result.player.get("recognized", False))
        usable = int(result.counters.get("background_matches_strong", 0)) + int(result.counters.get("background_matches_usable", 0))
        s["frames_without_background_reference"] += int(usable == 0)
        s["overlays_detected"] += sum(int(cell.metrics.overlay_detected) for cell in result.cells)
        created = sum(int(event.get("event") == "entity_created") for event in result.events)
        s["entities_created"] += created
        s["tracks_created"] += created
        s["semantic_candidates"] += int(result.counters.get("semantic_candidates", 0))
        s["residual_candidates"] += int(result.counters.get("residual_candidates", 0))
        s["frames_with_diagnostic_difference"] += int(result.counters.get("diagnostic_differences", 0) > 0)
        s["mobile_entities"] += sum(int(entity.movement_detected) for entity in result.entities)
        s["unknown_entities"] += sum(int(not entity.classification.known) for entity in result.entities)
        s["possible_enemies"] += sum(int(8 <= entity.hostility_score < 12) for entity in result.entities)
        s["probable_enemies"] += sum(int(12 <= entity.hostility_score < 16) for entity in result.entities)
        s["confirmed_enemies"] += sum(int(entity.hostility_score >= 16) for entity in result.entities)
        s["processing_errors"] += len(result.errors)
        s["processing_times"].append(result.processing_time_ms)

    def finalize(self, tracks: dict[str, Any] | None = None, status: str = "finished") -> None:
        if not self.enabled:
            return
        if self.writer:
            self.writer.close()
            if self.writer.errors:
                with (self.session_root / "errors.log").open("a", encoding="utf-8") as handle:
                    handle.write("\n".join(self.writer.errors) + "\n")
                self.stats["processing_errors"] += len(self.writer.errors)
        finished_at = datetime.now(timezone.utc)
        times = self.stats.pop("processing_times", [])
        summary = {**self.stats,
                   "average_processing_time_ms": sum(times) / len(times) if times else 0.0,
                   "maximum_processing_time_ms": max(times, default=0.0),
                   "session_duration": (finished_at - self.started_at).total_seconds(),
                   "disk_usage_bytes": sum(path.stat().st_size for path in self.session_root.rglob("*") if path.is_file())}
        self._atomic_json(self.session_root / "tracks.json", {"tracks": [track.to_dict() for track in (tracks or {}).values()]})
        with (self.session_root / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle); writer.writerow(["metric", "value"]); writer.writerows(summary.items())
        self._atomic_json(self.session_root / "session.json", {
            "session_id": self.session_id, "status": status, "debug_enabled": True,
            "debug_mode": self.debug_mode, "debug_stride": self.debug_stride,
            "session_path": str(self.session_root), "started_at": self.started_at.isoformat(),
            "finished_at": finished_at.isoformat(), "summary": summary,
        })

    @staticmethod
    def _atomic_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(path)
