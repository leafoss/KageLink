from __future__ import annotations

import io
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageFilter

from .dataset import DatasetStore, Sample
from .learning_v2 import CombatPrediction, IDLE_LABEL, NAV_KEYS, PolicyPrediction

MODEL_VERSION = 1
FEATURE_MODE = "arena_spatial_edges_v1"
SPATIAL_SIZE = (32, 18)
MOTION_GRID = (8, 4)
ARENA_CROP = (0.04, 0.04, 0.96, 0.86)
MAX_EXEMPLARS_PER_LABEL = 64
STD_FLOOR = 0.05


def _key_set(keys: Iterable[str]) -> set[str]:
    return {str(key).strip().lower() for key in keys if str(key).strip()}


def _label(keys: Iterable[str]) -> str:
    normalized = sorted(_key_set(keys))
    return "+".join(normalized) if normalized else IDLE_LABEL


def _label_keys(label: str) -> tuple[str, ...]:
    value = str(label).strip().lower()
    return () if value in {"", IDLE_LABEL} else tuple(part for part in value.split("+") if part)


def _crop_box(image: Image.Image) -> tuple[int, int, int, int]:
    width, height = image.size
    left = max(0, min(width - 1, round(width * ARENA_CROP[0])))
    top = max(0, min(height - 1, round(height * ARENA_CROP[1])))
    right = max(left + 1, min(width, round(width * ARENA_CROP[2])))
    bottom = max(top + 1, min(height, round(height * ARENA_CROP[3])))
    return left, top, right, bottom


def _prepare_gray(jpeg: bytes, size: tuple[int, int]) -> Image.Image:
    with Image.open(io.BytesIO(jpeg)) as image:
        gray = image.convert("L")
        gray = gray.crop(_crop_box(gray))
        return gray.resize(size, Image.Resampling.BILINEAR)


def _pixels(image: Image.Image) -> list[float]:
    values = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
    return [float(value) / 255.0 for value in values]


def spatial_features(previous_jpeg: bytes, current_jpeg: bytes) -> list[float]:
    """Encode arena-local appearance and motion instead of the full static frame.

    Channel 1 is a high-pass/edge representation of the current arena. This
    suppresses broad static brightness and keeps sprite/shape boundaries.
    Channel 2 is amplified signed temporal change, so knockback and reposition
    motion contribute much more than in the legacy full-frame grayscale model.
    Coarse absolute-motion grid statistics are appended to retain where change
    happened even after the image is downsampled.
    """

    previous = _prepare_gray(previous_jpeg, SPATIAL_SIZE)
    current = _prepare_gray(current_jpeg, SPATIAL_SIZE)

    blurred = current.filter(ImageFilter.GaussianBlur(radius=1.2))
    edges = ImageChops.difference(current, blurred)
    edge_values = [min(1.0, value * 4.0) for value in _pixels(edges)]

    previous_values = _pixels(previous)
    current_values = _pixels(current)
    signed_delta = [max(-1.0, min(1.0, (now - before) * 3.0)) for before, now in zip(previous_values, current_values)]

    previous_motion = _prepare_gray(previous_jpeg, MOTION_GRID)
    current_motion = _prepare_gray(current_jpeg, MOTION_GRID)
    coarse_before = _pixels(previous_motion)
    coarse_now = _pixels(current_motion)
    coarse_abs = [min(1.0, abs(now - before) * 4.0) for before, now in zip(coarse_before, coarse_now)]

    grid_w, grid_h = MOTION_GRID
    horizontal = []
    for x in range(grid_w):
        column = [coarse_abs[y * grid_w + x] for y in range(grid_h)]
        horizontal.append(sum(column) / max(1, len(column)))
    vertical = []
    for y in range(grid_h):
        row = coarse_abs[y * grid_w:(y + 1) * grid_w]
        vertical.append(sum(row) / max(1, len(row)))

    return edge_values + signed_delta + coarse_abs + horizontal + vertical


