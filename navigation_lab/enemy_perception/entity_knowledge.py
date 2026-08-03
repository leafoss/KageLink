from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from .entity_features import EntityFeatureExtractor
from .models import EntityClass, EntityClassification


@dataclass(slots=True)
class EntityExample:
    id: str
    category: EntityClass
    feature: list[float]
    crop_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "feature": self.feature,
            "crop_path": self.crop_path,
        }


@dataclass(slots=True)
class UnknownEntityGroup:
    id: str
    feature: list[float]
    count: int
    first_seen_frame: int
    last_seen_frame: int
    crop_path: str | None = None


class EntityKnowledgeBase:
    """Entity examples and grouped unknowns, persisted separately from terrain knowledge."""

    def __init__(
        self,
        root: Path | None = None,
        auto_threshold: float = 0.95,
        review_threshold: float = 0.90,
        grouping_threshold: float = 0.965,
    ) -> None:
        self.root = Path(root) if root else None
        self.auto_threshold = float(auto_threshold)
        self.review_threshold = float(review_threshold)
        self.grouping_threshold = float(grouping_threshold)
        self.extractor = EntityFeatureExtractor()
        self.examples: list[EntityExample] = []
        self.unknown_groups: dict[str, UnknownEntityGroup] = {}
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
            self._load()

    def classify_feature(self, feature: list[float]) -> EntityClassification:
        best: EntityExample | None = None
        score = 0.0
        for example in self.examples:
            similarity = self.extractor.similarity(feature, example.feature)
            if similarity > score:
                score = similarity
                best = example
        if best is None or score < self.review_threshold:
            return EntityClassification(EntityClass.UNKNOWN_ENTITY, score, False, None)
        return EntityClassification(best.category, score, True, best.id)

    def add_example(
        self,
        crop: Any,
        mask: Any,
        category: EntityClass,
    ) -> EntityExample:
        if category == EntityClass.UNKNOWN_ENTITY:
            raise ValueError("UNKNOWN_ENTITY cannot be taught")
        example = EntityExample(
            uuid4().hex[:16],
            category,
            self.extractor.extract(crop, mask),
        )
        self.examples.append(example)
        if self.root:
            import cv2

            directory = self.root / "examples"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{example.id}.png"
            if not cv2.imwrite(str(path), crop):
                raise OSError(f"Failed to save entity example: {path}")
            example.crop_path = str(path.relative_to(self.root))
            self._save()
        return example

    def group_unknown(
        self,
        feature: list[float],
        crop: Any,
        frame_index: int,
    ) -> UnknownEntityGroup:
        selected: UnknownEntityGroup | None = None
        for group in self.unknown_groups.values():
            if self.extractor.similarity(feature, group.feature) >= self.grouping_threshold:
                selected = group
                break
        if selected is None:
            selected = UnknownEntityGroup(
                uuid4().hex[:16],
                list(feature),
                1,
                frame_index,
                frame_index,
            )
            self.unknown_groups[selected.id] = selected
            if self.root:
                import cv2

                directory = self.root / "unknown"
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / f"{selected.id}.png"
                if not cv2.imwrite(str(path), crop):
                    raise OSError(f"Failed to save unknown entity: {path}")
                selected.crop_path = str(path.relative_to(self.root))
        else:
            selected.count += 1
            selected.last_seen_frame = frame_index
        self._save()
        return selected

    def _save(self) -> None:
        if not self.root:
            return
        payload = {
            "schema_version": 1,
            "examples": [item.to_dict() for item in self.examples],
            "unknown_groups": [
                {
                    "id": item.id,
                    "feature": item.feature,
                    "count": item.count,
                    "first_seen_frame": item.first_seen_frame,
                    "last_seen_frame": item.last_seen_frame,
                    "crop_path": item.crop_path,
                }
                for item in self.unknown_groups.values()
            ],
        }
        path = self.root / "index.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _load(self) -> None:
        path = self.root / "index.json"
        if not path.is_file():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.examples = [
            EntityExample(
                item["id"],
                EntityClass(item["category"]),
                item["feature"],
                item.get("crop_path"),
            )
            for item in payload.get("examples", [])
        ]
        self.unknown_groups = {
            item["id"]: UnknownEntityGroup(**item)
            for item in payload.get("unknown_groups", [])
        }
