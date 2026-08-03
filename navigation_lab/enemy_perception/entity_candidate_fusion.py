from __future__ import annotations

from .models import EntityObservation


class EntityCandidateFusion:
    """Merge semantic NPC evidence with residual foreground evidence."""

    def __init__(self, max_anchor_distance: int = 1, min_iou: float = 0.05) -> None:
        self.max_anchor_distance = max(0, int(max_anchor_distance))
        self.min_iou = float(min_iou)

    @staticmethod
    def _anchor_distance(left: EntityObservation, right: EntityObservation) -> int:
        a = left.region.anchor_screen_cell
        b = right.region.anchor_screen_cell
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _iou(left: EntityObservation, right: EntityObservation) -> float:
        ax0, ay0, ax1, ay1 = left.region.bounding_box_px
        bx0, by0, bx1, by1 = right.region.bounding_box_px
        ix0, iy0 = max(ax0, bx0), max(ay0, by0)
        ix1, iy1 = min(ax1, bx1), min(ay1, by1)
        intersection = max(0, ix1 - ix0) * max(0, iy1 - iy0)
        if intersection <= 0:
            return 0.0
        area_a = max(1, (ax1 - ax0) * (ay1 - ay0))
        area_b = max(1, (bx1 - bx0) * (by1 - by0))
        return intersection / float(area_a + area_b - intersection)

    def fuse(
        self,
        semantic: list[EntityObservation],
        residual: list[EntityObservation],
    ) -> list[EntityObservation]:
        output: list[EntityObservation] = []
        unused = set(range(len(residual)))
        for semantic_item in semantic:
            best_index: int | None = None
            best_score = -1.0
            for index in list(unused):
                residual_item = residual[index]
                distance = self._anchor_distance(semantic_item, residual_item)
                overlap = self._iou(semantic_item, residual_item)
                if distance > self.max_anchor_distance and overlap < self.min_iou:
                    continue
                score = overlap + max(0.0, 1.0 - distance / 2.0)
                if score > best_score:
                    best_score = score
                    best_index = index
            if best_index is None:
                output.append(semantic_item)
                continue
            residual_item = residual[best_index]
            unused.remove(best_index)
            # Residual masks generally provide a tighter shape; semantic evidence
            # remains authoritative for category and candidate confidence.
            residual_item.classification = semantic_item.classification
            residual_item.semantic_class = semantic_item.semantic_class
            residual_item.semantic_confidence = semantic_item.semantic_confidence
            residual_item.candidate_sources = sorted(
                set(semantic_item.candidate_sources + residual_item.candidate_sources)
            )
            residual_item.overall_candidate_confidence = max(
                semantic_item.overall_candidate_confidence,
                residual_item.overall_candidate_confidence,
            )
            output.append(residual_item)
        output.extend(residual[index] for index in sorted(unused))
        return output
