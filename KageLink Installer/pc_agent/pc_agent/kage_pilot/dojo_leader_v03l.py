from __future__ import annotations

import base64
import binascii
import math
from typing import Iterable

import cv2
import numpy as np

from .post_combat_v03b import LeaderMatchV2
from .post_combat_v03c import PersistentDojoLeaderDetector as _PersistentDojoLeaderDetector


# Clear 68x77 source supplied from a real Dojo Trainer frame. It is kept as
# base64 text because data/kage_pilot is intentionally reserved for local,
# ignored calibration files.
_BUNDLED_CLEAR_TEMPLATE_PNG_B64 = """
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
""".strip()

# The validated Micro-PC capture sees the same sprite at approximately 32x45.
# Crop coordinates remove the extra side background before downscaling.
_CLEAR_CROP = (2, 4, 67, 77)
_COMPACT_SIZE = (32, 45)


def decode_bundled_clear_template() -> np.ndarray:
    """Decode the bundled clear Dojo Trainer frame as BGR pixels."""

    try:
        payload = base64.b64decode("".join(_BUNDLED_CLEAR_TEMPLATE_PNG_B64.split()), validate=True)
    except (ValueError, binascii.Error) as error:
        raise RuntimeError("DOJO_CLEAR_TEMPLATE_BASE64_INVALID") from error
    encoded = np.frombuffer(payload, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise RuntimeError("DOJO_CLEAR_TEMPLATE_PNG_INVALID")
    return image


def compact_bundled_clear_template(image: np.ndarray | None = None) -> np.ndarray:
    """Build the 32x45 runtime template from the clearer supplied source."""

    source = decode_bundled_clear_template() if image is None else image
    if source is None or source.size == 0:
        raise RuntimeError("DOJO_CLEAR_TEMPLATE_EMPTY")
    left, top, right, bottom = _CLEAR_CROP
    height, width = source.shape[:2]
    left = max(0, min(width - 1, int(left)))
    top = max(0, min(height - 1, int(top)))
    right = max(left + 1, min(width, int(right)))
    bottom = max(top + 1, min(height, int(bottom)))
    crop = source[top:bottom, left:right]
    if crop.size == 0:
        raise RuntimeError("DOJO_CLEAR_TEMPLATE_CROP_EMPTY")
    return cv2.resize(crop, _COMPACT_SIZE, interpolation=cv2.INTER_LINEAR)


class ClearDojoLeaderDetector(_PersistentDojoLeaderDetector):
    """Use both local calibration and the clearer bundled Trainer template.

    The local ``data/kage_pilot/dojo_leader_template.png`` remains the first
    authority when present. The bundled compact template is an additional
    candidate, so existing validated installations keep working while clean
    frames can recover from the old blurred-template weakness.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.72,
        template_path=None,
        memory_seconds: float = 180.0,
        scales: Iterable[float] = (0.90, 0.95, 1.00, 1.05, 1.10),
    ) -> None:
        super().__init__(
            threshold=threshold,
            template_path=template_path,
            memory_seconds=memory_seconds,
            scales=scales,
        )
        clear_compact = compact_bundled_clear_template()
        self._visual_templates: tuple[tuple[str, np.ndarray], ...] = (
            (str(self.template_source), self.template_gray),
            (
                "bundled-clear-32x45",
                cv2.cvtColor(clear_compact, cv2.COLOR_BGR2GRAY),
            ),
        )
        self.last_raw_template_source = str(self.template_source)

    def _best_visual(self, frame_bgr: np.ndarray, *, arena_rect=None) -> LeaderMatchV2 | None:
        roi, offset_x, offset_y = self._roi(frame_bgr, arena_rect)
        if roi.size == 0:
            return None
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        best_score = -1.0
        best_scale = 1.0
        best_location: tuple[int, int] | None = None
        best_size: tuple[int, int] | None = None
        best_source = str(self.template_source)

        for source_name, template_gray in self._visual_templates:
            original_h, original_w = template_gray.shape[:2]
            for scale in self.scales:
                width = max(8, round(original_w * scale))
                height = max(8, round(original_h * scale))
                if width > gray.shape[1] or height > gray.shape[0]:
                    continue
                interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
                template = cv2.resize(
                    template_gray,
                    (width, height),
                    interpolation=interpolation,
                )
                result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                _, score, _, location = cv2.minMaxLoc(result)
                score = float(score)
                if score > best_score:
                    best_score = score
                    best_scale = float(scale)
                    best_location = (int(location[0]), int(location[1]))
                    best_size = (width, height)
                    best_source = source_name

        self.last_raw_score = best_score
        self.last_raw_scale = best_scale
        self.last_raw_template_source = best_source
        self.last_raw_location = (
            (offset_x + best_location[0], offset_y + best_location[1])
            if best_location is not None
            else None
        )
        if best_location is None or best_size is None or best_score < self.threshold:
            return None

        left = offset_x + best_location[0]
        top = offset_y + best_location[1]
        width, height = best_size
        return LeaderMatchV2(
            score=best_score,
            bbox=(left, top, width, height),
            foot=(left + width * 0.50, top + height * 0.88),
            source="visual",
            scale=best_scale,
        )


def install_clear_dojo_leader_detector() -> None:
    """Install the detector before Trainer search or post-combat engine creation."""

    from . import post_combat_v03c

    post_combat_v03c.PersistentDojoLeaderDetector = ClearDojoLeaderDetector


__all__ = [
    "ClearDojoLeaderDetector",
    "compact_bundled_clear_template",
    "decode_bundled_clear_template",
    "install_clear_dojo_leader_detector",
]