def _distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / max(1, len(a)))


@dataclass(frozen=True, slots=True)
class FeatureScaler:
    mean: list[float]
    std: list[float]

    @classmethod
    def fit(cls, vectors: Iterable[list[float]]) -> "FeatureScaler":
        data = [list(vector) for vector in vectors]
        if not data:
            raise ValueError("NO_SPATIAL_FEATURES")
        width = len(data[0])
        if any(len(vector) != width for vector in data):
            raise ValueError("INCONSISTENT_SPATIAL_FEATURES")
        mean = [0.0] * width
        for vector in data:
            for index, value in enumerate(vector):
                mean[index] += value
        count = float(len(data))
        mean = [value / count for value in mean]
        variance = [0.0] * width
        for vector in data:
            for index, value in enumerate(vector):
                delta = value - mean[index]
                variance[index] += delta * delta
        std = [max(STD_FLOOR, math.sqrt(value / count)) for value in variance]
        return cls(mean, std)

    def transform(self, vector: list[float]) -> list[float]:
        if len(vector) != len(self.mean):
            raise ValueError("SPATIAL_FEATURE_SIZE_MISMATCH")
        return [max(-6.0, min(6.0, (value - mean) / std)) for value, mean, std in zip(vector, self.mean, self.std)]

    def to_dict(self) -> dict:
        return {"mean": self.mean, "std": self.std}

    @classmethod
    def from_dict(cls, payload: dict) -> "FeatureScaler":
        return cls([float(v) for v in payload["mean"]], [float(v) for v in payload["std"]])


class SpatialPolicy:
    def __init__(self, exemplars: dict[str, list[list[float]]], counts: dict[str, int] | None = None) -> None:
        if not exemplars:
            raise ValueError("EMPTY_SPATIAL_POLICY")
        self.exemplars = {
            str(label): [[float(value) for value in vector] for vector in vectors]
            for label, vectors in exemplars.items()
            if vectors
        }
        if not self.exemplars:
            raise ValueError("EMPTY_SPATIAL_POLICY")
        self.counts = {str(label): int(value) for label, value in (counts or {}).items()}

    @classmethod
    def from_examples(cls, examples: Iterable[tuple[str, list[float]]]) -> "SpatialPolicy":
        buckets: dict[str, list[list[float]]] = defaultdict(list)
        counts: dict[str, int] = defaultdict(int)
        for label, vector in examples:
            counts[label] += 1
            bucket = buckets[label]
            if len(bucket) < MAX_EXEMPLARS_PER_LABEL:
                bucket.append(list(vector))
            else:
                bucket[counts[label] % MAX_EXEMPLARS_PER_LABEL] = list(vector)
        return cls(dict(buckets), dict(counts))

    def predict_features(self, vector: list[float]) -> PolicyPrediction:
        ranked: list[tuple[float, str]] = []
        for label, exemplars in self.exemplars.items():
            distances = sorted(_distance(vector, exemplar) for exemplar in exemplars)
            nearest = distances[: min(3, len(distances))]
            score = sum(nearest) / max(1, len(nearest))
            ranked.append((score, label))
        ranked.sort(key=lambda item: (item[0], item[1]))
        best_distance, best_label = ranked[0]
        if len(ranked) == 1:
            confidence = 1.0
        else:
            second_distance = ranked[1][0]
            confidence = max(0.0, min(1.0, (second_distance - best_distance) / max(second_distance, 1e-9)))
        return PolicyPrediction(best_label, _label_keys(best_label), confidence, best_distance)

    def to_dict(self) -> dict:
        return {"exemplars": self.exemplars, "counts": self.counts}

    @classmethod
    def from_dict(cls, payload: dict) -> "SpatialPolicy":
        return cls(payload["exemplars"], payload.get("counts"))


