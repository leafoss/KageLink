from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .pr27_native_grid import CellState, FragmentRole, PR27FrameResult, SpriteClass, TrackState


class PR27DebugOverlay:
    """PR27.5 overlay separating search regions from body-level combat authority."""

    def __init__(self, *, window_name: str = "Kage Combat Lab - PR27.5 Body Lock") -> None:
        self.window_name = window_name
        self.created = False

    @staticmethod
    def _cell_color(state: CellState) -> tuple[int, int, int]:
        if state is CellState.CHANGED:
            return (0, 180, 255)
        if state is CellState.UNCERTAIN:
            return (255, 190, 0)
        if state is CellState.BASELINE_INVALID:
            return (0, 0, 255)
        return (75, 75, 75)

    @staticmethod
    def _track_color(category: SpriteClass, state: TrackState) -> tuple[int, int, int]:
        if state is TrackState.TEMPORARILY_MISSING:
            return (150, 150, 150)
        if category is SpriteClass.PLAYER:
            return (255, 180, 0)
        if category is SpriteClass.ENEMY:
            return (0, 0, 255)
        if category is SpriteClass.NPC:
            return (255, 0, 255)
        return (0, 255, 255)

    def render(self, result: PR27FrameResult) -> np.ndarray:
        canvas = result.arena_bgr.copy()
        target_id = result.target.track_id if result.target else None
        target_anchor_cell = result.target.anchor_cell if result.target else None
        for cell in result.cells:
            difference = result.differences.get((cell.row, cell.column))
            state = CellState.BASELINE_INVALID if difference is None else difference.state
            color = self._cell_color(state)
            thickness = 3 if target_anchor_cell == (cell.row, cell.column) else 1
            cv2.rectangle(
                canvas,
                (cell.x, cell.y),
                (cell.x + cell.width - 1, cell.y + cell.height - 1),
                color if thickness == 1 else (0, 0, 255),
                thickness,
            )
            label = f"{cell.row},{cell.column}"
            if difference is not None and difference.state is not CellState.STABLE:
                label += f" {difference.changed_ratio:.2f}"
            cv2.putText(canvas, label, (cell.x + 2, cell.y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.30, color, 1, cv2.LINE_AA)
        for group in result.groups:
            for cell in group.cells:
                cv2.rectangle(canvas, (cell.x + 2, cell.y + 2), (cell.x + cell.width - 3, cell.y + cell.height - 3), (180, 0, 180), 1)
                cv2.putText(canvas, f"G{group.group_id}", (cell.x + 2, cell.y + cell.height - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (180, 0, 180), 1, cv2.LINE_AA)
        for fragment in result.fragments:
            x, y, width, height = fragment.native_bbox
            color = (0, 220, 220) if fragment.role is FragmentRole.BODY_CANDIDATE else (100, 100, 100)
            cv2.rectangle(canvas, (x, y), (x + width, y + height), color, 1)
            cv2.putText(canvas, f"F{fragment.fragment_id} BODY {fragment.body_score:.2f}", (x, max(10, y - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.30, color, 1, cv2.LINE_AA)
        for track in result.tracks:
            if track.track_state is TrackState.LOST:
                continue
            color = self._track_color(track.classification, track.track_state)
            x, y, width, height = track.native_bbox
            cv2.rectangle(canvas, (x, y), (x + width, y + height), (135, 135, 135), 1)
            cv2.putText(canvas, f"OBS ID{track.track_id}", (x, max(12, y - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (165, 165, 165), 1, cv2.LINE_AA)
            if track.body_bbox is not None:
                bx, by, bw, bh = track.body_bbox
                thickness = 4 if track.track_id == target_id else 2
                cv2.rectangle(canvas, (bx, by), (bx + bw, by + bh), color, thickness)
                label = (
                    f"{'LOCKED ENEMY' if track.track_id == target_id else 'BODY'} "
                    f"ID{track.track_id} {track.classification.value} conf={track.body_confidence:.2f}"
                )
                cv2.putText(canvas, label, (bx, max(14, by - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)
            if track.body_anchor is not None:
                ax, ay = int(round(track.body_anchor[0])), int(round(track.body_anchor[1]))
                cv2.drawMarker(canvas, (ax, ay), color, cv2.MARKER_CROSS, 14, 2)
                cv2.putText(canvas, f"A{track.anchor_cell}", (ax + 5, ay + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.34, color, 1, cv2.LINE_AA)
        status = (
            f"frame={result.frame_index} state={result.state.value} action={result.action.value} "
            f"target={target_id if target_id is not None else '-'} phase={result.grid_phase} "
            f"anchor_cell={target_anchor_cell if target_anchor_cell is not None else '-'}"
        )
        cv2.rectangle(canvas, (0, 0), (min(canvas.shape[1] - 1, 1180), 24), (0, 0, 0), -1)
        cv2.putText(canvas, status, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (255, 255, 255), 1, cv2.LINE_AA)
        return canvas

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
