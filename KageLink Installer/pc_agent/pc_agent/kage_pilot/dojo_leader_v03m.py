from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from .dojo_leader_v03l import decode_bundled_clear_template
from .post_combat_v03b import LeaderMatchV2
from .post_combat_v03c import PersistentDojoLeaderDetector as _PersistentDojoLeaderDetector


# The clear 68x77 capture must only be resized isotropically. The prior v0.3l
# compatibility candidate stretched it to 32x45, changing the aspect ratio and
# destroying the correlation with the real runtime-sized Trainer.
_CLEAR_SCALES = (
    0.40,
    0.45,
    0.475,
    0.50,
    0.525,
    0.55,
    0.60,
    0.70,
    0.80,
    0.90,
    1.00,
    1.10,
    1.20,
    1.30,
)
_CLEAR_STRONG_THRESHOLD = 0.70
_LOCAL_WEAK_THRESHOLD = 0.60
_CLEAR_WEAK_THRESHOLD = 0.56
_FULL_FRAME_BONUS = 0.03

# Distinctive regions from the clear capture. A head match alone is not enough:
# it must agree with the chair or torso on the same scale and reconstructed
# native origin.
_CLEAR_PARTS = (
    ("head", (18, 2, 50, 30), 0.74),
    ("chair", (7, 22, 26, 60), 0.70),
    ("torso", (21, 27, 48, 60), 0.68),
)
_CLEAR_TRAINER_BODY_RECT = (19, 2, 31, 58)


@dataclass(frozen=True, slots=True)
class TemplateProbe:
    source: str
    score: float
    threshold: float
    scale: float
    bbox: tuple[int, int, int, int] | None
    scope: str
    accepted: bool = False

    @property
    def center(self) -> tuple[float, float] | None:
        if self.bbox is None:
            return None
        left, top, width, height = self.bbox
        return left + width * 0.5, top + height * 0.5

    @property
    def margin(self) -> float:
        return float(self.score) - float(self.threshold)


def _gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _resize(template_gray: np.ndarray, scale: float) -> np.ndarray:
    height, width = template_gray.shape[:2]
    target_width = max(6, round(width * float(scale)))
    target_height = max(6, round(height * float(scale)))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    return cv2.resize(
        template_gray,
        (target_width, target_height),
        interpolation=interpolation,
    )