class SpatialCombatModel:
    """Experimental v0.2 spatial model using arena-local edge and motion features."""

    def __init__(
        self,
        navigation: SpatialPolicy,
        skill: SpatialPolicy,
        scaler: FeatureScaler,
        *,
        base_keys: Iterable[str] = ("r",),
        skill_keys: Iterable[str] = ("h",),
        post_combat_keys: Iterable[str] = ("v",),
        history_frames: int = 2,
    ) -> None:
        self.navigation = navigation
        self.skill = skill
        self.scaler = scaler
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
    ) -> "SpatialCombatModel":
        base = _key_set(base_keys)
        skills = _key_set(skill_keys)
        post_combat = _key_set(post_combat_keys)
        stride = max(1, int(stride))
        history = max(1, int(history_frames))

        raw_examples: list[tuple[str, str, list[float]]] = []
        all_vectors: list[list[float]] = []

        for session_path in store.session_paths(results=results):
            samples = list(store.samples(session_path))
            if not samples:
                continue
            by_index = {sample.index: sample for sample in samples}
            actions_path = Path(session_path) / "actions.jsonl"
            if not actions_path.exists():
                continue

            combat_started = False
            run_index = 0
            with actions_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    raw = json.loads(line)
                    raw_keys = _key_set(raw.get("keys", ()))

                    if not combat_started:
                        if raw_keys.intersection(post_combat):
                            continue
                        if not raw_keys.intersection(base):
                            continue
                        combat_started = True
                    elif raw_keys.intersection(post_combat):
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
                    vector = spatial_features(previous_jpeg, current_jpeg)

                    keys = raw_keys.difference(base).difference(post_combat)
                    nav_label = _label(keys.intersection(NAV_KEYS))
                    skill_label = _label(keys.intersection(skills))
                    raw_examples.append((nav_label, skill_label, vector))
                    all_vectors.append(vector)

        if not raw_examples:
            raise ValueError("NO_SPATIAL_TRAINING_SAMPLES")

        scaler = FeatureScaler.fit(all_vectors)
        nav_examples = [(nav, scaler.transform(vector)) for nav, _, vector in raw_examples]
        skill_examples = [(skill, scaler.transform(vector)) for _, skill, vector in raw_examples]

        return cls(
            SpatialPolicy.from_examples(nav_examples),
            SpatialPolicy.from_examples(skill_examples),
            scaler,
            base_keys=base,
            skill_keys=skills,
            post_combat_keys=post_combat,
            history_frames=history,
        )

    def predict(self, previous_jpeg: bytes, current_jpeg: bytes) -> CombatPrediction:
        vector = self.scaler.transform(spatial_features(previous_jpeg, current_jpeg))
        return CombatPrediction(
            navigation=self.navigation.predict_features(vector),
            skill=self.skill.predict_features(vector),
        )

    def save(self, path: Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_version": MODEL_VERSION,
            "feature_mode": FEATURE_MODE,
            "spatial_size": list(SPATIAL_SIZE),
            "motion_grid": list(MOTION_GRID),
            "arena_crop": list(ARENA_CROP),
            "base_keys": list(self.base_keys),
            "skill_keys": list(self.skill_keys),
            "post_combat_keys": list(self.post_combat_keys),
            "history_frames": self.history_frames,
            "scaler": self.scaler.to_dict(),
            "navigation": self.navigation.to_dict(),
            "skill": self.skill.to_dict(),
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output

    @classmethod
    def load(cls, path: Path) -> "SpatialCombatModel":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(payload.get("model_version", 0)) != MODEL_VERSION:
            raise ValueError("UNSUPPORTED_SPATIAL_MODEL_VERSION")
        if payload.get("feature_mode") != FEATURE_MODE:
            raise ValueError("UNSUPPORTED_SPATIAL_FEATURE_MODE")
        return cls(
            SpatialPolicy.from_dict(payload["navigation"]),
            SpatialPolicy.from_dict(payload["skill"]),
            FeatureScaler.from_dict(payload["scaler"]),
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
