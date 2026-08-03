from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import BackgroundMatch


@dataclass(slots=True)
class _Reference:
    id: str
    world_cell: tuple[int, int]
    terrain_class: str
    path: str | None
    image: Any


@dataclass(slots=True)
class _Pending:
    image: Any
    count: int
    terrain_class: str


class BackgroundReferenceStore:
    """Persistent empty-tile references with conservative multi-frame learning."""

    def __init__(
        self,
        root: Path | None = None,
        max_references: int = 4,
        stable_frames: int = 3,
        stable_similarity: float = 0.985,
    ) -> None:
        self.root = Path(root) if root else None
        self.max_references = max(1, int(max_references))
        self.stable_frames = max(2, int(stable_frames))
        self.stable_similarity = float(stable_similarity)
        self.references: dict[tuple[int, int], list[_Reference]] = {}
        self.pending: dict[tuple[int, int], _Pending] = {}
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
            self._load()

    @staticmethod
    def similarity(left: Any, right: Any) -> float:
        import cv2
        import numpy as np

        if left is None or right is None or left.size == 0 or right.size == 0:
            return 0.0
        if left.shape[:2] != right.shape[:2]:
            right = cv2.resize(
                right,
                (left.shape[1], left.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
        diff = cv2.absdiff(left[:, :, :3], right[:, :, :3]).astype(np.float32)
        return max(0.0, min(1.0, 1.0 - float(diff.mean()) / 255.0))

    def choose(self, world_cell: tuple[int, int] | None, crop: Any) -> BackgroundMatch:
        if world_cell is None:
            return BackgroundMatch(False)
        candidates = self.references.get(tuple(world_cell), [])
        if not candidates:
            return BackgroundMatch(False)
        scored = [(self.similarity(crop, item.image), item) for item in candidates]
        score, selected = max(scored, key=lambda item: item[0])
        return BackgroundMatch(True, selected.id, score, selected.image.copy())

    def observe_empty_candidate(
        self,
        world_cell: tuple[int, int] | None,
        terrain_class: str,
        crop: Any,
        eligible: bool,
    ) -> str | None:
        if world_cell is None or not eligible:
            return None
        key = tuple(world_cell)
        existing = self.choose(key, crop)
        if existing.available and existing.confidence >= self.stable_similarity:
            return existing.reference_id
        pending = self.pending.get(key)
        if (
            pending is None
            or pending.terrain_class != terrain_class
            or self.similarity(crop, pending.image) < self.stable_similarity
        ):
            self.pending[key] = _Pending(crop.copy(), 1, terrain_class)
            return None
        pending.count += 1
        if pending.count < self.stable_frames:
            return None
        reference_id = f"bg-{uuid4().hex[:12]}"
        reference = _Reference(
            reference_id,
            key,
            terrain_class,
            None,
            pending.image.copy(),
        )
        bucket = self.references.setdefault(key, [])
        bucket.append(reference)
        del self.pending[key]
        if len(bucket) > self.max_references:
            bucket.pop(0)
        self._save_reference(reference)
        self._save_index()
        return reference_id

    def add_reference(self, world_cell: tuple[int, int], terrain_class: str, crop: Any) -> str:
        reference_id = f"bg-{uuid4().hex[:12]}"
        reference = _Reference(
            reference_id,
            tuple(world_cell),
            terrain_class,
            None,
            crop.copy(),
        )
        bucket = self.references.setdefault(tuple(world_cell), [])
        bucket.append(reference)
        if len(bucket) > self.max_references:
            bucket.pop(0)
        self._save_reference(reference)
        self._save_index()
        return reference_id

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
            "schema_version": 1,
            "references": [
                {
                    "id": item.id,
                    "world_cell": list(item.world_cell),
                    "terrain_class": item.terrain_class,
                    "path": item.path,
                }
                for bucket in self.references.values()
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
        for item in payload.get("references", []):
            image_path = self.root / item["path"]
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            reference = _Reference(
                item["id"],
                tuple(item["world_cell"]),
                item["terrain_class"],
                item["path"],
                image,
            )
            self.references.setdefault(reference.world_cell, []).append(reference)
