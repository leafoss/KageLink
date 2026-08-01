from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import time
from typing import Iterable

import cv2
import numpy as np


_CANONICAL_SIZE = 64
_EMBEDDED_SOURCES = (
    ("night-64", "trainer_night_64.b64"),
    ("day-64", "trainer_day_64.b64"),
)
_DEFAULT_BUILTIN_SCALES = (0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.25)


def _package_file(name: str) -> Path:
    return Path(__file__).resolve().with_name(name)


def _decode_b64_png(path: Path) -> np.ndarray:
    try:
        encoded = "".join(path.read_text(encoding="ascii").split())
        raw = base64.b64decode(encoded, validate=True)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"TRAINER_TEMPLATE_EMBEDDED_READ_FAILED:{path.name}") from exc
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise RuntimeError(f"TRAINER_TEMPLATE_EMBEDDED_DECODE_FAILED:{path.name}")
    if image.shape[:2] != (_CANONICAL_SIZE, _CANONICAL_SIZE):
        raise RuntimeError(
            f"TRAINER_TEMPLATE_CANONICAL_SIZE_INVALID:{path.name}:"
            f"{image.shape[1]}x{image.shape[0]}"
        )
    return image


def embedded_trainer_templates() -> dict[str, np.ndarray]:
    return {
        source: _decode_b64_png(_package_file(filename))
        for source, filename in _EMBEDDED_SOURCES
    }


def _runtime_seed_path(image: np.ndarray) -> Path:
    root = Path(tempfile.gettempdir()) / "KageLink" / "pr25"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "dojo_trainer_night_64.png"
    if not path.exists():
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise RuntimeError("TRAINER_TEMPLATE_SEED_ENCODE_FAILED")
        path.write_bytes(bytes(encoded))
    return path


def _normalized_scales(values: Iterable[float]) -> tuple[float, ...]:
    return tuple(sorted({max(0.70, min(1.30, float(value))) for value in values})) or (1.0,)


def _load_optional_gray(path: Path) -> np.ndarray | None:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        return None
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


class DayNightDojoLeaderDetector:
    """Runtime-created subclass of the validated persistent detector.

    The concrete base is selected in ``__new__`` after the PC Agent path is available.
    This keeps the deterministic lab importable without KageLink runtime setup.
    """

    def __new__(cls, *args, **kwargs):
        from pc_agent.kage_pilot.post_combat_v03c import PersistentDojoLeaderDetector

        concrete = _build_detector_class(PersistentDojoLeaderDetector)
        return concrete(*args, **kwargs)


_DETECTOR_CLASS = None


