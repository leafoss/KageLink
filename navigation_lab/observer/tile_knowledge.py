from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class TileClass(str, Enum):
    UNKNOWN = "unknown"
    WALKABLE = "walkable"
    WALL = "wall"
    WALKABLE_WITH_JUTSU = "walkable_with_jutsu"
    BLOCKING_OBJECT = "blocking_object"
    PLAYER = "player"
    NPC = "npc"
    TRANSITION = "transition"
    DANGER = "danger"
    IGNORE_DYNAMIC = "ignore_dynamic"


TILE_CLASS_LABELS_PT_BR: dict[TileClass, str] = {
    TileClass.UNKNOWN: "Desconhecido",
    TileClass.WALKABLE: "Caminhável",
    TileClass.WALL: "Parede",
    TileClass.WALKABLE_WITH_JUTSU: "Caminhável com jutsu",
    TileClass.BLOCKING_OBJECT: "Bloqueia caminho",
    TileClass.PLAYER: "Jogador / Player",
    TileClass.NPC: "NPC",
    TileClass.TRANSITION: "Transição",
    TileClass.DANGER: "Perigoso",
    TileClass.IGNORE_DYNAMIC: "Ignorar / dinâmico",
}


@dataclass(slots=True)
class TileExample:
    id: str
    category: TileClass
    feature: list[float]
    crop_path: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["category"] = self.category.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TileExample":
        return cls(
            id=str(payload["id"]),
            category=TileClass(str(payload["category"])),
            feature=[float(value) for value in payload.get("feature", [])],
            crop_path=payload.get("crop_path"),
            created_at=str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
            notes=payload.get("notes"),
        )


@dataclass(frozen=True, slots=True)
class TileClassification:
    category: TileClass
    confidence: float
    known: bool
    matched_example_id: str | None = None


class TileFeatureExtractor:
    """Build a compact explainable visual descriptor for one square tile crop."""

    def __init__(self, normalized_size: int = 32) -> None:
        if normalized_size < 16:
            raise ValueError("normalized_size must be at least 16")
        self.normalized_size = int(normalized_size)

    def extract(self, crop: Any) -> list[float]:
        import cv2
        import numpy as np

        if crop is None or not hasattr(crop, "shape") or crop.size == 0:
            raise ValueError("crop must be a non-empty image")
        if len(crop.shape) == 2:
            bgr = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        elif len(crop.shape) == 3 and crop.shape[2] >= 3:
            bgr = crop[:, :, :3]
        else:
            raise ValueError("crop must be grayscale or BGR-compatible")

        resized = cv2.resize(
            bgr,
            (self.normalized_size, self.normalized_size),
            interpolation=cv2.INTER_AREA,
        )
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        color_histogram = cv2.calcHist(
            [hsv],
            [0, 1],
            None,
            [12, 4],
            [0, 180, 0, 256],
        ).reshape(-1)
        color_histogram = color_histogram / max(float(color_histogram.sum()), 1e-9)

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        structure = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        structure = structure.reshape(-1)
        structure = structure - float(structure.mean())
        structure_std = float(structure.std())
        if structure_std > 1e-6:
            structure = structure / structure_std

        edges = cv2.Canny(gray, 45, 135)
        edge_blocks: list[float] = []
        for row in range(4):
            for column in range(4):
                y0 = row * edges.shape[0] // 4
                y1 = (row + 1) * edges.shape[0] // 4
                x0 = column * edges.shape[1] // 4
                x1 = (column + 1) * edges.shape[1] // 4
                edge_blocks.append(float(edges[y0:y1, x0:x1].mean()) / 255.0)

        means, deviations = cv2.meanStdDev(resized)
        color_statistics = [
            *(float(value) / 255.0 for value in means.reshape(-1)[:3]),
            *(float(value) / 255.0 for value in deviations.reshape(-1)[:3]),
        ]

        vector = np.concatenate(
            [
                color_histogram.astype(np.float32),
                structure.astype(np.float32),
                np.asarray(edge_blocks, dtype=np.float32),
                np.asarray(color_statistics, dtype=np.float32),
            ]
        )
        norm = float(np.linalg.norm(vector))
        if norm > 1e-9:
            vector = vector / norm
        return [float(value) for value in vector]

    @staticmethod
    def similarity(left: list[float], right: list[float]) -> float:
        import numpy as np

        if not left or len(left) != len(right):
            return 0.0
        left_array = np.asarray(left, dtype=np.float32)
        right_array = np.asarray(right, dtype=np.float32)
        denominator = float(np.linalg.norm(left_array) * np.linalg.norm(right_array))
        if denominator <= 1e-9:
            return 0.0
        cosine = float(np.dot(left_array, right_array) / denominator)
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


class TileKnowledgeBase:
    def __init__(
        self,
        examples: list[TileExample] | None = None,
        similarity_threshold: float = 0.92,
        extractor: TileFeatureExtractor | None = None,
    ) -> None:
        if not 0.50 <= float(similarity_threshold) <= 1.0:
            raise ValueError("similarity_threshold must be between 0.50 and 1.0")
        self.examples = list(examples or [])
        self.similarity_threshold = float(similarity_threshold)
        self.extractor = extractor or TileFeatureExtractor()

    def classify(self, crop: Any, threshold: float | None = None) -> TileClassification:
        return self.classify_feature(self.extractor.extract(crop), threshold=threshold)

    def classify_feature(
        self,
        feature: list[float],
        threshold: float | None = None,
    ) -> TileClassification:
        required = self.similarity_threshold if threshold is None else float(threshold)
        best_example: TileExample | None = None
        best_score = 0.0
        for example in self.examples:
            score = self.extractor.similarity(feature, example.feature)
            if score > best_score:
                best_score = score
                best_example = example
        if best_example is None or best_score < required:
            return TileClassification(TileClass.UNKNOWN, best_score, False, None)
        return TileClassification(best_example.category, best_score, True, best_example.id)

    def add_example(
        self,
        crop: Any,
        category: TileClass,
        crop_path: str | None = None,
        notes: str | None = None,
    ) -> TileExample:
        if category == TileClass.UNKNOWN:
            raise ValueError("UNKNOWN cannot be stored as a taught category")
        example = TileExample(
            id=uuid4().hex[:16],
            category=category,
            feature=self.extractor.extract(crop),
            crop_path=crop_path,
            notes=notes,
        )
        self.examples.append(example)
        return example

    def remove_example(self, example_id: str) -> bool:
        before = len(self.examples)
        self.examples = [example for example in self.examples if example.id != example_id]
        return len(self.examples) != before

    def counts(self) -> dict[TileClass, int]:
        result = {category: 0 for category in TileClass if category != TileClass.UNKNOWN}
        for example in self.examples:
            result[example.category] = result.get(example.category, 0) + 1
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "similarity_threshold": self.similarity_threshold,
            "examples": [example.to_dict() for example in self.examples],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TileKnowledgeBase":
        return cls(
            examples=[TileExample.from_dict(item) for item in payload.get("examples", [])],
            similarity_threshold=float(payload.get("similarity_threshold", 0.92)),
        )
