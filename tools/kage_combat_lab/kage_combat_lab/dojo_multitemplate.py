from __future__ import annotations

import base64
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class TemplateCandidate:
    mode: str
    source_name: str
    template_gray: np.ndarray
    threshold: float
    scales: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class TemplateMatch:
    score: float
    bbox: tuple[int, int, int, int]
    foot: tuple[float, float]
    mode: str
    source_name: str
    scale: float


@dataclass(frozen=True, slots=True)
class TemplateScan:
    accepted: TemplateMatch | None
    raw_best: TemplateMatch | None
    scores: dict[str, float]
    scales: dict[str, float]
    rejection_reason: str


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


def _normalized_scales(values: Iterable[float]) -> tuple[float, ...]:
    return tuple(sorted({max(0.70, min(1.30, float(value))) for value in values})) or (1.0,)


def embedded_template_candidates(
    *,
    threshold: float = 0.88,
    scales: Iterable[float] = _DEFAULT_BUILTIN_SCALES,
) -> tuple[TemplateCandidate, ...]:
    normalized = _normalized_scales(scales)
    required = max(0.45, min(0.98, float(threshold)))
    templates = embedded_trainer_templates()
    return tuple(
        TemplateCandidate(
            mode="64",
            source_name=source_name,
            template_gray=cv2.cvtColor(templates[source_name], cv2.COLOR_BGR2GRAY),
            threshold=required,
            scales=normalized,
        )
        for source_name in ("night-64", "day-64")
    )


def _roi(frame_bgr: np.ndarray, arena_rect=None) -> tuple[np.ndarray, int, int]:
    frame_h, frame_w = frame_bgr.shape[:2]
    if arena_rect is None:
        x0, y0, x1, y1 = 0, 0, frame_w, frame_h
    else:
        x0, y0, x1, y1 = (int(value) for value in arena_rect)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(frame_w, x1), min(frame_h, y1)
    return frame_bgr[y0:y1, x0:x1], x0, y0


def scan_templates(
    frame_bgr: np.ndarray,
    candidates: Iterable[TemplateCandidate],
    *,
    arena_rect=None,
) -> TemplateScan:
    roi, offset_x, offset_y = _roi(frame_bgr, arena_rect)
    candidate_tuple = tuple(candidates)
    if roi.size == 0:
        return TemplateScan(None, None, {}, {}, "empty-roi")
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    raw_best: TemplateMatch | None = None
    accepted: list[TemplateMatch] = []
    scores: dict[str, float] = {}
    scales_by_source: dict[str, float] = {}

    for candidate in candidate_tuple:
        original_h, original_w = candidate.template_gray.shape[:2]
        source_best: TemplateMatch | None = None
        for scale in candidate.scales:
            width = max(8, round(original_w * scale))
            height = max(8, round(original_h * scale))
            if width > gray.shape[1] or height > gray.shape[0]:
                continue
            interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_NEAREST
            template = cv2.resize(candidate.template_gray, (width, height), interpolation=interpolation)
            result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(result)
            left = offset_x + int(location[0])
            top = offset_y + int(location[1])
            match = TemplateMatch(
                score=float(score),
                bbox=(left, top, width, height),
                foot=(left + width * 0.50, top + height * 0.88),
                mode=candidate.mode,
                source_name=candidate.source_name,
                scale=float(scale),
            )
            if source_best is None or match.score > source_best.score:
                source_best = match
            if raw_best is None or match.score > raw_best.score:
                raw_best = match

        if source_best is None:
            scores[candidate.source_name] = -1.0
            scales_by_source[candidate.source_name] = 1.0
            continue
        scores[candidate.source_name] = source_best.score
        scales_by_source[candidate.source_name] = source_best.scale
        if source_best.score >= candidate.threshold:
            accepted.append(source_best)

    if raw_best is None:
        return TemplateScan(None, None, scores, scales_by_source, "no-comparable-template")
    if not accepted:
        return TemplateScan(None, raw_best, scores, scales_by_source, "below-threshold")
    winner = max(accepted, key=lambda match: match.score)
    return TemplateScan(winner, raw_best, scores, scales_by_source, "")


class EmbeddedTrainerMatcher:
    """Pure OpenCV matcher used by both CI tests and the Windows adapter."""

    def __init__(
        self,
        *,
        threshold: float = 0.88,
        scales: Iterable[float] = _DEFAULT_BUILTIN_SCALES,
    ) -> None:
        self.candidates = embedded_template_candidates(threshold=threshold, scales=scales)
        self.threshold = max(candidate.threshold for candidate in self.candidates)
        self.last_scan = TemplateScan(None, None, {}, {}, "not-run")

    def match(self, frame_bgr: np.ndarray, *, arena_rect=None) -> TemplateMatch | None:
        self.last_scan = scan_templates(frame_bgr, self.candidates, arena_rect=arena_rect)
        return self.last_scan.accepted

    def diagnostics_text(self) -> str:
        day = self.last_scan.scores.get("day-64", -1.0)
        night = self.last_scan.scores.get("night-64", -1.0)
        best = max(self.last_scan.scores.values(), default=-1.0)
        winner = (
            self.last_scan.accepted.source_name
            if self.last_scan.accepted is not None
            else self.last_scan.raw_best.source_name
            if self.last_scan.raw_best is not None
            else "-"
        )
        return (
            f"day64={day:.3f} night64={night:.3f} best={best:.3f} "
            f"winner={winner} need={self.threshold:.3f} "
            f"rejection={self.last_scan.rejection_reason or '-'}"
        )


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


