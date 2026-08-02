from __future__ import annotations

import os
from typing import Any

import cv2
import numpy as np

from .domain import CELL_SIZE_PX
from .occupancy_model import OccupancyState


_INSTALLED = False


def _player_rect(state: Any, margin: int) -> tuple[int, int, int, int]:
    width = max(6, int(round(float(os.environ.get("KAGE_PR26_PLAYER_MASK_WIDTH", "18")))))
    height = max(10, int(round(float(os.environ.get("KAGE_PR26_PLAYER_MASK_HEIGHT", "38")))))
    center_x, center_y = (float(value) for value in state.player_center)
    return (
        int(round(center_x - width / 2.0)) - margin,
        int(round(center_y - height / 2.0)) - margin,
        width + margin * 2,
        height + margin * 2,
    )


def _affinity_code(affinity: Any | None) -> str:
    level = str(getattr(affinity, "level", "NONE"))
    return {
        "DANGER_CONFIRMED": "DC",
        "DANGER_LIKELY": "DL",
        "DANGER_WEAK_PRIOR": "DW",
    }.get(level, "--")


def install_runtime_mask_cluster_guard() -> None:
    """Install player exclusion and truthful 64px mask/semantic overlay."""

    global _INSTALLED
    if _INSTALLED:
        return

    from .occupancy_tracking import PR26OccupancyTracker
    from .pixel_occupancy import PixelOccupancyMap

    original_observe = PixelOccupancyMap.observe

    def player_masked_observe(self, *, player_rect=None, state, **kwargs):
        if player_rect is None:
            player_rect = _player_rect(state, self.config.player_mask_margin_px)
        return original_observe(
            self,
            state=state,
            player_rect=player_rect,
            **kwargs,
        )

    def truthful_overlay(self, frame: np.ndarray, state: Any, active):
        result = frame.copy()
        arena_x, arena_y, _, _ = (int(value) for value in state.arena_rect)
        affinities = (
            getattr(self.map.perception, "last_danger_affinity", {})
            if self.map.perception is not None
            else {}
        )

        # Red pixels are the actual largest foreground component after player
        # exclusion. Blue rectangles are always the immutable 64x64 cells.
        for item in self.last_cells.values():
            left, top, width, height = item.evidence.bbox
            full_left = arena_x + left
            full_top = arena_y + top
            affinity = affinities.get(item.cell)
            if item.mask is not None and np.any(item.mask):
                roi = result[
                    full_top : full_top + height,
                    full_left : full_left + width,
                ]
                if roi.shape[:2] == item.mask.shape[:2]:
                    red = np.zeros_like(roi)
                    red[:, :, 2] = 255
                    selected = item.mask > 0
                    roi[selected] = cv2.addWeighted(
                        roi[selected],
                        0.45,
                        red[selected],
                        0.55,
                        0.0,
                    )
            cv2.rectangle(
                result,
                (full_left, full_top),
                (full_left + width, full_top + height),
                (255, 120, 0),
                1,
            )
            affinity_level = str(getattr(affinity, "level", "NONE"))
            if affinity_level in {"DANGER_CONFIRMED", "DANGER_LIKELY"}:
                cv2.rectangle(
                    result,
                    (full_left + 1, full_top + 1),
                    (full_left + width - 1, full_top + height - 1),
                    (0, 255, 255),
                    2,
                )
            source = "E" if item.reference_authoritative else "C"
            state_code = (
                "O"
                if item.state is OccupancyState.OCCUPIED
                else "W"
                if item.state is OccupancyState.WEAK
                else "-"
            )
            cv2.putText(
                result,
                f"{item.true_changed_ratio:.2f}{source}{state_code}",
                (full_left + 2, full_top + 11),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.27,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                result,
                (
                    f"{_affinity_code(affinity)} "
                    f"{float(getattr(affinity, 'danger_similarity', 0.0)):.2f} "
                    f"M{float(getattr(affinity, 'danger_margin', 0.0)):+.2f}"
                ),
                (full_left + 2, full_top + 23),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.25,
                (0, 255, 255) if affinity_level != "NONE" else (180, 180, 180),
                1,
                cv2.LINE_AA,
            )

        player_rect = self.map.last_player_rect
        if player_rect is not None:
            left, top, width, height = player_rect
            cv2.rectangle(
                result,
                (arena_x + left, arena_y + top),
                (arena_x + left + width, arena_y + top + height),
                (255, 255, 255),
                2,
            )
            cv2.putText(
                result,
                "PLAYER MASK",
                (arena_x + left, max(16, arena_y + top - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        for cluster in self.last_clusters:
            left, top, width, height = cluster.bbox
            cv2.rectangle(
                result,
                (arena_x + left, arena_y + top),
                (arena_x + left + width, arena_y + top + height),
                (255, 0, 255),
                2,
            )
            cv2.circle(
                result,
                (
                    arena_x + int(round(cluster.foot_point[0])),
                    arena_y + int(round(cluster.foot_point[1])),
                ),
                5,
                (255, 0, 255),
                -1,
            )
            cv2.putText(
                result,
                f"C{cluster.local_id} n={len(cluster.cells)} D={cluster.danger_prior:.2f}",
                (arena_x + left, max(45, arena_y + top - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.32,
                (255, 0, 255),
                1,
                cv2.LINE_AA,
            )

        direction = "-"
        cluster_id = "-"
        cell_count = 0
        cluster_bbox = "-"
        face_lock = False
        combat_lock = False
        lock_kind = "NONE"
        danger_score = 0.0
        if active is not None:
            direction = self._face(state.player_center, active.foot_point) or "HOLD"
            cluster_id = str(active.track_id)
            cell_count = len(active.cells)
            cluster_bbox = f"{active.bbox[2]}x{active.bbox[3]}"
            face_lock = bool(active.face_only_lock)
            combat_lock = bool(active.combat_lock)
            danger_score = float(active.danger_score)
            lock_kind = "DANGER_LOCK" if danger_score >= 0.50 else "ENTITY_LOCK"

        cv2.rectangle(result, (0, 0), (result.shape[1], 47), (0, 0, 0), -1)
        cv2.putText(
            result,
            (
                f"PR26.5 {self.mode.value} CELL_SIZE={CELL_SIZE_PX}x{CELL_SIZE_PX} "
                f"active={cluster_id} lock={lock_kind} cells={cell_count} bbox={cluster_bbox}"
            ),
            (10, 17),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            result,
            (
                f"face_lock={face_lock} direction={direction} combat_lock={combat_lock} "
                f"danger={danger_score:.2f} candidates={len(self.last_clusters)} "
                f"rejected={len(self.map.last_rejected_clusters)}"
            ),
            (10, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        return result

    PixelOccupancyMap.observe = player_masked_observe
    PR26OccupancyTracker._overlay = truthful_overlay
    _INSTALLED = True
    print(
        "PR26.5 MASK CLUSTER GUARD: player excluded; cardinal edge-contact only; "
        "humanoid cluster <=2x3 cells; semantic DANGER affinity visible"
    )


__all__ = ["install_runtime_mask_cluster_guard"]
