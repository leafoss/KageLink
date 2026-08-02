from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .domain import CandidateObservation


class PlayerFacingDatasetCollector:
    """Collect trustworthy player crops after exclusive facing transactions."""

    def __init__(
        self,
        root: Path | str,
        *,
        crop_size: int = 64,
        minimum_confidence: float = 0.80,
        maximum_contamination: float = 0.35,
    ) -> None:
        self.root = Path(root)
        self.crop_size = max(32, min(96, int(crop_size)))
        self.minimum_confidence = max(0.0, min(1.0, float(minimum_confidence)))
        self.maximum_contamination = max(0.0, min(1.0, float(maximum_contamination)))
        for direction in ("right", "left", "up", "down"):
            (self.root / direction).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _intersection_ratio(
        left: tuple[int, int, int, int],
        right: tuple[int, int, int, int],
    ) -> float:
        lx, ly, lw, lh = left
        rx, ry, rw, rh = right
        x0 = max(lx, rx)
        y0 = max(ly, ry)
        x1 = min(lx + lw, rx + rw)
        y1 = min(ly + lh, ry + rh)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        overlap = float((x1 - x0) * (y1 - y0))
        return min(1.0, overlap / max(1.0, float(lw * lh)))

    def _player_crop(
        self,
        frame_bgr: np.ndarray,
        state: Any,
    ) -> tuple[np.ndarray | None, tuple[int, int, int, int]]:
        arena = tuple(int(value) for value in state.arena_rect)
        center = state.player_center
        cx = int(round(arena[0] + float(center[0])))
        cy = int(round(arena[1] + float(center[1])))
        half = self.crop_size // 2
        left = max(0, cx - half)
        top = max(0, cy - half)
        right = min(frame_bgr.shape[1], left + self.crop_size)
        bottom = min(frame_bgr.shape[0], top + self.crop_size)
        left = max(0, right - self.crop_size)
        top = max(0, bottom - self.crop_size)
        if right <= left or bottom <= top:
            return None, (left, top, 0, 0)
        crop = frame_bgr[top:bottom, left:right].copy()
        if crop.shape[0] != self.crop_size or crop.shape[1] != self.crop_size:
            return None, (left, top, right - left, bottom - top)
        return crop, (left, top, self.crop_size, self.crop_size)

    def _contamination_score(
        self,
        *,
        state: Any,
        player_rect: tuple[int, int, int, int],
        candidate: CandidateObservation | None,
    ) -> float:
        overlap = 0.0
        if candidate is not None and candidate.bbox is not None:
            arena = tuple(int(value) for value in state.arena_rect)
            x, y, width, height = candidate.bbox
            target_rect = (arena[0] + int(x), arena[1] + int(y), int(width), int(height))
            overlap = self._intersection_ratio(player_rect, target_rect)

        motion_density = 0.0
        mask = getattr(state, "motion_mask", None)
        if mask is not None and getattr(mask, "size", 0):
            arena = tuple(int(value) for value in state.arena_rect)
            x, y, width, height = player_rect
            local_x0 = max(0, x - arena[0])
            local_y0 = max(0, y - arena[1])
            local_x1 = min(mask.shape[1], local_x0 + width)
            local_y1 = min(mask.shape[0], local_y0 + height)
            local = mask[local_y0:local_y1, local_x0:local_x1]
            if local.size:
                motion_density = float(np.count_nonzero(local)) / float(local.size)
        return min(1.0, max(overlap, motion_density * 1.5))

    def save_if_trustworthy(
        self,
        *,
        frame_bgr: np.ndarray,
        state: Any,
        candidate: CandidateObservation | None,
        direction: str,
        round_name: str,
        frame_index: int,
        confidence: float,
        source: str,
    ) -> tuple[bool, float, Path | None]:
        normalized = str(direction).strip().lower()
        if normalized not in {"right", "left", "up", "down"}:
            return False, 1.0, None
        if float(confidence) < self.minimum_confidence:
            return False, 1.0, None

        crop, player_rect = self._player_crop(frame_bgr, state)
        if crop is None or crop.size == 0:
            return False, 1.0, None
        contamination = self._contamination_score(
            state=state,
            player_rect=player_rect,
            candidate=candidate,
        )
        if contamination > self.maximum_contamination:
            return False, contamination, None

        folder = self.root / normalized
        base = f"{round_name}_frame_{int(frame_index):06d}"
        image_path = folder / f"{base}.png"
        metadata_path = folder / f"{base}.json"
        index = 2
        while image_path.exists() or metadata_path.exists():
            image_path = folder / f"{base}_{index}.png"
            metadata_path = folder / f"{base}_{index}.json"
            index += 1

        if not cv2.imwrite(str(image_path), crop):
            return False, contamination, None
        metadata_path.write_text(
            json.dumps(
                {
                    "round": round_name,
                    "frame": int(frame_index),
                    "commanded_facing": normalized.upper(),
                    "confirmed_facing": normalized.upper(),
                    "source": str(source),
                    "confidence": round(float(confidence), 4),
                    "contamination_score": round(float(contamination), 4),
                    "image": image_path.name,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return True, contamination, image_path


__all__ = ["PlayerFacingDatasetCollector"]
