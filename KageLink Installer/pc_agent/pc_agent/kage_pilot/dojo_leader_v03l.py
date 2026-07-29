from __future__ import annotations

import base64
import binascii
from typing import Iterable
import zlib

import cv2
import numpy as np

from .post_combat_v03b import LeaderMatchV2
from .post_combat_v03c import PersistentDojoLeaderDetector as _PersistentDojoLeaderDetector


# Exact BGR pixels from the clearer 68x77 Trainer frame supplied from the real
# Dojo. The previous revision resized this image immediately to 32x45 and used
# the normal 0.88 CLI threshold, which discarded the new template's intended
# 0.72 acceptance floor before real matching could occur.
#
# Keep the native frame and derive a compact compatibility candidate at runtime.
# Raw pixels are zlib-compressed to avoid libpng differences across platforms.
_BUNDLED_CLEAR_NATIVE_ZLIB_B64 = """
eNrlm9tP1UAQxnknxkAgQS7hcg4icDiIgJAA4aZHDCrGF4i+AD4Y0Pgu/7wO/UrP105n2CKYdF2+h82e6XZ+ZXa6u21bu5323oFo
YfeNqLXTEXELq7XbEel2yOoHdWjx9aEo12fSbvWp+9e+ZV61bljQgjrO6Huu/fcp0FtK1Hkn0r1pUvbNasmIulcyIhb2iuu6f0t+
FLX334osGz/e0utA/pdSZ/+LmFg4xqzxDn/0GPfpoN6kpNFLR/VS0b1xNFoZqf3qUMQhFxOLPwbDBa+43p+UXrfoKGUfQrIQLrW2
rDtLOjbvlId1tIRTWFw5Rhr71nWG8zwW4mC5NeOV+u8TgWU4KWOqoN2iDp87aZtYWRBvTOHPLqxo6Q8uuczsXlVz7pQckuXnaFj4
vqPzM9+zrHVB772W8LuAlb1jYtGz66p3SY4ZjPFWUk6Oj0UHSUEd7bAJIUpzcue9yBr+5uyrtizWf6fqipU9YRZQnH89E6Hus1hR
ZM1+sdDTq8jas/C8zp1p5/LeA2QAHefwh6Mrd+VpYyS3Eo+CRUeavkuiZa61UCpY8tifW90VXSUlXYvtn4hQRztsquZkvR7s/lPi
YtH7A1w/Oj6pJPgzv/VJBJ8x0sGCOtphw/77I93Z2SisDuJgKVn1UAaAh5+/XYh+XP0qCO0QLEeeLongJ/xHLLHQDhvYW/NY/06R
8RaOjYOF+0lzIGUDn4WJYIne4OHsxgcRPGehnSnutiefERXu4HGwlOQ6uodWZeE4mZ4cEzER6mj3Z7b+2C/kqwJvHCx6ZZrbIV98
VElNVVZU0TalTyKce3fIKiw+llwPiYeb2xO3yvI8pODYCk8VaY9F7/PHweLv2PxLFn9V6LQU5mBxsLB4lOkYW9veKJVmCeHS9jdP
kcpXXiH5OVaWkiewCQt7jvXXbKstQov2vCqLlQH08z5e0XefuReev8fB4r7pwTEG/8ECCrQ8HEtQjO10CvOuOFj8jKdzMrNY2fjv
Wcw3RnZKdikDs3e9WPw7JrMwBeeBhx77FhG/26MzWN1ZrLdi0lWzYsF4Z00nBeusxtKeCC0+C2xgn67RksIZODe3Z/8pX4nDW3tf
eAUXB4temeZWPQFzGGiaSvisko/y+2eJ8wVZq+z6suj3NHJcwXNLXiOHjHRuD6ewWOaXX4riY9E5sOoa2WJhb/1ftcbmpwr6f1j8
HTa9a6T7h6w9Jc1i/aopRo5mReM7o5nQXgBZ3/gY8nS4jiwls5fknsV7sOiHe2bB8vT8VPT98jITWmbacyLrV34axRTMwi2wEYRM
t8zEasvC9Wcb26KZtU2R3z/r7OKnqDkyJFqkghawWL/6LJqiwPJkolGYbcbDQu9TTT1fEQ0Mj4i4f/8s8ApzRUh7yyxsyTY4r5Vh
xhdmRbAZmmiIrkHs71/qy6J3+WDJLNDS1rrIOgv8sfS4r0/k2zDLwPCoCJ5DE+05EfsW8v1LfVk40hpLqyLE2ODw6OB1h91jrXdI
cC5tz16hbtt0hbNznLOaL9ZE+NX//qXuLBxj3A8LjEw6ubgssuzxK9vAB27hPnVvzeU1EVvqs/jfv9SdRb8TaHl4i8SZzJ+knnqo
6tax4OUo8hXy/Ut9WfQ3I36k6XY+O0cLR5oZkxmgHbH6LLmx737/Ul+W+/pmRPNqCj322UPrWvkxJs739PxO/noiYPkDhjmfsw==
""".strip()

_NATIVE_WIDTH = 68
_NATIVE_HEIGHT = 77
_CHANNELS = 3
_NATIVE_BYTE_COUNT = _NATIVE_WIDTH * _NATIVE_HEIGHT * _CHANNELS

_CLEAR_SOURCE_CROP = (2, 4, 67, 77)
_COMPACT_WIDTH = 32
_COMPACT_HEIGHT = 45

