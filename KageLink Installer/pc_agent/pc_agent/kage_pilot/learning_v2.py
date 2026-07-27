from __future__ import annotations

import io
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image

from .dataset import DatasetStore, Sample

MODEL_VERSION = 2
FEATURE_SIZE = (24, 14)
IDLE_LABEL = "idle"
NAV_KEYS = frozenset({"up", "down", "left", "right"})
MAX_EXEMPLARS_PER_LABEL = 64


def _key_set(keys: Iterable[str]) -> set[str]:
    return {str(key).strip().lower() for key in keys if str(key).strip()}


def _label(keys: Iterable[str]) -> str:
    normalized = sorted(_key_set(keys))
    return "+".join(normalized) if normalized else IDLE_LABEL


def _label_keys(label: str) -> tuple[str, ...]:
    value = str(label).strip().lower()
    return () if value in {"", IDLE_LABEL} else tuple(part for part in value.split("+") if part)


def _gray_vector(jpeg: bytes) -> list[float]:
    with Image.open(io.BytesIO(jpeg)) as image:
        gray = image.convert("L").resize(FEATURE_SIZE, Image.Resampling.BILINEAR)
        pixels = gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata()
        return [float(pixel) / 255.0 for pixel in pixels]


def temporal_features(previous_jpeg: bytes, current_jpeg: bytes) -> list[float]:
    """Encode current appearance plus signed visual change from the previous frame."""
    previous = _gray_vector(previous_jpeg)
    current = _gray_vector(current_jpeg)
    delta = [now - before for before, now in zip(previous, current)]
    return current + delta


def _distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / max(1, len(a)))


@dataclass(frozen=True, slots=True)
class PolicyPrediction:
    label: str
    keys: tuple[str, ...]
    confidence: float
    distance: float


