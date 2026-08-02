from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .pr27_native_grid import CellState, PR27FrameResult, SpriteClass, TrackState


class PR27DebugOverlay:
    """Truthful PR27 overlay: cell truth first, group hints second, sprite IDs last."""

    def __init__(self, *, window_name: str = "Kage Combat Lab - PR27") -> None:
        self.window_name = window_name
        self.paused = False

    @staticmethod
    def _cell_color(state: CellState) -> tuple[int, int, int]:
        if state is CellState.CHANGED:
            return (0, 180, 255)
        if state is CellState.UNCERTAIN:
            return (255, 190, 0)
        if state is CellState.BASELINE_INVALID:
            return (0, 0, 255)
        return (90, 90, 90)

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
        for cell in result.cells:
            difference = result.differences.get((cell.row, cell.column))
            state = CellState.BASELINE_INVALID if difference is None else difference.state
            color = self._cell_color(state)
            cv2.rectangle(
                canvas,
                (cell.x, cell.y),
                (cell.x + cell.width - 1, cell.y + cell.height - 1),
                color,
                1,
            )
            label = f"{cell.row},{cell.column}"
            if difference is not None and difference.state is not CellState.STABLE:
                label += f" {difference.changed_ratio:.2f}"
            cv2.putText(
                canvas,
                label,
                (cell.x + 2, cell.y + 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.32,
                color,
                1,
                cv2.LINE_AA,
            )

        for group in result.groups:
            for cell in group.cells:
                cv2.rectangle(
                    canvas,
                    (cell.x + 2, cell.y + 2),
                    (cell.x + cell.width - 3, cell.y + cell.height - 3),
                    (180, 0, 180),
                    1,
                )
                cv2.putText(
                    canvas,
                    f"G{group.group_id}",
                    (cell.x + 2, cell.y + cell.height - 4),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.34,
                    (180, 0, 180),
                    1,
                    cv2.LINE_AA,
                )

        for fragment in result.fragments:
            x, y, width, height = fragment.native_bbox
            cv2.rectangle(canvas, (x, y), (x + width, y + height), (0, 220, 220), 1)
            cv2.putText(
                canvas,
                f"F{fragment.fragment_id}",
                (x, max(10, y - 2)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                (0, 220, 220),
                1,
                cv2.LINE_AA,
            )

        for track in result.tracks:
            if track.track_state is TrackState.LOST:
                continue
            x, y, width, height = track.native_bbox
            color = self._track_color(track.classification, track.track_state)
            cv2.rectangle(canvas, (x, y), (x + width, y + height), color, 2)
            cv2.putText(
                canvas,
                f"ID {track.track_id} {track.classification.value} {track.track_state.value}",
                (x, max(14, y - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                color,
                1,
                cv2.LINE_AA,
            )

        status = (
            f"frame={result.frame_index} state={result.state.value} "
            f"action={result.action.value} target={result.target.track_id if result.target else '-'}"
        )
        cv2.rectangle(canvas, (0, 0), (min(canvas.shape[1] - 1, 880), 24), (0, 0, 0), -1)
        cv2.putText(
            canvas,
            status,
            (6, 17),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        return canvas

    def show(self, image: np.ndarray) -> bool:
        cv2.imshow(self.window_name, image)
        key = cv2.waitKey(1 if not self.paused else 0) & 0xFF
        if key in (ord("p"), ord(" ")):
            self.paused = not self.paused
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