_BUNDLED_THRESHOLD = 0.72
_BUNDLED_SCALES = (0.90, 0.95, 1.00, 1.05, 1.10)


def decode_bundled_clear_template() -> np.ndarray:
    """Decode the exact clearer 68x77 Dojo Trainer frame as a BGR image."""

    try:
        compressed = base64.b64decode(
            "".join(_BUNDLED_CLEAR_NATIVE_ZLIB_B64.split()),
            validate=True,
        )
        raw = zlib.decompress(compressed)
    except (ValueError, binascii.Error, zlib.error) as error:
        raise RuntimeError("DOJO_CLEAR_TEMPLATE_DATA_INVALID") from error
    if len(raw) != _NATIVE_BYTE_COUNT:
        raise RuntimeError(
            f"DOJO_CLEAR_TEMPLATE_SIZE_INVALID:{len(raw)}/{_NATIVE_BYTE_COUNT}"
        )
    return np.frombuffer(raw, dtype=np.uint8).reshape(
        (_NATIVE_HEIGHT, _NATIVE_WIDTH, _CHANNELS)
    ).copy()


def compact_bundled_clear_template(image: np.ndarray | None = None) -> np.ndarray:
    """Return the legacy 32x45 compatibility view of the clearer frame."""

    if image is None:
        image = decode_bundled_clear_template()
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
    """Match local calibration plus native and compact clear Trainer templates.

    The caller's threshold remains authoritative for the existing local/legacy
    template. The two bundled clear candidates use their own conservative 0.72
    floor and still require the acquisition gate's stable multi-frame visual
    confirmation before any click.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.88,
        template_path=None,
        memory_seconds: float = 180.0,
        scales: Iterable[float] = _BUNDLED_SCALES,
    ) -> None:
        super().__init__(
            threshold=threshold,
            template_path=template_path,
            memory_seconds=memory_seconds,
            scales=scales,
        )
        native = decode_bundled_clear_template()
        compact = compact_bundled_clear_template(native)
        bundled_threshold = min(float(self.threshold), _BUNDLED_THRESHOLD)
        common_scales = tuple(float(value) for value in self.scales)

        self._visual_templates: tuple[
            tuple[str, np.ndarray, float, tuple[float, ...]], ...
        ] = (
            (
                str(self.template_source),
                self.template_gray,
                float(self.threshold),
                common_scales,
            ),
            (
                "bundled-clear-native-68x77",
                cv2.cvtColor(native, cv2.COLOR_BGR2GRAY),
                bundled_threshold,
                _BUNDLED_SCALES,
            ),
            (
                "bundled-clear-compact-32x45",
                cv2.cvtColor(compact, cv2.COLOR_BGR2GRAY),
                bundled_threshold,
                _BUNDLED_SCALES,
            ),
        )
        self.last_raw_template_source = str(self.template_source)
        self.last_raw_required_threshold = float(self.threshold)
        self.last_accepted_template_source: str | None = None
        self.last_accepted_threshold: float | None = None

    def _best_visual(
        self,
        frame_bgr: np.ndarray,
        *,
        arena_rect=None,
    ) -> LeaderMatchV2 | None:
        roi, offset_x, offset_y = self._roi(frame_bgr, arena_rect)
        if roi.size == 0:
            return None
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        raw_best_score = -1.0
        raw_best_scale = 1.0
        raw_best_location: tuple[int, int] | None = None
        raw_best_source = str(self.template_source)
        raw_best_threshold = float(self.threshold)

        accepted_score = -1.0
        accepted_scale = 1.0
        accepted_location: tuple[int, int] | None = None
        accepted_size: tuple[int, int] | None = None
        accepted_source: str | None = None
        accepted_threshold: float | None = None

        for source_name, template_gray, required_threshold, source_scales in self._visual_templates:
            original_h, original_w = template_gray.shape[:2]
            for scale in source_scales:
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
                location = (int(location[0]), int(location[1]))

                if score > raw_best_score:
                    raw_best_score = score
                    raw_best_scale = float(scale)
                    raw_best_location = location
                    raw_best_source = source_name
                    raw_best_threshold = float(required_threshold)

                # Evaluate each source against its own threshold. A rejected
                # higher raw score must not hide a valid bundled candidate.
                if score >= float(required_threshold) and score > accepted_score:
                    accepted_score = score
                    accepted_scale = float(scale)
                    accepted_location = location
                    accepted_size = (width, height)
                    accepted_source = source_name
                    accepted_threshold = float(required_threshold)

        self.last_raw_score = raw_best_score
        self.last_raw_scale = raw_best_scale
        self.last_raw_template_source = raw_best_source
        self.last_raw_required_threshold = raw_best_threshold
        self.last_raw_location = (
            (offset_x + raw_best_location[0], offset_y + raw_best_location[1])
            if raw_best_location is not None
            else None
        )
        self.last_accepted_template_source = accepted_source
        self.last_accepted_threshold = accepted_threshold

        if (
            accepted_location is None
            or accepted_size is None
            or accepted_source is None
        ):
            return None

        left = offset_x + accepted_location[0]
        top = offset_y + accepted_location[1]
        width, height = accepted_size
        return LeaderMatchV2(
            score=accepted_score,
            bbox=(left, top, width, height),
            foot=(left + width * 0.50, top + height * 0.88),
            source="visual",
            scale=accepted_scale,
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