def _load_optional_gray(path: Path) -> np.ndarray | None:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        return None
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


class DayNightDojoLeaderDetector:
    """Runtime-created subclass of the validated persistent Windows detector."""

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

            built_in_scales = _normalized_scales((*requested_scales, *_DEFAULT_BUILTIN_SCALES))
            visual_candidates = list(
                embedded_template_candidates(
                    threshold=float(self.threshold),
                    scales=built_in_scales,
                )
            )

            store = DojoTemplateStore(template_root)
            for mode, record in store.records().items():
                if not record.configured:
                    continue
                gray = _load_optional_gray(record.path)
                if gray is not None:
                    visual_candidates.append(
                        TemplateCandidate(
                            mode=mode,
                            source_name=f"user-{mode}x{mode}",
                            template_gray=gray,
                            threshold=float(self.threshold),
                            scales=requested_scales,
                        )
                    )

            explicit = Path(template_path) if template_path is not None else legacy_source_template_path()
            if explicit.exists() and explicit.resolve() != seed.resolve():
                gray = _load_optional_gray(explicit)
                if gray is not None:
                    visual_candidates.append(
                        TemplateCandidate(
                            mode="legacy",
                            source_name="source-local-calibration",
                            template_gray=gray,
                            threshold=float(self.threshold),
                            scales=requested_scales,
                        )
                    )

            self._visual_candidates = tuple(visual_candidates)
            self.template_source = "night-64+day-64"
            self.template_mode = "64"
            self.last_raw_template_source = "-"
            self.last_raw_template_mode = "-"
            self.last_accepted_template_source: str | None = None
            self.last_accepted_template_mode: str | None = None
            self.last_rejection_reason = ""
            self.last_template_scores: dict[str, float] = {}
            self.last_template_scales: dict[str, float] = {}
            self._last_logged_winner: str | None = None
            self._last_logged_at = -1e9

        def describe(self) -> str:
            sources = ",".join(candidate.source_name for candidate in self._visual_candidates)
            return (
                f"multi_template_64 sources={sources} "
                f"threshold={self.threshold:.3f} selection=max(score)"
            )

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

        def _log_match(self, match: TemplateMatch) -> None:
            now = time.monotonic()
            if match.source_name == self._last_logged_winner and now - self._last_logged_at < 1.0:
                return
            self._last_logged_winner = match.source_name
            self._last_logged_at = now
            day = self.last_template_scores.get("day-64", -1.0)
            night = self.last_template_scores.get("night-64", -1.0)
            print(
                f"TRAINER_TEMPLATE_SCORES day-64={day:.3f} night-64={night:.3f} "
                f"best={match.score:.3f} winner={match.source_name}"
            )
            print(
                f"TRAINER_TEMPLATE_MATCH template={match.source_name} mode={match.mode} "
                f"score={match.score:.3f} scale={match.scale:.3f}"
            )

        def _best_visual(self, frame_bgr: np.ndarray, *, arena_rect=None):
            scan = scan_templates(frame_bgr, self._visual_candidates, arena_rect=arena_rect)
            self.last_template_scores = dict(scan.scores)
            self.last_template_scales = dict(scan.scales)
            self.last_accepted_template_mode = None
            self.last_accepted_template_source = None
            self.last_rejection_reason = scan.rejection_reason

            raw = scan.raw_best
            if raw is None:
                self.last_raw_score = -1.0
                self.last_raw_scale = 1.0
                self.last_raw_location = None
                self.last_raw_template_mode = "-"
                self.last_raw_template_source = "-"
            else:
                self.last_raw_score = raw.score
                self.last_raw_scale = raw.scale
                self.last_raw_location = (raw.bbox[0], raw.bbox[1])
                self.last_raw_template_mode = raw.mode
                self.last_raw_template_source = raw.source_name

            winner = scan.accepted
            if winner is None:
                return None
            self.last_accepted_template_mode = winner.mode
            self.last_accepted_template_source = winner.source_name
            self.last_rejection_reason = ""
            self._log_match(winner)
            return LeaderMatchV2(
                score=winner.score,
                bbox=winner.bbox,
                foot=winner.foot,
                source="visual",
                scale=winner.scale,
            )

    _DayNightDojoLeaderDetector.__name__ = "DayNightDojoLeaderDetector"
    _DayNightDojoLeaderDetector.__qualname__ = "DayNightDojoLeaderDetector"
    _DETECTOR_CLASS = _DayNightDojoLeaderDetector
    return _DETECTOR_CLASS


def install_day_night_dojo_detector() -> type:
    """Install one shared day/night detector before validated aliases are imported."""

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
    "EmbeddedTrainerMatcher",
    "TemplateCandidate",
    "TemplateMatch",
    "TemplateScan",
    "embedded_template_candidates",
    "embedded_trainer_templates",
    "install_day_night_dojo_detector",
    "scan_templates",
]
