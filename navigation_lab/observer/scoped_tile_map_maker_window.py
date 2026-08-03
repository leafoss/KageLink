from __future__ import annotations

from tkinter import messagebox
from typing import Any

from ..storage import JsonRepository
from .grid_calibration import GridCalibration
from .playfield_learning_scope import PlayfieldLearningScope
from .tile_map_engine import ClassifiedGridCell
from .tile_map_maker_window import TileMapMakerWindow
from .window_capture import WindowsClientCapture


class ScopedTileMapMakerWindow(TileMapMakerWindow):
    """Tile MapMaker that keeps the HUD visible but outside the learning scope."""

    def __init__(
        self,
        capture: WindowsClientCapture,
        repository: JsonRepository,
        region_id: str,
        calibration: GridCalibration,
        similarity_threshold: float = 0.92,
        language: str = "pt-BR",
        playfield_bottom_ratio: float = 0.75,
    ) -> None:
        self.learning_scope = PlayfieldLearningScope(playfield_bottom_ratio)
        super().__init__(
            capture=capture,
            repository=repository,
            region_id=region_id,
            calibration=calibration,
            similarity_threshold=similarity_threshold,
            language=language,
        )
        self.root.title("Kage Semantic Tile MapMaker — campo jogável protegido")

    def _frame_height(self) -> int:
        if self._scan is None or self._scan.frame is None:
            return 1
        return int(self._scan.frame.shape[0])

    def _is_learning_eligible(self, cell: ClassifiedGridCell) -> bool:
        return self.learning_scope.is_eligible(cell, self._frame_height())

    def _learnable_unknown_cells(self) -> list[ClassifiedGridCell]:
        if self._scan is None:
            return []
        return self.learning_scope.filter_eligible(
            self._scan.unknown_cells,
            self._frame_height(),
        )

    def _refresh_unknown_list(self) -> None:
        self.unknown_list.delete(0, "end")
        for cell in self._learnable_unknown_cells():
            self.unknown_list.insert(
                "end",
                f"{cell.crop.id}  melhor={cell.classification.confidence:.1%}",
            )

    def _refresh_stats(self) -> None:
        super()._refresh_stats()
        if self._scan is None:
            return
        height = self._frame_height()
        cutoff = self.learning_scope.cutoff_y(height)
        ignored = sum(
            1 for cell in self._scan.cells
            if not self.learning_scope.is_eligible(cell, height)
        )
        total_unknown = len(self._scan.unknown_cells)
        learnable_unknown = len(self._learnable_unknown_cells())
        self.stats_var.set(
            self.stats_var.get()
            + "\n\n"
            + f"Limite do campo jogável: y={cutoff}px "
            + f"({self.learning_scope.bottom_ratio:.0%} da altura)\n"
            + f"Células do HUD somente visualizadas: {ignored}\n"
            + f"Desconhecidas elegíveis para ensino: {learnable_unknown}/{total_unknown}"
        )

    def _select_first_unknown(self) -> None:
        unknown = self._learnable_unknown_cells()
        if not unknown:
            self._selected = None
            self._refresh_selected()
            return
        self.unknown_list.selection_clear(0, "end")
        self.unknown_list.selection_set(0)
        self.unknown_list.activate(0)
        self._selected = unknown[0]
        self._refresh_selected()

    def _select_from_unknown_list(self, _event: Any) -> None:
        selected_indices = self.unknown_list.curselection()
        if not selected_indices:
            return
        unknown = self._learnable_unknown_cells()
        index = int(selected_indices[0])
        if 0 <= index < len(unknown):
            self._selected = unknown[index]
            self._refresh_selected()
            self._redraw()

    def _refresh_selected(self) -> None:
        super()._refresh_selected()
        selected = self._selected
        if selected is not None and not self._is_learning_eligible(selected):
            self.selected_var.set(
                self.selected_var.get()
                + "\n\nHUD / fora do campo jogável: classificação visível, "
                + "mas o ensino está bloqueado."
            )

    def _teach(self, category: Any) -> None:
        selected = self._selected
        if selected is not None and not self._is_learning_eligible(selected):
            cutoff = self.learning_scope.cutoff_y(self._frame_height())
            self.status_var.set(
                f"Ensino bloqueado: {selected.crop.id} está abaixo de y={cutoff}px, na área do HUD."
            )
            messagebox.showwarning(
                "Kage MapMaker",
                "Esta célula pertence à área do HUD. Ela pode ser visualizada e classificada, "
                "mas não pode ser registrada como novo exemplo.",
            )
            return
        super()._teach(category)

    def _draw_overlay(self) -> Any:
        import cv2

        frame = super()._draw_overlay()
        if frame is None:
            return None
        height, width = frame.shape[:2]
        cutoff = self.learning_scope.cutoff_y(height)
        if cutoff >= height:
            return frame

        shade = frame.copy()
        cv2.rectangle(shade, (0, cutoff), (width - 1, height - 1), (35, 35, 35), -1)
        cv2.addWeighted(shade, 0.62, frame, 0.38, 0.0, frame)
        cv2.line(frame, (0, cutoff), (width - 1, cutoff), (0, 0, 255), 3)
        cv2.putText(
            frame,
            "HUD — SOMENTE CLASSIFICACAO; NOVOS EXEMPLOS BLOQUEADOS",
            (12, min(height - 10, cutoff + 24)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return frame
