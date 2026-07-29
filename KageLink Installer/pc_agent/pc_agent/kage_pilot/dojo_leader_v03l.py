from __future__ import annotations

import base64
import binascii
from typing import Iterable
import zlib

import cv2
import numpy as np

from .post_combat_v03b import LeaderMatchV2
from .post_combat_v03c import PersistentDojoLeaderDetector as _PersistentDojoLeaderDetector


# The clearer 68x77 Trainer frame supplied from the real Dojo was cropped and
# normalized offline to the validated 32x45 runtime footprint. Raw BGR pixels
# are zlib-compressed instead of storing the source PNG, avoiding differences
# between libpng builds on Windows and Linux.
_BUNDLED_CLEAR_TEMPLATE_ZLIB_B64 = """
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
""".strip()

_CLEAR_SOURCE_CROP = (2, 4, 67, 77)
_COMPACT_WIDTH = 32
_COMPACT_HEIGHT = 45
_COMPACT_CHANNELS = 3
_COMPACT_BYTE_COUNT = _COMPACT_WIDTH * _COMPACT_HEIGHT * _COMPACT_CHANNELS


def decode_bundled_clear_template() -> np.ndarray:
    """Decode the bundled normalized Dojo Trainer pixels as a BGR image."""

    try:
        compressed = base64.b64decode(
            "".join(_BUNDLED_CLEAR_TEMPLATE_ZLIB_B64.split()),
            validate=True,
        )
        raw = zlib.decompress(compressed)
    except (ValueError, binascii.Error, zlib.error) as error:
        raise RuntimeError("DOJO_CLEAR_TEMPLATE_DATA_INVALID") from error
    if len(raw) != _COMPACT_BYTE_COUNT:
        raise RuntimeError(
            f"DOJO_CLEAR_TEMPLATE_SIZE_INVALID:{len(raw)}/{_COMPACT_BYTE_COUNT}"
        )
    return np.frombuffer(raw, dtype=np.uint8).reshape(
        (_COMPACT_HEIGHT, _COMPACT_WIDTH, _COMPACT_CHANNELS)
    ).copy()


def compact_bundled_clear_template(image: np.ndarray | None = None) -> np.ndarray:
    """Return a 32x45 template, optionally normalizing the original clear frame."""

    if image is None:
        return decode_bundled_clear_template()
    if image.size == 0:
        raise RuntimeError("DOJO_CLEAR_TEMPLATE_EMPTY")
    if image.shape[:2] == (_COMPACT_HEIGHT, _COMPACT_WIDTH):
        return image.copy()

    left, top, right, bottom = _CLEAR_SOURCE_CROP
    height, width = image.shape[:2]
    left = max(0, min(width - 1, int(left)))
    top = max(0, min(height - 1, int(top)))
    right = max(left + 1, min(width, int(right)))
    bottom = max(top + 1, min(height, int(bottom)))
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        raise RuntimeError("DOJO_CLEAR_TEMPLATE_CROP_EMPTY")
    return cv2.resize(
        crop,
        (_COMPACT_WIDTH, _COMPACT_HEIGHT),
        interpolation=cv2.INTER_LINEAR,
    )


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
