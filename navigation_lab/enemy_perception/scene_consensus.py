from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class _ConsensusPending:
    terrain_class: str
    image: Any
    count: int
    last_frame: int


class SceneConsensusLearner:
    """Learn repeated dominant terrain without treating one stationary NPC as empty.

    A candidate appearance must occur in several different cells in one frame
    and repeat across multiple frames. Player, NPC, HUD and dynamic cells are
    excluded by the caller before they reach this component.
    """

    def __init__(
        self,
        background_store: Any,
        min_cells: int = 8,
        required_frames: int = 4,
        similarity_threshold: float = 0.94,
    ) -> None:
        self.background_store = background_store
        self.min_cells = max(2, int(min_cells))
        self.required_frames = max(2, int(required_frames))
        self.similarity_threshold = float(similarity_threshold)
        self.pending: list[_ConsensusPending] = []

    def _frame_groups(
        self,
        candidates: list[tuple[str, Any]],
    ) -> list[tuple[str, list[Any]]]:
        groups: list[tuple[str, list[Any]]] = []
        for terrain_class, crop in candidates:
            selected: list[Any] | None = None
            for group_class, images in groups:
                if group_class != terrain_class:
                    continue
                if self.background_store.raw_similarity(crop, images[0]) >= self.similarity_threshold:
                    selected = images
                    break
            if selected is None:
                groups.append((terrain_class, [crop]))
            else:
                selected.append(crop)
        return [item for item in groups if len(item[1]) >= self.min_cells]

    @staticmethod
    def _median_image(images: list[Any]) -> Any:
        import numpy as np

        stack = np.stack(images, axis=0).astype(np.float32)
        return np.median(stack, axis=0).astype(np.uint8)

    def observe(
        self,
        candidates: list[tuple[str, Any]],
        frame_index: int,
    ) -> list[str]:
        learned: list[str] = []
        for terrain_class, images in self._frame_groups(candidates):
            median = self._median_image(images)
            existing = self.background_store.choose(median, terrain_class=terrain_class)
            if existing.available and existing.raw_similarity >= 0.985:
                continue
            selected: _ConsensusPending | None = None
            for pending in self.pending:
                if pending.terrain_class != terrain_class:
                    continue
                if frame_index - pending.last_frame > 2:
                    continue
                if self.background_store.raw_similarity(median, pending.image) >= self.similarity_threshold:
                    selected = pending
                    break
            if selected is None:
                self.pending.append(
                    _ConsensusPending(terrain_class, median.copy(), 1, int(frame_index))
                )
                continue
            selected.count += 1
            selected.last_frame = int(frame_index)
            selected.image = self._median_image([selected.image, median])
            if selected.count < self.required_frames:
                continue
            learned.append(
                self.background_store.add_reference(
                    None,
                    terrain_class,
                    selected.image,
                    source_frame=frame_index,
                    source="scene_consensus",
                )
            )
            self.pending.remove(selected)
        self.pending = [
            item for item in self.pending if frame_index - item.last_frame <= 8
        ]
        return learned
