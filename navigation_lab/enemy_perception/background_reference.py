from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import BackgroundMatch


SCHEMA_VERSION = 2


@dataclass(slots=True)
class _Reference:
    id: str
    terrain_class: str
    path: str | None
    image: Any
    source_world_cell: tuple[int, int] | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_frame: int | None = None
    similarity_history: list[float] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION


@dataclass(slots=True)
class _Pending:
    image: Any
    count: int
    terrain_class: str
    source_world_cell: tuple[int, int] | None
    source_frame: int | None


class BackgroundReferenceStore:
    """Visual catalogue of empty tiles, independent from world coordinates.

    Production matching answers: "Have I seen this empty tile, or something
    visually similar, before?" References are grouped by semantic terrain class;
    world coordinates are retained only as source metadata.
    """

    def __init__(
        self,
        root: Path | None = None,
        max_references: int = 32,
        stable_frames: int = 3,
        stable_similarity: float = 0.985,
        trim_changed_fraction: float = 0.20,
    ) -> None:
        self.root = Path(root) if root else None
        self.max_references = max(1, int(max_references))
        self.stable_frames = max(2, int(stable_frames))
        self.stable_similarity = float(stable_similarity)
        self.trim_changed_fraction = min(0.40, max(0.0, float(trim_changed_fraction)))
        self.references_by_class: dict[str, list[_Reference]] = {}
        self.references: dict[tuple[int, int], list[_Reference]] = {}
        self.pending: dict[str, list[_Pending]] = {}
        self.outdated_schema_detected = False
        self.outdated_schema_version: int | None = None
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
            self._load()

    @staticmethod
    def _difference_intensity(left: Any, right: Any) -> Any:
        import cv2
        import numpy as np

        if left is None or right is None or left.size == 0 or right.size == 0:
            return np.full((1,), 255.0, np.float32)
        if left.shape[:2] != right.shape[:2]:
            right = cv2.resize(
                right,
                (left.shape[1], left.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
        return cv2.absdiff(left[:, :, :3], right[:, :, :3]).max(axis=2).astype(np.float32)

    def similarity(self, left: Any, right: Any) -> float:
        """Robust similarity that ignores a small localized foreground overlay."""

        import numpy as np

        flattened = np.sort(self._difference_intensity(left, right).reshape(-1))
        keep = max(1, int(round(flattened.size * (1.0 - self.trim_changed_fraction))))
        robust_mean = float(flattened[:keep].mean())
        return max(0.0, min(1.0, 1.0 - robust_mean / 255.0))

    def raw_similarity(self, left: Any, right: Any) -> float:
        diff = self._difference_intensity(left, right)
        return max(0.0, min(1.0, 1.0 - float(diff.mean()) / 255.0))

    def choose(
        self,
        crop_or_world_cell: Any,
        crop: Any | None = None,
        terrain_class: str | None = None,
    ) -> BackgroundMatch:
        """Choose the closest known empty appearance.

        New production API: ``choose(crop, terrain_class="walkable")``.
        The old ``choose(world_cell, crop)`` form remains for compatibility and
        never participates in the enemy-perception runtime.
        """

        if crop is not None and isinstance(crop_or_world_cell, tuple):
            current = crop
            candidates = self.references.get(tuple(crop_or_world_cell), [])
        else:
            current = crop_or_world_cell
            if terrain_class is None:
                candidates = [
                    item
                    for bucket in self.references_by_class.values()
                    for item in bucket
                ]
            else:
                candidates = list(self.references_by_class.get(str(terrain_class), []))
        if not candidates:
            return BackgroundMatch(False)
        scored = [(self.similarity(current, item.image), item) for item in candidates]
        score, selected = max(scored, key=lambda item: item[0])
        selected.similarity_history.append(float(score))
        selected.similarity_history = selected.similarity_history[-32:]
        return BackgroundMatch(
            True,
            selected.id,
            score,
            selected.image.copy(),
            selected.terrain_class,
            selected.source_world_cell,
            self.raw_similarity(current, selected.image),
            selected.schema_version,
        )

    def observe_empty_candidate(
        self,
        world_cell: tuple[int, int] | None,
        terrain_class: str,
        crop: Any,
        eligible: bool,
        source_frame: int | None = None,
    ) -> str | None:
        if not eligible:
            return None
        existing = self.choose(crop, terrain_class=terrain_class)
        if existing.available and existing.confidence >= self.stable_similarity:
            return existing.reference_id

        bucket = self.pending.setdefault(terrain_class, [])
        selected: _Pending | None = None
        for pending in bucket:
            if self.similarity(crop, pending.image) >= self.stable_similarity:
                selected = pending
                break
        if selected is None:
            bucket.append(
                _Pending(
                    crop.copy(),
                    1,
                    terrain_class,
                    tuple(world_cell) if world_cell is not None else None,
                    source_frame,
                )
            )
            return None
        selected.count += 1
        if selected.count < self.stable_frames:
            return None
        bucket.remove(selected)
        return self.add_reference(
            selected.source_world_cell,
            terrain_class,
            selected.image,
            source_frame=selected.source_frame,
        )

    def add_reference(
        self,
        world_cell: tuple[int, int] | None,
        terrain_class: str,
        crop: Any,
        source_frame: int | None = None,
    ) -> str:
        reference = _Reference(
            id=f"bg-{uuid4().hex[:12]}",
            terrain_class=terrain_class,
            path=None,
            image=crop.copy(),
            source_world_cell=tuple(world_cell) if world_cell is not None else None,
            source_frame=source_frame,
        )
        bucket = self.references_by_class.setdefault(terrain_class, [])
        bucket.append(reference)
        while len(bucket) > self.max_references:
            removed = bucket.pop(0)
            self._remove_from_source_index(removed)
        if reference.source_world_cell is not None:
            source_bucket = self.references.setdefault(reference.source_world_cell, [])
            source_bucket.append(reference)
            while len(source_bucket) > self.max_references:
                source_bucket.pop(0)
        self._save_reference(reference)
        self._save_index()
        return reference.id

    def _remove_from_source_index(self, reference: _Reference) -> None:
        if reference.source_world_cell is None:
            return
        bucket = self.references.get(reference.source_world_cell, [])
        self.references[reference.source_world_cell] = [
            item for item in bucket if item.id != reference.id
        ]

    def _save_reference(self, reference: _Reference) -> None:
        if not self.root:
            return
        import cv2

        path = self.root / f"{reference.id}.png"
        if not cv2.imwrite(str(path), reference.image):
            raise OSError(f"Failed to write background reference: {path}")
        reference.path = path.name

    def _save_index(self) -> None:
        if not self.root:
            return
        payload = {
            "schema_version": SCHEMA_VERSION,
            "matching_semantics": "visual_similarity_within_terrain_class",
            "references": [
                {
                    "id": item.id,
                    "terrain_class": item.terrain_class,
                    "source_world_cell": (
                        list(item.source_world_cell)
                        if item.source_world_cell is not None
                        else None
                    ),
                    "created_at": item.created_at,
                    "source_frame": item.source_frame,
                    "similarity_history": item.similarity_history[-32:],
                    "path": item.path,
                    "schema_version": item.schema_version,
                }
                for bucket in self.references_by_class.values()
                for item in bucket
            ],
        }
        path = self.root / "index.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _load(self) -> None:
        import cv2

        path = self.root / "index.json"
        if not path.is_file():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema = int(payload.get("schema_version", 1))
        if schema != SCHEMA_VERSION:
            self.outdated_schema_detected = True
            self.outdated_schema_version = schema
            warning = self.root / "BACKGROUND_SCHEMA_OUTDATED.txt"
            warning.write_text(
                "Background references were not loaded because their schema uses "
                f"version {schema}; expected {SCHEMA_VERSION}. Run the laboratory "
                "with -ResetBackgroundReferences to start a clean visual catalogue.\n",
                encoding="utf-8",
            )
            return
        for item in payload.get("references", []):
            image_path = self.root / item["path"]
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            source = item.get("source_world_cell")
            reference = _Reference(
                id=str(item["id"]),
                terrain_class=str(item["terrain_class"]),
                path=str(item["path"]),
                image=image,
                source_world_cell=tuple(source) if source is not None else None,
                created_at=str(item.get("created_at") or datetime.now(timezone.utc).isoformat()),
                source_frame=item.get("source_frame"),
                similarity_history=[float(value) for value in item.get("similarity_history", [])],
                schema_version=int(item.get("schema_version", SCHEMA_VERSION)),
            )
            self.references_by_class.setdefault(reference.terrain_class, []).append(reference)
            if reference.source_world_cell is not None:
                self.references.setdefault(reference.source_world_cell, []).append(reference)
