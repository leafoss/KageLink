from __future__ import annotations

from pathlib import Path
import os

import cv2
import numpy as np

from .pr27_native_grid import (
    LocalBackgroundState,
    PR27FrameResult,
    SpriteClass,
    SpriteRole,
    TrackState,
)


class PR27DebugOverlay:
    """PR27.7 local overlay; labels derive from immutable authority IDs."""

    def __init__(self, *, window_name: str = "Kage Combat Lab - PR27.7 SELF Authority") -> None:
        self.window_name = window_name
        self.created = False

    @staticmethod
    def _track_color(track, result: PR27FrameResult) -> tuple[int, int, int]:
        if track.track_state is TrackState.TEMPORARILY_MISSING:
            return (150, 150, 150)
        if track.track_id == result.player_track_id:
            return (255, 190, 0)
        if result.target is not None and track.track_id == result.target.track_id:
            return (0, 0, 255)
        if track.effective_role is SpriteRole.NPC:
            return (255, 0, 255)
        if track.effective_role is SpriteRole.ENEMY:
            return (0, 80, 255)
        return (0, 255, 255)

    @staticmethod
    def _background_color(state: LocalBackgroundState | None) -> tuple[int, int, int]:
        if state is LocalBackgroundState.OCCLUDED_BY_EFFECT:
            return (0, 100, 255)
        if state in {LocalBackgroundState.UNKNOWN, LocalBackgroundState.LEARNING_BACKGROUND}:
            return (0, 220, 220)
        return (70, 70, 70)

    @staticmethod
    def _role_label(track, result: PR27FrameResult) -> str:
        if track.track_id == result.player_track_id:
            return f"SELF ID{track.track_id} {result.self_track_state.value}"
        if track.classification is SpriteClass.PLAYER or track.effective_role is SpriteRole.SELF:
            return f"INVALID ROLE FLIP ID{track.track_id} ENEMY/NPC->SELF BLOCKED"
        if result.target is not None and track.track_id == result.target.track_id:
            return f"ENEMY LOCK ID{track.track_id} source={track.track_source}"
        return f"BODY ID{track.track_id} role={track.effective_role.value}"

    def render(self, result: PR27FrameResult) -> np.ndarray:
        canvas = result.arena_bgr.copy()
        enemy_cell = result.enemy_relative_cell

        for cell in result.cells:
            key = (cell.row, cell.column)
            if key == (0, 0):
                color, thickness = (255, 190, 0), 4
            elif key == enemy_cell:
                color, thickness = (0, 0, 255), 4
            else:
                color, thickness = self._background_color(result.local_background_states.get(key)), 1
            cv2.rectangle(
                canvas,
                (cell.x, cell.y),
                (cell.x + cell.width - 1, cell.y + cell.height - 1),
                color,
                thickness,
            )
            label = "SELF CELL (0,0)" if key == (0, 0) else f"({cell.row:+d},{cell.column:+d})"
            if key == enemy_cell:
                label = f"ENEMY CELL ({cell.row:+d},{cell.column:+d})"
            cv2.putText(
                canvas,
                label,
                (cell.x + 2, cell.y + 13),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                color,
                1,
                cv2.LINE_AA,
            )

        if result.roi_center is not None:
            cx, cy = int(round(result.roi_center[0])), int(round(result.roi_center[1]))
            cv2.circle(canvas, (cx, cy), result.roi_radius_cells * 64, (255, 150, 0), 1, cv2.LINE_AA)

        if result.merged_body_detected and result.merged_body_bbox is not None:
            x, y, width, height = result.merged_body_bbox
            cv2.rectangle(canvas, (x, y), (x + width, y + height), (0, 140, 255), 5)
            cv2.putText(
                canvas,
                "MERGED_BODY - IDENTITIES PRESERVED",
                (x, max(18, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (0, 140, 255),
                2,
                cv2.LINE_AA,
            )

        for track in result.tracks:
            if track.track_state is TrackState.LOST or track.body_bbox is None:
                continue
            color = self._track_color(track, result)
            bx, by, bw, bh = track.body_bbox
            is_target = result.target is not None and track.track_id == result.target.track_id
            thickness = 4 if is_target or track.track_id == result.player_track_id else 2
            cv2.rectangle(canvas, (bx, by), (bx + bw, by + bh), color, thickness)
            label = self._role_label(track, result)
            if track.track_id == result.player_track_id:
                label += f" source={result.self_role_source} conf={result.self_confidence:.2f}"
            cv2.putText(
                canvas,
                label,
                (bx, max(16, by - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                color,
                1,
                cv2.LINE_AA,
            )
            if track.body_anchor is not None:
                ax, ay = int(round(track.body_anchor[0])), int(round(track.body_anchor[1]))
                cv2.drawMarker(canvas, (ax, ay), color, cv2.MARKER_CROSS, 14, 2)
                cv2.putText(
                    canvas,
                    f"A{track.anchor_cell} obs={track.observation_id}",
                    (ax + 5, ay + 14),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.34,
                    color,
                    1,
                    cv2.LINE_AA,
                )

        if result.role_conflict:
            cv2.rectangle(canvas, (2, 48), (min(canvas.shape[1] - 2, 760), 78), (255, 255, 255), 3)
            cv2.putText(
                canvas,
                f"ROLE_CONFLICT {result.role_flip_blocked or 'SHARED OBSERVATION BLOCKED'}",
                (10, 69),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        status1 = (
            f"frame={result.frame_index} state={result.state.value} local={result.local_state.value} "
            f"action={result.action.value} ROI_RADIUS={result.roi_radius_cells} ROI_CELLS={result.roi_processed_cell_count}"
        )
        control_enabled = os.environ.get("KAGE_PR27_CONTROL_MODE", "").strip().upper() == "CONTROL_ENABLED"
        status2 = (
            f"SELF={result.player_track_id} SELF_STATE={result.self_track_state.value} SELF_OBS={result.self_observation_id} "
            f"ENEMY={result.target.track_id if result.target else '-'} ENEMY_OBS={result.enemy_observation_id}"
        )
        status3 = (
            f"ROLE_CONFLICT={str(result.role_conflict).lower()} MERGED={str(result.merged_body_detected).lower()} "
            f"REL_PX={result.enemy_relative_anchor_px or '-'} SUBCELL={result.subcell_direction or '-'} "
            f"RECOVERY={result.close_reacquire_state.value}"
        )
        status4 = (
            f"R_LATCHED={str(control_enabled).lower()} FACING_CMD={result.facing_commanded or 'UNKNOWN'} "
            f"FACING_OBS={result.facing_observed or 'UNKNOWN'} CONFIRMED={str(result.facing_confirmed).lower()} "
            f"H_BLOCK={result.h_block_reason or '-'} DEADLOCK={dict(result.deadlock_counters)}"
        )
        cv2.rectangle(canvas, (0, 0), (min(canvas.shape[1] - 1, 1700), 82), (0, 0, 0), -1)
        for index, text in enumerate((status1, status2, status3, status4)):
            cv2.putText(
                canvas,
                text,
                (6, 16 + index * 19),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
        return canvas

    @staticmethod
    def roi_crop(image: np.ndarray, result: PR27FrameResult, *, margin: int = 24) -> np.ndarray:
        if result.roi_center is None:
            return image
        radius = result.roi_radius_cells * 64 + max(0, int(margin))
        cx, cy = int(round(result.roi_center[0])), int(round(result.roi_center[1]))
        left, top = max(0, cx - radius), max(0, cy - radius)
        right, bottom = min(image.shape[1], cx + radius), min(image.shape[0], cy + radius)
        if right <= left or bottom <= top:
            return image
        return image[top:bottom, left:right].copy()

    def show(self, image: np.ndarray) -> bool:
        if not self.created:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            self.created = True
        cv2.imshow(self.window_name, image)
        key = cv2.waitKey(1) & 0xFF
        return key not in (27, ord("q"))

    @staticmethod
    def save(image: np.ndarray, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), image)

    @staticmethod
    def close() -> None:
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
