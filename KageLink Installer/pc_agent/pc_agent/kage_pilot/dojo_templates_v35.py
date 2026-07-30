from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from .post_combat_v03b import LeaderMatchV2
from .post_combat_v03c import PersistentDojoLeaderDetector as _PersistentDojoLeaderDetector


DOJO_TEMPLATE_MODES = ("32", "64")
TEMPLATE_FILENAMES = {
    "32": "dojo_trainer_32.png",
    "64": "dojo_trainer_64.png",
}
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_MIN_DIMENSION = 8
_MAX_DIMENSION = 2048
_DEFAULT_SCALES = (0.90, 0.95, 1.00, 1.05, 1.10)


def _local_app_data_root() -> Path:
    value = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if value:
        return Path(value)
    if os.name == "nt":
        return Path.home() / "AppData" / "Local"
    return Path.home() / ".local" / "share"


def default_template_root() -> Path:
    return _local_app_data_root() / "KageLink" / "data" / "kage_pilot" / "templates"


def legacy_source_template_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "kage_pilot" / "dojo_leader_template.png"


def normalize_template_mode(mode: str | int) -> str:
    value = str(mode).strip()
    if value not in DOJO_TEMPLATE_MODES:
        raise ValueError(f"DOJO_TEMPLATE_MODE_INVALID:{value}")
    return value


@dataclass(frozen=True, slots=True)
class DojoTemplateRecord:
    mode: str
    path: Path
    configured: bool
    width: int | None = None
    height: int | None = None
    size_bytes: int = 0
    sha256: str | None = None
    updated_at: str | None = None
    original_filename: str | None = None

    def to_public_dict(self) -> dict:
        return {
            "mode": self.mode,
            "configured": self.configured,
            "width": self.width,
            "height": self.height,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "updated_at": self.updated_at,
            "original_filename": self.original_filename,
        }


