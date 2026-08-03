from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import BackgroundMatch


SCHEMA_VERSION = 3


@dataclass(slots=True)
class _Reference:
    id: str
    cluster_id: str
    terrain_class: str
    path: str | None
    image: Any
    source: str = "taught_tile"
    source_world_cell: tuple[int, int] | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_frame: int | None = None
    similarity_history: list[float] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION


@dataclass(slots=True)
class _Cluster:
    id: str
    terrain_class: str
    source: str
    references: list[_Reference] = field(default_factory=list)
    observation_count: int = 0
    confirmed_empty_count: int = 0
    acceptance_threshold: float = 0.88


@dataclass(slots=True)
class _Pending:
    image: Any
    count: int
    terrain_class: str
    source_world_cell: tuple[int, int] | None
    source_frame: int | None


class BackgroundReferenceStore:
    """Visual empty-tile catalogue grouped by semantic class and appearance.

    The production question is: "Have I seen this empty tile, or something
    visually similar, before?" World coordinates are retained only as source
    metadata and never select the operational background.
    """

    def __init__(
        self,
        root: Path | None = None,
        max_references: int = 32,
        stable_frames: int = 3,
        stable_similarity: float = 0.985,
        trim_changed_fraction: float = 0.60,
        cluster_similarity: float = 0.94,
        max_representatives_per_cluster: int = 4,
    ) -> None:
        self.root = Path(root) if root else None
        self.max_references = max(1, int(max_references))
        self.stable_frames = max(2, int(stable_frames))
        self.stable_similarity = float(stable_similarity)
        self.trim_changed_fraction = min(0.75, max(0.0, float(trim_changed_fraction)))
        self.cluster_similarity = float(cluster_similarity)
        self.max_representatives_per_cluster = max(1, int(max_representatives_per_cluster))
        self.clusters_by_class: dict[str, list[_Cluster]] = {}
        # Compatibility indexes retained for older unit tests and diagnostics.
        self.references_by_class: dict[str, list[_Reference]] = {}
        self.references: dict[tuple[int, int], list[_Reference]] = {}
        self.pending: dict[str, list[_Pending]] = {}
        self.outdated_schema_detected = False
        self.outdated_schema_version: int | None = None
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
            self._load()

    @property
    def cluster_count(self) -> int:
        return sum(len(items) for items in self.clusters_by_class.values())

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
        """Robust score that tolerates a localized foreground sprite."""

        import numpy as np

        flattened = np.sort(self._difference_intensity(left, right).reshape(-1))
        keep = max(1, int(round(flattened.size * (1.0 - self.trim_changed_fraction))))
        robust_mean = float(flattened[:keep].mean())
        return max(0.0, min(1.0, 1.0 - robust_mean / 255.0))

    def raw_similarity(self, left: Any, right: Any) -> float:
        diff = self._difference_intensity(left, right)
        return max(0.0, min(1.0, 1.0 - float(diff.mean()) / 255.0))

    def _candidate_clusters(self, terrain_class: str | None) -> list[_Cluster]:
        if terrain_class is None:
            return [cluster for bucket in self.clusters_by_class.values() for cluster in bucket]
        return list(self.clusters_by_class.get(str(terrain_class), []))

    def choose(
        self,
        crop_or_world_cell: Any,
        crop: Any | None = None,
        terrain_class: str | None = None,
    ) -> BackgroundMatch:
        # Legacy coordinate lookup remains only for compatibility tests.
        if crop is not None and isinstance(crop_or_world_cell, tuple):
            current = crop
            candidates = self.references.get(tuple(crop_or_world_cell), [])
            if not candidates:
                return BackgroundMatch(False)
            scored = [(self.similarity(current, item.image), item) for item in candidates]
        else:
            current = crop_or_world_cell
            clusters = self._candidate_clusters(terrain_class)
            scored = [
                (self.similarity(current, reference.image), reference)
                for cluster in clusters
                for reference in cluster.references
            ]
        if not scored:
            return BackgroundMatch(False)
        score, selected = max(scored, key=lambda item: item[0])
        selected.similarity_history.append(float(score))
        selected.similarity_history = selected.similarity_history[-32:]
        return BackgroundMatch(
            available=True,
            reference_id=selected.id,
            confidence=float(score),
            image=selected.image.copy(),
            terrain_class=selected.terrain_class,
            source_world_cell=selected.source_world_cell,
            raw_similarity=self.raw_similarity(current, selected.image),
            schema_version=selected.schema_version,
            cluster_id=selected.cluster_id,
            source=selected.source,
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
            source="stable_observation",
        )

    def _select_cluster(self, terrain_class: str, crop: Any) -> _Cluster | None:
        best: tuple[float, _Cluster] | None = None
        for cluster in self.clusters_by_class.get(terrain_class, []):
            score = max(
                (self.raw_similarity(crop, ref.image) for ref in cluster.references),
                default=0.0,
            )
            if best is None or score > best[0]:
                best = (score, cluster)
        if best is not None and best[0] >= self.cluster_similarity:
            return best[1]
        return None

    def add_reference(
        self,
        world_cell: tuple[int, int] | None,
        terrain_class: str,
        crop: Any,
        source_frame: int | None = None,
        source: str = "taught_tile",
    ) -> str:
        cluster = self._select_cluster(terrain_class, crop)
        if cluster is None:
            cluster = _Cluster(
                id=f"bgc-{uuid4().hex[:12]}",
                terrain_class=terrain_class,
                source=source,
                observation_count=1,
                confirmed_empty_count=1,
            )
            self.clusters_by_class.setdefault(terrain_class, []).append(cluster)
        else:
            cluster.observation_count += 1
            cluster.confirmed_empty_count += 1
        reference = _Reference(
            id=f"bg-{uuid4().hex[:12]}",
            cluster_id=cluster.id,
            terrain_class=terrain_class,
            path=None,
            image=crop.copy(),
            source=source,
            source_world_cell=tuple(world_cell) if world_cell is not None else None,
            source_frame=source_frame,
        )
        cluster.references.append(reference)
        while len(cluster.references) > self.max_representatives_per_cluster:
            removed = cluster.references.pop(0)
            self._remove_reference_indexes(removed)
        class_bucket = self.references_by_class.setdefault(terrain_class, [])
        class_bucket.append(reference)
        while len(class_bucket) > self.max_references:
            removed = class_bucket.pop(0)
            self._remove_reference_from_clusters(removed)
            self._remove_reference_indexes(removed)
        if reference.source_world_cell is not None:
            self.references.setdefault(reference.source_world_cell, []).append(reference)
        self._save_reference(reference)
        self._save_index()
        return reference.id

    def _remove_reference_from_clusters(self, reference: _Reference) -> None:
        for cluster in self.clusters_by_class.get(reference.terrain_class, []):
            cluster.references = [item for item in cluster.references if item.id != reference.id]

    def _remove_reference_indexes(self, reference: _Reference) -> None:
        bucket = self.references_by_class.get(reference.terrain_class, [])
        self.references_by_class[reference.terrain_class] = [
            item for item in bucket if item.id != reference.id
        ]
        if reference.source_world_cell is not None:
            source_bucket = self.references.get(reference.source_world_cell, [])
            self.references[reference.source_world_cell] = [
                item for item in source_bucket if item.id != reference.id
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
            "matching_semantics": "semantic_class_plus_visual_cluster",
            "clusters": [
                {
                    "id": cluster.id,
                    "terrain_class": cluster.terrain_class,
                    "source": cluster.source,
                    "observation_count": cluster.observation_count,
                    "confirmed_empty_count": cluster.confirmed_empty_count,
                    "acceptance_threshold": cluster.acceptance_threshold,
                    "references": [
                        {
                            "id": item.id,
                            "path": item.path,
                            "source": item.source,
                            "source_world_cell": list(item.source_world_cell) if item.source_world_cell is not None else None,
                            "created_at": item.created_at,
                            "source_frame": item.source_frame,
                            "similarity_history": item.similarity_history[-32:],
                            "schema_version": item.schema_version,
                        }
                        for item in cluster.references
                    ],
                }
                for bucket in self.clusters_by_class.values()
                for cluster in bucket
            ],
        }
        path = self.root / "index.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
            (self.root / "BACKGROUND_SCHEMA_OUTDATED.txt").write_text(
                "Background references were not loaded because their schema uses "
                f"version {schema}; expected {SCHEMA_VERSION}. Run with "
                "-ResetBackgroundReferences to rebuild visual clusters.\n",
                encoding="utf-8",
            )
            return
        for item in payload.get("clusters", []):
            cluster = _Cluster(
                id=str(item["id"]),
                terrain_class=str(item["terrain_class"]),
                source=str(item.get("source", "taught_tile")),
                observation_count=int(item.get("observation_count", 0)),
                confirmed_empty_count=int(item.get("confirmed_empty_count", 0)),
                acceptance_threshold=float(item.get("acceptance_threshold", 0.88)),
            )
            for raw in item.get("references", []):
                image = cv2.imread(str(self.root / raw["path"]), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                source_cell = raw.get("source_world_cell")
                reference = _Reference(
                    id=str(raw["id"]),
                    cluster_id=cluster.id,
                    terrain_class=cluster.terrain_class,
                    path=str(raw["path"]),
                    image=image,
                    source=str(raw.get("source", cluster.source)),
                    source_world_cell=tuple(source_cell) if source_cell is not None else None,
                    created_at=str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
                    source_frame=raw.get("source_frame"),
                    similarity_history=[float(value) for value in raw.get("similarity_history", [])],
                    schema_version=int(raw.get("schema_version", SCHEMA_VERSION)),
                )
                cluster.references.append(reference)
                self.references_by_class.setdefault(cluster.terrain_class, []).append(reference)
                if reference.source_world_cell is not None:
                    self.references.setdefault(reference.source_world_cell, []).append(reference)
            if cluster.references:
                self.clusters_by_class.setdefault(cluster.terrain_class, []).append(cluster)
