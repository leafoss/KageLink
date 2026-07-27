from __future__ import annotations

import io
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from PIL import Image

from .dataset import DatasetStore, Sample

FEATURE_SIZE = (16, 9)
MODEL_VERSION = 1
IDLE_LABEL = "idle"


def _normalized_key_set(keys: Iterable[str]) -> set[str]:
    return {str(key).strip().lower() for key in keys if str(key).strip()}


def action_label(keys: Iterable[str], *, exclude_keys: Iterable[str] = ()) -> str:
    excluded = _normalized_key_set(exclude_keys)
    normalized = sorted(_normalized_key_set(keys).difference(excluded))
    return "+".join(normalized) if normalized else IDLE_LABEL


def label_keys(label: str) -> tuple[str, ...]:
    normalized = str(label).strip().lower()
    return () if normalized in {"", IDLE_LABEL} else tuple(part for part in normalized.split("+") if part)


def frame_features(jpeg: bytes) -> list[float]:
    with Image.open(io.BytesIO(jpeg)) as image:
        gray = image.convert("L").resize(FEATURE_SIZE, Image.Resampling.BILINEAR)
        pixels = gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata()
        return [pixel / 255.0 for pixel in pixels]


@dataclass(frozen=True, slots=True)
class Prediction:
    label: str
    keys: tuple[str, ...]
    confidence: float
    distance: float


class BehaviorCloner:
    """Small dependency-free behavioral-cloning baseline using visual action prototypes."""

    def __init__(self, prototypes: dict[str, list[float]], counts: dict[str, int] | None = None) -> None:
        if not prototypes:
            raise ValueError("EMPTY_MODEL")
        expected = FEATURE_SIZE[0] * FEATURE_SIZE[1]
        for label, vector in prototypes.items():
            if len(vector) != expected:
                raise ValueError(f"INVALID_PROTOTYPE:{label}")
        self.prototypes = {str(k): [float(v) for v in values] for k, values in prototypes.items()}
        self.counts = {str(k): int(v) for k, v in (counts or {}).items()}

    @classmethod
    def train(
        cls,
        store: DatasetStore,
        *,
        results: Iterable[str] = ("victory",),
        stride: int = 1,
        include_idle: bool = True,
        exclude_keys: Iterable[str] = (),
        use_action_runs: bool = True,
    ) -> "BehaviorCloner":
        stride = max(1, int(stride))
        excluded = tuple(sorted(_normalized_key_set(exclude_keys)))
        sums: dict[str, list[float]] = {}
        counts: dict[str, int] = defaultdict(int)
        accepted = 0

        for session_path in store.session_paths(results=results):
            examples = (
                _action_run_examples(store, session_path, stride=stride, exclude_keys=excluded)
                if use_action_runs
                else _frame_examples(store, session_path, stride=stride, exclude_keys=excluded)
            )
            for sample, label in examples:
                if not include_idle and label == IDLE_LABEL:
                    continue
                jpeg = (session_path / sample.frame).read_bytes()
                vector = frame_features(jpeg)
                if label not in sums:
                    sums[label] = [0.0] * len(vector)
                for index, value in enumerate(vector):
                    sums[label][index] += value
                counts[label] += 1
                accepted += 1

        if accepted == 0:
            raise ValueError("NO_TRAINING_SAMPLES")
        prototypes = {
            label: [value / counts[label] for value in vector]
            for label, vector in sums.items()
        }
        return cls(prototypes, dict(counts))

    def predict(self, jpeg: bytes) -> Prediction:
        vector = frame_features(jpeg)
        ranked: list[tuple[float, str]] = []
        for label, prototype in self.prototypes.items():
            distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(vector, prototype)) / len(vector))
            ranked.append((distance, label))
        ranked.sort(key=lambda item: (item[0], item[1]))
        best_distance, best_label = ranked[0]
        if len(ranked) == 1:
            confidence = 1.0
        else:
            second_distance = ranked[1][0]
            confidence = max(0.0, min(1.0, (second_distance - best_distance) / max(second_distance, 1e-9)))
        return Prediction(
            label=best_label,
            keys=label_keys(best_label),
            confidence=confidence,
            distance=best_distance,
        )

    def save(self, path: Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_version": MODEL_VERSION,
            "feature_size": list(FEATURE_SIZE),
            "prototypes": self.prototypes,
            "counts": self.counts,
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output

    @classmethod
    def load(cls, path: Path) -> "BehaviorCloner":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(payload.get("model_version", 0)) != MODEL_VERSION:
            raise ValueError("UNSUPPORTED_MODEL_VERSION")
        if tuple(payload.get("feature_size", ())) != FEATURE_SIZE:
            raise ValueError("UNSUPPORTED_FEATURE_SIZE")
        return cls(payload["prototypes"], payload.get("counts"))


def _frame_examples(
    store: DatasetStore,
    session_path: Path,
    *,
    stride: int,
    exclude_keys: Iterable[str],
) -> Iterator[tuple[Sample, str]]:
    for sample in store.samples(session_path):
        if sample.index % stride:
            continue
        yield sample, action_label(sample.keys, exclude_keys=exclude_keys)


def _action_run_examples(
    store: DatasetStore,
    session_path: Path,
    *,
    stride: int,
    exclude_keys: Iterable[str],
) -> Iterator[tuple[Sample, str]]:
    """Yield one representative frame per contiguous action run.

    A key held for several seconds should not receive dozens of training votes
    only because the Recorder samples the keyboard at roughly 10 FPS.
    """
    actions_path = Path(session_path) / "actions.jsonl"
    if not actions_path.exists():
        yield from _frame_examples(store, session_path, stride=stride, exclude_keys=exclude_keys)
        return

    samples_by_index = {sample.index: sample for sample in store.samples(session_path)}
    run_index = 0
    with actions_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            take = run_index % stride == 0
            run_index += 1
            if not take:
                continue
            sample = samples_by_index.get(int(raw["start_index"]))
            if sample is None:
                continue
            yield sample, action_label(raw.get("keys", ()), exclude_keys=exclude_keys)