class DojoTemplateStore:
    """Persistent user-owned Trainer templates stored outside packaged executables."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_template_root()
        self.metadata_path = self.root / "templates.json"

    def template_path(self, mode: str | int) -> Path:
        value = normalize_template_mode(mode)
        return self.root / TEMPLATE_FILENAMES[value]

    def _read_metadata(self) -> dict:
        try:
            value = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "templates": {}}
        except (OSError, ValueError, TypeError):
            return {"version": 1, "templates": {}}
        if not isinstance(value, dict):
            return {"version": 1, "templates": {}}
        templates = value.get("templates")
        if not isinstance(templates, dict):
            templates = {}
        return {"version": 1, "templates": templates}

    def _write_metadata(self, value: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.metadata_path)

    @staticmethod
    def _decode_image(raw: bytes) -> np.ndarray:
        if not raw:
            raise ValueError("DOJO_TEMPLATE_EMPTY")
        if len(raw) > _MAX_UPLOAD_BYTES:
            raise ValueError("DOJO_TEMPLATE_TOO_LARGE")
        encoded = np.frombuffer(raw, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
        if image is None or image.size == 0:
            raise ValueError("DOJO_TEMPLATE_DECODE_FAILED")
        height, width = image.shape[:2]
        if width < _MIN_DIMENSION or height < _MIN_DIMENSION:
            raise ValueError("DOJO_TEMPLATE_DIMENSIONS_TOO_SMALL")
        if width > _MAX_DIMENSION or height > _MAX_DIMENSION:
            raise ValueError("DOJO_TEMPLATE_DIMENSIONS_TOO_LARGE")
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.shape[2] == 4:
            alpha = image[:, :, 3]
            if int(np.max(alpha)) == 0:
                raise ValueError("DOJO_TEMPLATE_FULLY_TRANSPARENT")
        return image

    def save(self, mode: str | int, raw: bytes, *, original_filename: str = "") -> DojoTemplateRecord:
        value = normalize_template_mode(mode)
        image = self._decode_image(raw)
        ok, png = cv2.imencode(".png", image)
        if not ok:
            raise ValueError("DOJO_TEMPLATE_ENCODE_FAILED")
        payload = bytes(png)
        digest = hashlib.sha256(payload).hexdigest()
        height, width = image.shape[:2]
        updated_at = datetime.now(timezone.utc).isoformat()

        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.template_path(value)
        temporary = destination.with_suffix(".png.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, destination)

        metadata = self._read_metadata()
        templates = metadata.setdefault("templates", {})
        templates[value] = {
            "file": destination.name,
            "width": int(width),
            "height": int(height),
            "size_bytes": len(payload),
            "sha256": digest,
            "updated_at": updated_at,
            "original_filename": Path(str(original_filename or "")).name or None,
        }
        self._write_metadata(metadata)
        return self.record(value)

    def remove(self, mode: str | int) -> DojoTemplateRecord:
        value = normalize_template_mode(mode)
        path = self.template_path(value)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        metadata = self._read_metadata()
        metadata.setdefault("templates", {}).pop(value, None)
        self._write_metadata(metadata)
        return self.record(value)

    def record(self, mode: str | int) -> DojoTemplateRecord:
        value = normalize_template_mode(mode)
        path = self.template_path(value)
        if not path.exists():
            return DojoTemplateRecord(mode=value, path=path, configured=False)

        metadata = self._read_metadata().get("templates", {}).get(value, {})
        try:
            raw = path.read_bytes()
            image = self._decode_image(raw)
            height, width = image.shape[:2]
            digest = hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError):
            return DojoTemplateRecord(mode=value, path=path, configured=False)

        return DojoTemplateRecord(
            mode=value,
            path=path,
            configured=True,
            width=int(width),
            height=int(height),
            size_bytes=len(raw),
            sha256=digest,
            updated_at=str(metadata.get("updated_at") or "") or None,
            original_filename=str(metadata.get("original_filename") or "") or None,
        )

    def records(self) -> dict[str, DojoTemplateRecord]:
        return {mode: self.record(mode) for mode in DOJO_TEMPLATE_MODES}

    def has_any(self) -> bool:
        return any(record.configured for record in self.records().values())

    def public_status(self) -> dict:
        records = self.records()
        configured_modes = [mode for mode, record in records.items() if record.configured]
        return {
            "ready": bool(configured_modes),
            "storage": str(self.root),
            "configured_modes": configured_modes,
            "templates": {mode: record.to_public_dict() for mode, record in records.items()},
        }

    def image_base64(self, mode: str | int) -> str:
        record = self.record(mode)
        if not record.configured:
            raise FileNotFoundError("DOJO_TEMPLATE_NOT_CONFIGURED")
        return base64.b64encode(record.path.read_bytes()).decode("ascii")


DEFAULT_DOJO_TEMPLATE_STORE = DojoTemplateStore()


class UserDojoLeaderDetector(_PersistentDojoLeaderDetector):
    """Match user-provided 32x32 and 64x64-mode templates without packaged image data."""

    def __init__(
        self,
        *,
        threshold: float = 0.88,
        template_path=None,
        memory_seconds: float = 180.0,
        scales: Iterable[float] = _DEFAULT_SCALES,
        template_root: Path | str | None = None,
    ) -> None:
        self.store = DojoTemplateStore(template_root)
        candidates: list[tuple[str, str, Path]] = []
        for mode, record in self.store.records().items():
            if record.configured:
                candidates.append((mode, f"user-{mode}x{mode}", record.path))

        explicit = Path(template_path) if template_path is not None else legacy_source_template_path()
        if explicit.exists():
            candidates.append(("legacy", "source-local-calibration", explicit))

        if not candidates:
            raise RuntimeError("DOJO_TRAINER_TEMPLATE_REQUIRED")

        normalized_scales = tuple(
            sorted({max(0.70, min(1.30, float(value))) for value in scales})
        ) or (1.0,)
        primary_mode, primary_source, primary_path = candidates[0]
        super().__init__(
            threshold=threshold,
            template_path=primary_path,
            memory_seconds=memory_seconds,
            scales=normalized_scales,
        )

        visual_templates = []
        for mode, source_name, path in candidates:
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None or image.size == 0:
                continue
            visual_templates.append(
                (
                    mode,
                    source_name,
                    cv2.cvtColor(image, cv2.COLOR_BGR2GRAY),
                    float(self.threshold),
                    normalized_scales,
                )
            )
        if not visual_templates:
            raise RuntimeError("DOJO_TRAINER_TEMPLATE_DECODE_FAILED")

        self._visual_templates = tuple(visual_templates)
        self.template_source = primary_source
        self.template_mode = primary_mode
        self.last_raw_template_source = primary_source
        self.last_raw_template_mode = primary_mode
        self.last_accepted_template_source: str | None = None
        self.last_accepted_template_mode: str | None = None
        self.last_rejection_reason = ""

    def describe(self) -> str:
        modes = ",".join(mode for mode, *_ in self._visual_templates)
        return f"templates={len(self._visual_templates)} modes={modes} threshold={self.threshold:.3f}"

    def diagnostics_text(self, *, limit: int = 8) -> str:
        del limit
        return (
            f"raw={self.last_raw_score:.3f} need={self.threshold:.3f} "
            f"scale={self.last_raw_scale:.3f} mode={self.last_raw_template_mode} "
            f"template={self.last_raw_template_source} rejection={self.last_rejection_reason or '-'}"
        )

    def _best_visual(self, frame_bgr: np.ndarray, *, arena_rect=None) -> LeaderMatchV2 | None:
        roi, offset_x, offset_y = self._roi(frame_bgr, arena_rect)
        if roi.size == 0:
            return None
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        raw_best = None
        accepted_by_mode: dict[str, tuple] = {}
        for mode, source_name, template_gray, required_threshold, source_scales in self._visual_templates:
            original_h, original_w = template_gray.shape[:2]
            mode_best = None
            for scale in source_scales:
                width = max(8, round(original_w * scale))
                height = max(8, round(original_h * scale))
                if width > gray.shape[1] or height > gray.shape[0]:
                    continue
                interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
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
                if raw_best is None or candidate[0] > raw_best[0]:
                    raw_best = candidate
                if mode_best is None or candidate[0] > mode_best[0]:
                    mode_best = candidate
            if mode_best is not None and mode_best[0] >= mode_best[6]:
                accepted_by_mode[mode] = mode_best

        if raw_best is None:
            return None
        score, scale, location, _, mode, source_name, required_threshold = raw_best
        self.last_raw_score = score
        self.last_raw_scale = scale
        self.last_raw_template_mode = mode
        self.last_raw_template_source = source_name
        self.last_raw_location = (offset_x + location[0], offset_y + location[1])
        self.last_accepted_template_mode = None
        self.last_accepted_template_source = None
        self.last_rejection_reason = "below-threshold"

        accepted = sorted(accepted_by_mode.values(), key=lambda item: item[0], reverse=True)
        if not accepted:
            return None

        best = accepted[0]
        if len(accepted) > 1:
            second = accepted[1]
            if best[4] != second[4] and abs(best[0] - second[0]) < 0.015:
                best_center = (
                    best[2][0] + best[3][0] * 0.5,
                    best[2][1] + best[3][1] * 0.5,
                )
                second_center = (
                    second[2][0] + second[3][0] * 0.5,
                    second[2][1] + second[3][1] * 0.5,
                )
                if float(np.hypot(best_center[0] - second_center[0], best_center[1] - second_center[1])) > 24.0:
                    self.last_rejection_reason = "mode-ambiguous"
                    return None

        score, scale, location, size, mode, source_name, required_threshold = best
        left = offset_x + location[0]
        top = offset_y + location[1]
        width, height = size
        self.last_accepted_template_mode = mode
        self.last_accepted_template_source = source_name
        self.last_rejection_reason = ""
        return LeaderMatchV2(
            score=score,
            bbox=(left, top, width, height),
            foot=(left + width * 0.50, top + height * 0.88),
            source="visual",
            scale=scale,
        )


def install_user_dojo_leader_detector() -> None:
    """Install the external-template detector before Trainer search modules are imported."""

    from . import post_combat_v03c

    post_combat_v03c.PersistentDojoLeaderDetector = UserDojoLeaderDetector


__all__ = [
    "DEFAULT_DOJO_TEMPLATE_STORE",
    "DOJO_TEMPLATE_MODES",
    "DojoTemplateRecord",
    "DojoTemplateStore",
    "UserDojoLeaderDetector",
    "default_template_root",
    "install_user_dojo_leader_detector",
    "legacy_source_template_path",
    "normalize_template_mode",
]