class PrototypePolicy:
    """Class-balanced nearest-exemplar policy with centroid fallback.

    v0.2 originally compared a frame only with the mean image of each action.
    That made the very diverse `idle` state produce a broad/generic centroid.
    We still persist centroids for backwards compatibility, but new models also
    persist representative real action-run examples and score every class by
    its nearest example. Counts therefore do not vote for a class.
    """

    def __init__(
        self,
        prototypes: dict[str, list[float]],
        counts: dict[str, int] | None = None,
        exemplars: dict[str, list[list[float]]] | None = None,
    ) -> None:
        if not prototypes:
            raise ValueError("EMPTY_POLICY")
        expected = FEATURE_SIZE[0] * FEATURE_SIZE[1] * 2
        for label, vector in prototypes.items():
            if len(vector) != expected:
                raise ValueError(f"INVALID_POLICY_PROTOTYPE:{label}")
        self.prototypes = {str(k): [float(v) for v in values] for k, values in prototypes.items()}
        self.counts = {str(k): int(v) for k, v in (counts or {}).items()}
        self.exemplars: dict[str, list[list[float]]] = {}
        for label, vectors in (exemplars or {}).items():
            normalized_vectors: list[list[float]] = []
            for vector in vectors:
                if len(vector) != expected:
                    raise ValueError(f"INVALID_POLICY_EXEMPLAR:{label}")
                normalized_vectors.append([float(v) for v in vector])
            if normalized_vectors:
                self.exemplars[str(label)] = normalized_vectors

    @classmethod
    def from_examples(cls, examples: Iterable[tuple[str, list[float]]]) -> "PrototypePolicy":
        sums: dict[str, list[float]] = {}
        counts: dict[str, int] = defaultdict(int)
        exemplars: dict[str, list[list[float]]] = defaultdict(list)
        accepted = 0
        for label, vector in examples:
            if label not in sums:
                sums[label] = [0.0] * len(vector)
            for index, value in enumerate(vector):
                sums[label][index] += value
            counts[label] += 1
            accepted += 1
            bucket = exemplars[label]
            if len(bucket) < MAX_EXEMPLARS_PER_LABEL:
                bucket.append(list(vector))
            else:
                # Deterministic reservoir-like spacing: replace slots as the
                # class grows so long demonstrations do not preserve only the
                # earliest examples.
                slot = counts[label] % MAX_EXEMPLARS_PER_LABEL
                bucket[slot] = list(vector)
        if accepted == 0:
            raise ValueError("NO_POLICY_SAMPLES")
        prototypes = {
            label: [value / counts[label] for value in vector]
            for label, vector in sums.items()
        }
        return cls(prototypes, dict(counts), dict(exemplars))

    def predict_features(self, vector: list[float]) -> PolicyPrediction:
        ranked: list[tuple[float, str]] = []
        for label, prototype in self.prototypes.items():
            candidates = self.exemplars.get(label)
            if candidates:
                distance = min(_distance(vector, exemplar) for exemplar in candidates)
            else:
                distance = _distance(vector, prototype)
            ranked.append((distance, label))
        ranked.sort(key=lambda item: (item[0], item[1]))
        best_distance, best_label = ranked[0]
        if len(ranked) == 1:
            confidence = 1.0
        else:
            second_distance = ranked[1][0]
            confidence = max(0.0, min(1.0, (second_distance - best_distance) / max(second_distance, 1e-9)))
        return PolicyPrediction(
            label=best_label,
            keys=_label_keys(best_label),
            confidence=confidence,
            distance=best_distance,
        )

    def to_dict(self) -> dict:
        return {
            "prototypes": self.prototypes,
            "counts": self.counts,
            "exemplars": self.exemplars,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "PrototypePolicy":
        return cls(payload["prototypes"], payload.get("counts"), payload.get("exemplars"))


@dataclass(frozen=True, slots=True)
class CombatPrediction:
    navigation: PolicyPrediction
    skill: PolicyPrediction


class TemporalCombatModel:
    """Kage Pilot v0.2 combat model: temporal navigation + independent skill policy."""

    def __init__(
        self,
        navigation: PrototypePolicy,
        skill: PrototypePolicy,
        *,
        base_keys: Iterable[str] = ("r",),
        skill_keys: Iterable[str] = ("h",),
        post_combat_keys: Iterable[str] = ("v",),
        history_frames: int = 2,
    ) -> None:
        self.navigation = navigation
        self.skill = skill
        self.base_keys = tuple(sorted(_key_set(base_keys)))
        self.skill_keys = tuple(sorted(_key_set(skill_keys)))
        self.post_combat_keys = tuple(sorted(_key_set(post_combat_keys)))
        self.history_frames = max(1, int(history_frames))

    @classmethod
    def train(
        cls,
        store: DatasetStore,
        *,
        results: Iterable[str] = ("victory",),
        base_keys: Iterable[str] = ("r",),
        skill_keys: Iterable[str] = ("h",),
        post_combat_keys: Iterable[str] = ("v",),
        stride: int = 1,
        history_frames: int = 2,
    ) -> "TemporalCombatModel":
        base = _key_set(base_keys)
        skills = _key_set(skill_keys)
        post_combat = _key_set(post_combat_keys)
        stride = max(1, int(stride))
        history = max(1, int(history_frames))
        nav_examples: list[tuple[str, list[float]]] = []
        skill_examples: list[tuple[str, list[float]]] = []

        for session_path in store.session_paths(results=results):
            samples = list(store.samples(session_path))
            if not samples:
                continue
            by_index = {sample.index: sample for sample in samples}
            actions_path = Path(session_path) / "actions.jsonl"
            if not actions_path.exists():
                continue
            run_index = 0
            with actions_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    raw = json.loads(line)
                    raw_keys = _key_set(raw.get("keys", ()))

                    # In Shinobi Story Online V is meditation/rest after the
                    # fight. Once a post-combat key appears in a victorious
                    # demonstration, the remaining tail is not combat data.
                    if raw_keys.intersection(post_combat):
                        break

                    take = run_index % stride == 0
                    run_index += 1
                    if not take:
                        continue
                    start_index = int(raw.get("start_index", 0))
                    current = by_index.get(start_index)
                    if current is None:
                        continue
                    previous = _nearest_previous(by_index, start_index, history) or current
                    current_jpeg = (Path(session_path) / current.frame).read_bytes()
                    previous_jpeg = (Path(session_path) / previous.frame).read_bytes()
                    features = temporal_features(previous_jpeg, current_jpeg)

                    keys = raw_keys.difference(base).difference(post_combat)
                    nav_label = _label(keys.intersection(NAV_KEYS))
                    skill_label = _label(keys.intersection(skills))
                    nav_examples.append((nav_label, features))
                    skill_examples.append((skill_label, features))

        if not nav_examples or not skill_examples:
            raise ValueError("NO_V2_TRAINING_SAMPLES")
        return cls(
            PrototypePolicy.from_examples(nav_examples),
            PrototypePolicy.from_examples(skill_examples),
            base_keys=base,
            skill_keys=skills,
            post_combat_keys=post_combat,
            history_frames=history,
        )

    def predict(self, previous_jpeg: bytes, current_jpeg: bytes) -> CombatPrediction:
        features = temporal_features(previous_jpeg, current_jpeg)
        return CombatPrediction(
            navigation=self.navigation.predict_features(features),
            skill=self.skill.predict_features(features),
        )

    def save(self, path: Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_version": MODEL_VERSION,
            "feature_size": list(FEATURE_SIZE),
            "base_keys": list(self.base_keys),
            "skill_keys": list(self.skill_keys),
            "post_combat_keys": list(self.post_combat_keys),
            "history_frames": self.history_frames,
            "navigation": self.navigation.to_dict(),
            "skill": self.skill.to_dict(),
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output

    @classmethod
    def load(cls, path: Path) -> "TemporalCombatModel":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(payload.get("model_version", 0)) != MODEL_VERSION:
            raise ValueError("UNSUPPORTED_V2_MODEL_VERSION")
        if tuple(payload.get("feature_size", ())) != FEATURE_SIZE:
            raise ValueError("UNSUPPORTED_V2_FEATURE_SIZE")
        return cls(
            PrototypePolicy.from_dict(payload["navigation"]),
            PrototypePolicy.from_dict(payload["skill"]),
            base_keys=payload.get("base_keys", ("r",)),
            skill_keys=payload.get("skill_keys", ("h",)),
            post_combat_keys=payload.get("post_combat_keys", ("v",)),
            history_frames=int(payload.get("history_frames", 2)),
        )


def _nearest_previous(by_index: dict[int, Sample], start_index: int, history_frames: int) -> Sample | None:
    target = max(0, int(start_index) - max(1, int(history_frames)))
    for index in range(target, -1, -1):
        sample = by_index.get(index)
        if sample is not None:
            return sample
    return None