class IsotropicDojoLeaderDetector(_PersistentDojoLeaderDetector):
    """Local calibration first, then undistorted clear-capture matching.

    Acceptance order:
    1. local calibration at the validated configured threshold;
    2. clear 68x77 capture at a strong isotropic match;
    3. weak local + clear agreement at the same position;
    4. clear head + chair/torso geometric consensus.

    The acquisition layer still requires two stable current frames before the
    one permitted Trainer click.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.88,
        template_path=None,
        memory_seconds: float = 180.0,
        scales: Iterable[float] = (0.80, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20),
    ) -> None:
        super().__init__(
            threshold=threshold,
            template_path=template_path,
            memory_seconds=memory_seconds,
            scales=scales,
        )
        self.clear_bgr = decode_bundled_clear_template()
        self.clear_gray = _gray(self.clear_bgr)
        self.clear_parts = tuple(
            (
                name,
                _gray(self.clear_bgr[top:bottom, left:right]),
                (left, top, right, bottom),
                float(part_threshold),
            )
            for name, (left, top, right, bottom), part_threshold in _CLEAR_PARTS
        )
        self.last_probe_rows: tuple[TemplateProbe, ...] = ()
        self.last_raw_template_source = str(self.template_source)
        self.last_raw_required_threshold = float(self.threshold)
        self.last_accepted_template_source: str | None = None
        self.last_accepted_threshold: float | None = None
        self.last_scope = "arena"

    def describe(self) -> str:
        local_exists = Path(self.template_path).exists()
        local_shape = (
            f"{self.template.shape[1]}x{self.template.shape[0]}"
            if self.template is not None and self.template.size > 0
            else "-"
        )
        return (
            f"local_source={self.template_source} "
            f"local_exists={'yes' if local_exists else 'no'} "
            f"local_shape={local_shape} local_threshold={self.threshold:.3f} "
            f"clear=68x77 isotropic scales=0.40..1.30 "
            f"clear_threshold={_CLEAR_STRONG_THRESHOLD:.2f}"
        )

    def diagnostics_text(self, *, limit: int = 8) -> str:
        rows = sorted(
            self.last_probe_rows,
            key=lambda row: (row.accepted, row.margin, row.score),
            reverse=True,
        )
        if not rows:
            return "no-probes"
        return " | ".join(
            f"{row.source}={row.score:.3f}/{row.threshold:.3f}"
            f"@{row.scale:.3f}:{row.scope}"
            for row in rows[: max(1, int(limit))]
        )

    def near_visual_candidate(self, *, ratio: float = 0.82) -> bool:
        required_ratio = max(0.50, min(1.0, float(ratio)))
        for row in self.last_probe_rows:
            if row.source.startswith("clear-part-"):
                continue
            if row.threshold > 0.0 and row.score >= row.threshold * required_ratio:
                return True
        return False

    @staticmethod
    def _scope(frame_bgr, arena_rect, *, full_frame: bool):
        if full_frame:
            return frame_bgr, 0, 0, "full"
        roi, offset_x, offset_y = _PersistentDojoLeaderDetector._roi(
            frame_bgr,
            arena_rect,
        )
        return roi, int(offset_x), int(offset_y), "arena"

    @staticmethod
    def _best_probe(
        gray: np.ndarray,
        template_gray: np.ndarray,
        *,
        source: str,
        threshold: float,
        scales: Iterable[float],
        offset_x: int,
        offset_y: int,
        scope: str,
    ) -> TemplateProbe:
        best_score = -1.0
        best_scale = 1.0
        best_bbox = None

        for scale in scales:
            resized = _resize(template_gray, float(scale))
            height, width = resized.shape[:2]
            if width > gray.shape[1] or height > gray.shape[0]:
                continue
            result = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(result)
            score = float(score)
            if score > best_score:
                best_score = score
                best_scale = float(scale)
                best_bbox = (
                    int(offset_x + location[0]),
                    int(offset_y + location[1]),
                    int(width),
                    int(height),
                )

        return TemplateProbe(
            source=source,
            score=best_score,
            threshold=float(threshold),
            scale=best_scale,
            bbox=best_bbox,
            scope=scope,
            accepted=best_bbox is not None and best_score >= float(threshold),
        )

    @staticmethod
    def _centers_agree(
        first: TemplateProbe,
        second: TemplateProbe,
        *,
        tolerance: float = 24.0,
    ) -> bool:
        first_center = first.center
        second_center = second.center
        if first_center is None or second_center is None:
            return False
        return math.hypot(
            first_center[0] - second_center[0],
            first_center[1] - second_center[1],
        ) <= float(tolerance)

    def _part_consensus(
        self,
        gray: np.ndarray,
        *,
        offset_x: int,
        offset_y: int,
        scope: str,
        threshold_bonus: float,
    ) -> tuple[TemplateProbe | None, list[TemplateProbe]]:
        rows: list[TemplateProbe] = []
        best_key = None
        best_probe = None

        for scale in _CLEAR_SCALES:
            current = []
            for name, part_gray, (left, top, _right, _bottom), base_threshold in self.clear_parts:
                probe = self._best_probe(
                    gray,
                    part_gray,
                    source=f"clear-part-{name}",
                    threshold=float(base_threshold) + threshold_bonus,
                    scales=(scale,),
                    offset_x=offset_x,
                    offset_y=offset_y,
                    scope=scope,
                )
                rows.append(probe)
                if not probe.accepted or probe.bbox is None:
                    continue
                part_left, part_top, _width, _height = probe.bbox
                current.append(
                    (
                        name,
                        probe,
                        (
                            float(part_left) - float(left) * float(scale),
                            float(part_top) - float(top) * float(scale),
                        ),
                    )
                )

            for count in range(2, len(current) + 1):
                for subset in itertools.combinations(current, count):
                    if "head" not in {item[0] for item in subset}:
                        continue
                    origins = [item[2] for item in subset]
                    max_distance = max(
                        (
                            math.hypot(
                                first[0] - second[0],
                                first[1] - second[1],
                            )
                            for first, second in itertools.combinations(origins, 2)
                        ),
                        default=0.0,
                    )
                    if max_distance > 6.0 + 8.0 * float(scale):
                        continue

                    mean_score = sum(item[1].score for item in subset) / len(subset)
                    mean_margin = sum(item[1].margin for item in subset) / len(subset)
                    key = (len(subset), mean_margin, mean_score)
                    if best_key is not None and key <= best_key:
                        continue

                    origin_x = sum(item[2][0] for item in subset) / len(subset)
                    origin_y = sum(item[2][1] for item in subset) / len(subset)
                    body_x, body_y, body_width, body_height = _CLEAR_TRAINER_BODY_RECT
                    bbox = (
                        round(origin_x + body_x * float(scale)),
                        round(origin_y + body_y * float(scale)),
                        max(6, round(body_width * float(scale))),
                        max(12, round(body_height * float(scale))),
                    )
                    best_key = key
                    best_probe = TemplateProbe(
                        source="bundled-clear-parts",
                        score=float(mean_score),
                        threshold=float(mean_score - mean_margin),
                        scale=float(scale),
                        bbox=bbox,
                        scope=scope,
                        accepted=True,
                    )

        return best_probe, rows

    @staticmethod
    def _to_match(probe: TemplateProbe) -> LeaderMatchV2:
        assert probe.bbox is not None
        left, top, width, height = probe.bbox
        return LeaderMatchV2(
            score=float(probe.score),
            bbox=(left, top, width, height),
            foot=(
                float(left) + float(width) * 0.50,
                float(top) + float(height) * 0.88,
            ),
            source="visual",
            scale=float(probe.scale),
        )

    def _search_scope(self, frame_bgr, *, arena_rect, full_frame: bool):
        roi, offset_x, offset_y, scope = self._scope(
            frame_bgr,
            arena_rect,
            full_frame=full_frame,
        )
        if roi.size == 0:
            return None, []
        gray = _gray(roi)
        bonus = _FULL_FRAME_BONUS if full_frame else 0.0

        local_probe = self._best_probe(
            gray,
            self.template_gray,
            source=str(self.template_source),
            threshold=float(self.threshold) + bonus,
            scales=self.scales,
            offset_x=offset_x,
            offset_y=offset_y,
            scope=scope,
        )
        clear_probe = self._best_probe(
            gray,
            self.clear_gray,
            source="bundled-clear-isotropic-68x77",
            threshold=_CLEAR_STRONG_THRESHOLD + bonus,
            scales=_CLEAR_SCALES,
            offset_x=offset_x,
            offset_y=offset_y,
            scope=scope,
        )
        rows = [local_probe, clear_probe]

        if self.template_source == "local" and local_probe.accepted:
            return local_probe, rows
        if clear_probe.accepted:
            return clear_probe, rows

        if (
            self.template_source == "local"
            and local_probe.score >= _LOCAL_WEAK_THRESHOLD + bonus
            and clear_probe.score >= _CLEAR_WEAK_THRESHOLD + bonus
            and self._centers_agree(local_probe, clear_probe)
        ):
            combined = TemplateProbe(
                source="local-clear-consensus",
                score=(local_probe.score + clear_probe.score) * 0.5,
                threshold=(_LOCAL_WEAK_THRESHOLD + _CLEAR_WEAK_THRESHOLD) * 0.5 + bonus,
                scale=local_probe.scale,
                bbox=local_probe.bbox,
                scope=scope,
                accepted=True,
            )
            rows.append(combined)
            return combined, rows

        part_probe, part_rows = self._part_consensus(
            gray,
            offset_x=offset_x,
            offset_y=offset_y,
            scope=scope,
            threshold_bonus=bonus,
        )
        rows.extend(part_rows)
        if part_probe is not None:
            rows.append(part_probe)
            return part_probe, rows

        if self.template_source != "local" and local_probe.accepted:
            return local_probe, rows
        return None, rows

    def _best_visual(self, frame_bgr: np.ndarray, *, arena_rect=None):
        accepted, rows = self._search_scope(
            frame_bgr,
            arena_rect=arena_rect,
            full_frame=False,
        )
        if accepted is None and arena_rect is not None:
            full_accepted, full_rows = self._search_scope(
                frame_bgr,
                arena_rect=arena_rect,
                full_frame=True,
            )
            rows.extend(full_rows)
            accepted = full_accepted

        self.last_probe_rows = tuple(rows)
        primary_rows = [
            row
            for row in rows
            if not row.source.startswith("clear-part-") or row.accepted
        ]
        best_raw = max(primary_rows, key=lambda row: row.score, default=None)
        if best_raw is None:
            self.last_raw_score = -1.0
            self.last_raw_scale = 1.0
            self.last_raw_location = None
            self.last_raw_template_source = "-"
            self.last_raw_required_threshold = float(self.threshold)
        else:
            self.last_raw_score = float(best_raw.score)
            self.last_raw_scale = float(best_raw.scale)
            self.last_raw_template_source = str(best_raw.source)
            self.last_raw_required_threshold = float(best_raw.threshold)
            self.last_raw_location = (
                (best_raw.bbox[0], best_raw.bbox[1])
                if best_raw.bbox is not None
                else None
            )

        if accepted is None:
            self.last_accepted_template_source = None
            self.last_accepted_threshold = None
            return None

        self.last_accepted_template_source = str(accepted.source)
        self.last_accepted_threshold = float(accepted.threshold)
        self.last_scope = str(accepted.scope)
        return self._to_match(accepted)

    def debug_overlay(self, frame_bgr: np.ndarray, *, arena_rect=None) -> np.ndarray:
        overlay = frame_bgr.copy()
        if arena_rect is not None:
            x0, y0, x1, y1 = (int(value) for value in arena_rect)
            cv2.rectangle(overlay, (x0, y0), (x1, y1), (255, 255, 255), 1)

        rows = sorted(
            (row for row in self.last_probe_rows if row.bbox is not None),
            key=lambda row: (row.accepted, row.margin, row.score),
            reverse=True,
        )[:6]
        for index, row in enumerate(rows):
            left, top, width, height = row.bbox or (0, 0, 0, 0)
            cv2.rectangle(
                overlay,
                (left, top),
                (left + width, top + height),
                (255, 255, 255),
                1,
            )
            cv2.putText(
                overlay,
                f"{index + 1} {row.source} {row.score:.3f}/{row.threshold:.3f}",
                (max(0, left), max(14, top - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
        return overlay


def install_isotropic_dojo_leader_detector() -> None:
    """Patch both post-combat and initial acquisition before runtime creation."""

    from . import dojo_fight_v03i
    from . import post_combat_v03c
    from .trainer_search_v03m import search_trainer_until_visible_diagnostic

    post_combat_v03c.PersistentDojoLeaderDetector = IsotropicDojoLeaderDetector
    dojo_fight_v03i.search_trainer_until_visible = (
        search_trainer_until_visible_diagnostic
    )


__all__ = [
    "IsotropicDojoLeaderDetector",
    "TemplateProbe",
    "install_isotropic_dojo_leader_detector",
]
