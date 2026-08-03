from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import FramePerception


class DebugRecorder:
    """Persist every processed frame, including rejected, empty and error frames."""

    REQUIRED_IMAGES = (
        "00_raw_window.png",
        "01_grid_overlay.png",
        "02_background_composite.png",
        "03_difference_composite.png",
        "04_mask_composite.png",
        "05_components_overlay.png",
        "06_entities_overlay.png",
        "07_tracking_overlay.png",
        "08_hostility_overlay.png",
    )

    def __init__(
        self,
        root: Path,
        session_id: str,
        enabled: bool = True,
        max_frames: int | None = None,
    ) -> None:
        self.enabled = enabled
        self.session_id = session_id
        self.debug_root = Path(root)
        self.session_root = self.debug_root / session_id
        self.frames_root = self.session_root / "frames"
        self.max_frames = max_frames
        self.started_at = datetime.now(timezone.utc)
        self.stats: dict[str, Any] = {
            "total_frames": 0,
            "settled_frames": 0,
            "moving_frames": 0,
            "frames_without_player": 0,
            "frames_without_background_reference": 0,
            "overlays_detected": 0,
            "entities_created": 0,
            "mobile_entities": 0,
            "unknown_entities": 0,
            "possible_enemies": 0,
            "probable_enemies": 0,
            "confirmed_enemies": 0,
            "processing_errors": 0,
            "processing_times": [],
        }
        if enabled:
            self.frames_root.mkdir(parents=True, exist_ok=True)
            (self.session_root / "errors.log").touch(exist_ok=True)
            (self.debug_root / "LATEST_SESSION.txt").write_text(
                str(self.session_root),
                encoding="utf-8",
            )
            (self.session_root / "OPEN_THIS_FOLDER.txt").write_text(
                str(self.session_root),
                encoding="utf-8",
            )
            self._atomic_json(
                self.session_root / "session.json",
                {
                    "session_id": session_id,
                    "status": "running",
                    "debug_enabled": True,
                    "session_path": str(self.session_root),
                    "started_at": self.started_at.isoformat(),
                },
            )
            with (self.session_root / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "event": "session_started",
                            "session_id": session_id,
                            "session_path": str(self.session_root),
                            "started_at": self.started_at.isoformat(),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def record_frame(
        self,
        result: FramePerception,
        images: dict[str, Any],
    ) -> None:
        if not self.enabled:
            return
        if (
            self.max_frames is not None
            and self.stats["total_frames"] >= self.max_frames
        ):
            raise StopIteration("maximum debug frame count reached")

        import cv2
        import numpy as np

        frame_dir = self.frames_root / f"frame_{result.frame_index:06d}"
        entities_dir = frame_dir / "entities"
        entities_dir.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []
        raw = images.get("00_raw_window.png")
        fallback = np.zeros((64, 64, 3), np.uint8) if raw is None else raw

        for name in self.REQUIRED_IMAGES:
            image = images.get(name, fallback)
            if image is None or not cv2.imwrite(str(frame_dir / name), image):
                errors.append(f"failed_to_write:{name}")

        for entity in result.entities:
            if not entity.track_id:
                continue
            prefix = entities_dir / entity.track_id
            cv2.imwrite(
                str(prefix.with_name(prefix.name + "_crop.png")),
                entity.region.crop,
            )
            cv2.imwrite(
                str(prefix.with_name(prefix.name + "_mask.png")),
                entity.region.mask,
            )
            cv2.imwrite(
                str(prefix.with_name(prefix.name + "_difference.png")),
                entity.region.difference,
            )
            self._atomic_json(prefix.with_suffix(".json"), entity.to_dict())

        result.errors.extend(errors)
        self._atomic_json(frame_dir / "frame.json", result.to_dict())
        with (self.session_root / "events.jsonl").open("a", encoding="utf-8") as handle:
            for event in result.events:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._accumulate(result)

        if errors:
            with (self.session_root / "errors.log").open("a", encoding="utf-8") as handle:
                for error in errors:
                    handle.write(f"frame={result.frame_index} {error}\n")

    def _accumulate(self, result: FramePerception) -> None:
        stats = self.stats
        stats["total_frames"] += 1
        stats["settled_frames"] += int(result.frame_state.get("settled", False))
        stats["moving_frames"] += int(not result.frame_state.get("settled", False))
        stats["frames_without_player"] += int(not result.player.get("recognized", False))
        stats["frames_without_background_reference"] += int(
            any(not cell.background_reference_available for cell in result.cells)
        )
        stats["overlays_detected"] += sum(
            int(cell.metrics.overlay_detected) for cell in result.cells
        )
        stats["mobile_entities"] += sum(
            int(entity.movement_detected) for entity in result.entities
        )
        stats["unknown_entities"] += sum(
            int(not entity.classification.known) for entity in result.entities
        )
        stats["possible_enemies"] += sum(
            int(8 <= entity.hostility_score < 12) for entity in result.entities
        )
        stats["probable_enemies"] += sum(
            int(12 <= entity.hostility_score < 16) for entity in result.entities
        )
        stats["confirmed_enemies"] += sum(
            int(entity.hostility_score >= 16) for entity in result.entities
        )
        stats["processing_errors"] += len(result.errors)
        stats["processing_times"].append(result.processing_time_ms)

    def finalize(
        self,
        tracks: dict[str, Any] | None = None,
        status: str = "finished",
    ) -> None:
        if not self.enabled:
            return
        finished_at = datetime.now(timezone.utc)
        times = self.stats.pop("processing_times", [])
        summary = {
            **self.stats,
            "average_processing_time_ms": sum(times) / len(times) if times else 0.0,
            "maximum_processing_time_ms": max(times, default=0.0),
            "session_duration": (finished_at - self.started_at).total_seconds(),
            "disk_usage_bytes": sum(
                path.stat().st_size
                for path in self.session_root.rglob("*")
                if path.is_file()
            ),
        }
        self._atomic_json(
            self.session_root / "tracks.json",
            {"tracks": [track.to_dict() for track in (tracks or {}).values()]},
        )
        with (self.session_root / "summary.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(["metric", "value"])
            writer.writerows(summary.items())
        self._atomic_json(
            self.session_root / "session.json",
            {
                "session_id": self.session_id,
                "status": status,
                "debug_enabled": True,
                "session_path": str(self.session_root),
                "started_at": self.started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "summary": summary,
            },
        )

    @staticmethod
    def _atomic_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(path)