def _build_detector_class(base_class):
    global _DETECTOR_CLASS
    if _DETECTOR_CLASS is not None and issubclass(_DETECTOR_CLASS, base_class):
        return _DETECTOR_CLASS

    from pc_agent.kage_pilot.dojo_templates_v35 import (
        DojoTemplateStore,
        legacy_source_template_path,
    )
    from pc_agent.kage_pilot.post_combat_v03b import LeaderMatchV2

    class _DayNightDojoLeaderDetector(base_class):
        """Multi-template detector for canonical 64px day/night Trainer appearances."""

        def __init__(
            self,
            *,
            threshold: float = 0.88,
            template_path=None,
            memory_seconds: float = 180.0,
            scales: Iterable[float] = _DEFAULT_BUILTIN_SCALES,
            template_root: Path | str | None = None,
        ) -> None:
            embedded = embedded_trainer_templates()
            seed = _runtime_seed_path(embedded["night-64"])
            requested_scales = _normalized_scales(scales)
            super().__init__(
                threshold=threshold,
                template_path=seed,
                memory_seconds=memory_seconds,
                scales=requested_scales,
            )

            visual_templates: list[tuple[str, str, np.ndarray, float, tuple[float, ...]]] = []
            built_in_scales = _normalized_scales((*requested_scales, *_DEFAULT_BUILTIN_SCALES))
            for source_name in ("night-64", "day-64"):
                visual_templates.append(
                    (
                        "64",
                        source_name,
                        cv2.cvtColor(embedded[source_name], cv2.COLOR_BGR2GRAY),
                        float(self.threshold),
                        built_in_scales,
                    )
                )

            store = DojoTemplateStore(template_root)
            for mode, record in store.records().items():
                if not record.configured:
                    continue
                gray = _load_optional_gray(record.path)
                if gray is not None:
                    visual_templates.append(
                        (mode, f"user-{mode}x{mode}", gray, float(self.threshold), requested_scales)
                    )

            explicit = Path(template_path) if template_path is not None else legacy_source_template_path()
            if explicit.exists() and explicit.resolve() != seed.resolve():
                gray = _load_optional_gray(explicit)
                if gray is not None:
                    visual_templates.append(
                        ("legacy", "source-local-calibration", gray, float(self.threshold), requested_scales)
                    )

            self._visual_templates = tuple(visual_templates)
            self.template_source = "night-64+day-64"
            self.template_mode = "64"
            self.last_raw_template_source = "-"
            self.last_raw_template_mode = "-"
            self.last_accepted_template_source: str | None = None
            self.last_accepted_template_mode: str | None = None
            self.last_rejection_reason = ""
            self.last_template_scores: dict[str, float] = {
                source_name: -1.0 for _, source_name, *_ in self._visual_templates
            }
            self.last_template_scales: dict[str, float] = {
                source_name: 1.0 for _, source_name, *_ in self._visual_templates
            }
            self._last_logged_winner: str | None = None
            self._last_logged_at = -1e9

        def describe(self) -> str:
            sources = ",".join(source for _, source, *_ in self._visual_templates)
            return (
                f"multi_template_64 sources={sources} "
                f"threshold={self.threshold:.3f} selection=max(score)"
            )

        def diagnostic_snapshot(self) -> dict[str, object]:
            winner = self.last_accepted_template_source or self.last_raw_template_source or "-"
            best = max(self.last_template_scores.values(), default=-1.0)
            return {
                "scores": dict(self.last_template_scores),
                "scales": dict(self.last_template_scales),
                "best_score": float(best),
                "winner": winner,
                "accepted": self.last_accepted_template_source is not None,
                "threshold": float(self.threshold),
            }

        def diagnostics_text(self, *, limit: int = 8) -> str:
            del limit
            day = self.last_template_scores.get("day-64", -1.0)
            night = self.last_template_scores.get("night-64", -1.0)
            best = max(self.last_template_scores.values(), default=-1.0)
            winner = self.last_accepted_template_source or self.last_raw_template_source or "-"
            return (
                f"day64={day:.3f} night64={night:.3f} best={best:.3f} "
                f"winner={winner} need={self.threshold:.3f} "
                f"scale={self.last_raw_scale:.3f} rejection={self.last_rejection_reason or '-'}"
            )

        def _log_match(self, *, source_name: str, mode: str, score: float, scale: float) -> None:
            now = time.monotonic()
            if source_name == self._last_logged_winner and now - self._last_logged_at < 1.0:
                return
            self._last_logged_winner = source_name
            self._last_logged_at = now
            day = self.last_template_scores.get("day-64", -1.0)
            night = self.last_template_scores.get("night-64", -1.0)
            print(
                f"TRAINER_TEMPLATE_SCORES day-64={day:.3f} night-64={night:.3f} "
                f"best={score:.3f} winner={source_name}"
            )
            print(
                f"TRAINER_TEMPLATE_MATCH template={source_name} mode={mode} "
                f"score={score:.3f} scale={scale:.3f}"
            )

        def _best_visual(self, frame_bgr: np.ndarray, *, arena_rect=None):
            roi, offset_x, offset_y = self._roi(frame_bgr, arena_rect)
            if roi.size == 0:
                self.last_rejection_reason = "empty-roi"
                return None
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

            raw_best = None
            accepted: list[tuple] = []
            scores: dict[str, float] = {}
            scales_by_source: dict[str, float] = {}

            for mode, source_name, template_gray, required_threshold, source_scales in self._visual_templates:
                original_h, original_w = template_gray.shape[:2]
                source_best = None
                for scale in source_scales:
                    width = max(8, round(original_w * scale))
                    height = max(8, round(original_h * scale))
                    if width > gray.shape[1] or height > gray.shape[0]:
                        continue
                    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_NEAREST
                    template = cv2.resize(template_gray, (width, height), interpolation=interpolation)
                    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                    _, score, _, location = cv2.minMaxLoc(result)
                    candidate = (
                        float(score),
                        float(scale),
                        (int(location[0]), int(location[1])),
                        (width, height),
                        mode,
                        source_name,
                        float(required_threshold),
                    )
                    if source_best is None or candidate[0] > source_best[0]:
                        source_best = candidate
                    if raw_best is None or candidate[0] > raw_best[0]:
                        raw_best = candidate

                if source_best is None:
                    scores[source_name] = -1.0
                    scales_by_source[source_name] = 1.0
                    continue
                scores[source_name] = float(source_best[0])
                scales_by_source[source_name] = float(source_best[1])
                if source_best[0] >= source_best[6]:
                    accepted.append(source_best)

            self.last_template_scores = scores
            self.last_template_scales = scales_by_source
            self.last_accepted_template_mode = None
            self.last_accepted_template_source = None

            if raw_best is None:
                self.last_raw_score = -1.0
                self.last_raw_scale = 1.0
                self.last_raw_location = None
                self.last_raw_template_mode = "-"
                self.last_raw_template_source = "-"
                self.last_rejection_reason = "no-comparable-template"
                return None

            score, scale, location, _, mode, source_name, _ = raw_best
            self.last_raw_score = float(score)
            self.last_raw_scale = float(scale)
            self.last_raw_template_mode = str(mode)
            self.last_raw_template_source = str(source_name)
            self.last_raw_location = (offset_x + location[0], offset_y + location[1])

            if not accepted:
                self.last_rejection_reason = "below-threshold"
                return None

            best = max(accepted, key=lambda item: item[0])
            score, scale, location, size, mode, source_name, _ = best
            left = offset_x + location[0]
            top = offset_y + location[1]
            width, height = size
            self.last_accepted_template_mode = str(mode)
            self.last_accepted_template_source = str(source_name)
            self.last_rejection_reason = ""
            self._log_match(
                source_name=str(source_name),
                mode=str(mode),
                score=float(score),
                scale=float(scale),
            )
            return LeaderMatchV2(
                score=float(score),
                bbox=(left, top, width, height),
                foot=(left + width * 0.50, top + height * 0.88),
                source="visual",
                scale=float(scale),
            )

    _DayNightDojoLeaderDetector.__name__ = "DayNightDojoLeaderDetector"
    _DayNightDojoLeaderDetector.__qualname__ = "DayNightDojoLeaderDetector"
    _DETECTOR_CLASS = _DayNightDojoLeaderDetector
    return _DETECTOR_CLASS


def install_day_night_dojo_detector() -> type:
    """Install one shared day/night detector before the validated loop imports aliases."""

    from pc_agent.kage_pilot import dojo_templates_v35, post_combat_v03c

    detector_class = _build_detector_class(post_combat_v03c.PersistentDojoLeaderDetector)
    dojo_templates_v35.UserDojoLeaderDetector = detector_class
    post_combat_v03c.PersistentDojoLeaderDetector = detector_class

    try:
        from pc_agent.kage_pilot import dojo_templates

        dojo_templates.UserDojoLeaderDetector = detector_class
    except Exception:
        pass

    return detector_class


__all__ = [
    "DayNightDojoLeaderDetector",
    "embedded_trainer_templates",
    "install_day_night_dojo_detector",
]
