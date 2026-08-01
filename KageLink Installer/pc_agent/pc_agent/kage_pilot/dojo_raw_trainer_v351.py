from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from .post_combat_v03b import LeaderMatchV2


RAW_TEMPLATE_BASE64 = {
    "32": "iVBORw0KGgoAAAANSUhEUgAAAB4AAAAfCAYAAADwbH0HAAADr0lEQVRIS62W2W7bMBBFSVGS16BflrZA+zdt0KeiG/pU9EuTOF60FGfkq4xoOXnpDQLTJGfmzmrGH59v+yIWoSxj6LoQuq4PTduGMqUg9KEPbdvZmv3lsgwPjwdbF0UMRRHC/tCMMut1FXa7k52hT1guUtjtT3Yv/rp793wyg7brRgV934cY4/iZsOjubdd1QNl+34Su7wIOXcPEcJFi6FrHcFmGp/3JvE2pGL0G5ulZMUaBJ4JhsF7VRkSoqhgOx3YwnIckh85JASBUSgdndZ1MuddzzWPtx99f3vcSBAijVEIwxB4K8SzGYb3dLEYZ3ZEckfJezhGKf75+MI8pBhRXZXrV++NpUOrzjRx4SVaEKLL48+5tH0McD3PosljjFflmrZz6LlBFA7x7s12E+8fhu8D+RVVjALzEHPjCq6vS7vsQj4RdwargxhzLCCHYH9pJTnLgHW3zsDua5/zTQ9xX/jC2XJQhxWDemoeROhgMUx+W45yZkBeJhxHYLGx97Y7g04TM7ul42U7X1oK8AhA7ntqRcF4PORRqYIYlwKexOU8l2qxKcVIc200VmrYPTdOOIxZgzLcl8CSBCFnoNavBXGi5DBCgX0+nZ09QwGTCa+XZn3mjggjG759u+0WdQtNchgZABuSEgFeuNbWSkwCcA7tTxGxWn0MxV2gI0qtjaFMMdVlYF+h8jkRdDeFXNHU2aScg4/maMKc0zaHHnGEPpWk07D2mjxnGKPfTSMj7XEpuNtXYr3y/RsKvLzwGsMMAlS0jChXzXKOSPaaXH7k5CQ8eFMx2cDEyXwJRAIoEhmkrFWZuTHMbspt1HR53tOpw9uIAETCgpw6YKz7kIDYXVjxVVPRomPSxjKoQ8jz7dxmYIwlyEn5UsgepyeTy+B8kvNeS197kIZDnKA+pCot75sH5dxdyvKOQVV7zYsSwHgy2fq24EKQSYUuubK8dhkkeBQiVvETc5GKPtfcWR62d7ML5IiFUlcL+/uFga1h79nY3pXFvDj5i3FNFg7GPc4M23mbGp4zq1YHCqko2Pgnl07lW8A7gocKOLN5ajgm1fyepSLh8PLb2sEOh9hX2uYIU8loRJqH+++1jL6NABhV6eQggoFflZlXZ80eE5AmFVlVD3wsisbJJN5A1j68xBBqfGEQ5E8/n2+ed9xeD4lo0ZIfPsarnjCu/KCWnCjvjT4q9wRwQBYqebFihzbVTXo30nh7x8vpm+9zHtNlqORSk7lghnfPJGsL8YZyW+wfmTI7GL8kXIgAAAABJRU5ErkJggg==",
    "64": "iVBORw0KGgoAAAANSUhEUgAAAD0AAABACAYAAACp3n/2AAAFM0lEQVRoQ+2by44cRRBFq1/ztvgGxAbxJywQCLbs+AxAeAESCHnlT/VMT08/ZlA+Tqn7TIer2rYAOX03qcqqyqyIGxEZGZ09+fvXb5+6ruum00lqusfHfNldXMxzu1ptczsW290utzfX57nl/aeujLvbPeb2so5/X+/7eYNx57NZ7TnE41MZF0wn09wek2PSpNCvfvsuUwDDAM2hsfkcS8hN//wQA2YY8DxM3N49HPRjedMyfbd6KEx5nqurRW6Xy01ubbHGxfmsa1NozPuY7b8PdtUkrPmnp9JOJqXf1zOoFRjv5uost/DI99oy34Y2hf7rl2+y0sZoKGE6q8zt0PUhsJj7VfExfHk2K+Pbt0Hvw/oOGAaRJTh6X10WizhmuW0KPeTT9slT4feJ9oBo7FWA987OyjXf5fHAB/XpaJKx8Pv/K6EXi/Jxm035uEjTgPsIYQ0zHsQiND5ag3XfH2VkHsfzRWQBKz2hZ7opoV///n0WevVw6GtoEE2R8cDUYl4s4H3Nfr05ZChav5kPvOu8Sa42hfY6DQO973Xl+lTY1+xb+CbrN/1ehx3VgXNuQBT/7KbEiDd3h/cT2hSaQHbKOpcAc+BdfQxgGc7kzhaln/FtQcD9UeaY5GxT6Nd//JBV4ShtHwRpP5pAtI+eGwK+yq7pdrnOLT5Oy3aK8W2RMHpxXpiul70v8zyrQLKgNoWOorczschHDPvWWPTM18wMnDqOYUtM83wSOmvEPhP47Kn9hucBWMp6U5i3ZdmSxs4HcvS2eftjokFP7Tc8D/hXhQb4FFHcmuV6eV+irWtbxIJFjQHHMqKEm+uSUW0rk9ttZbbo4pnSUKZjjREpE6RxeqZBE0J7nUbDMGmNmfkIjAcY11tYA6aoceHbXq+NIYb30abQ/oUDjdXtbHdefWi7Pa7hCFgEGLIMEDHmfvKGIQsAvJ/QptAuDK7XRNHjmrPvj83U0DT7Yo/POGfzwqQrOWYauL8fZ3EY5fdj0Seh9zVjRo3oftRP1J5Vpsf6ODCjIOo39leNZ0w3JXTEkMF+msI1SopqWcbQftzMvaiZm/fH3Pc1eFt/z7Qnj/BRCE0aCkPktkNRHOArMEcObiXafai2uvrJc9TKomrskAVESCcj2hYaDZmhDw18HzgGwDS7LmeCQ4y6Ho5FXdda3N1y/Xw/3YTQf/5chEYTXj8jJUT9Bsz59BAYm9ExH5ZipiML4HTTfmxoU2ibN4g0Z4a9Px5ar6PzaMDjD2HIAujviyP3R3wafNRCk5wAa9rrawS/919ZQETWvgW2KbQzMjMMg6x7kSbBUDR2JsZ4LkgCLOahZojM6/XYFul5YDpVb9sUmhoZGKorjwWa5uwIlsS6CfgdmvtD0R/LmHMGpQ7naM9z9PeWnHZZTQqNT/d15uo7hjXJeuvcGF97c1syMIBvRb4GYMTPjUUUUxgvlQHaFPqnH7/OKvny88J07zOK5kPMEgN4PtI4MMM+WwIzi1rVpErKb2f89wPw3YAo76ie5m1b6K++KOukfdfrIXAGhkaJCZwEhBk/76huRsYChqO8wcjRG/NuSuioMBgxDMysLcQ+C2DeZz+vL8t8nDLy93ANo2RqixoL2K8btoD0f7A2hfbW0gyf6jPAVVKYhTF+FY3Wb19jOZwvoxJyaizIPt2k0NTIhs5vj2Xc6zMMsQ47qke1uYjZIWBJwPJkppsU+tXLssvi99zorEkEMwv6jKpakE/w27df1PPZXi3YlV1eHGZ+gHGwDL7b/VhWspgmhf4H2l+z6ucPI9EAAAAASUVORK5CYII=",
}
RAW_TEMPLATE_BYTES = {mode: base64.b64decode(value, validate=True) for mode, value in RAW_TEMPLATE_BASE64.items()}
RAW_TEMPLATE_SHA256 = {mode: hashlib.sha256(value).hexdigest() for mode, value in RAW_TEMPLATE_BYTES.items()}
# 32/64 are game cell modes. The user-supplied RAW crops themselves are 30x31 and 61x64.
RAW_TEMPLATE_PIXEL_SIZE = {"32": (30, 31), "64": (61, 64)}
RAW_TEMPLATE_CELL_SIZE = {"32": 32.0, "64": 64.0}
RAW_TEMPLATE_FILENAMES = {"32": "dojo_trainer_32.png", "64": "dojo_trainer_64.png"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_INSTALLED = False
_ORIGINAL_TRAINER_SEARCH = None


def _local_app_data_root() -> Path:
    value = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if value:
        return Path(value)
    return Path.home() / ("AppData/Local" if os.name == "nt" else ".local/share")


def default_template_root() -> Path:
    return _local_app_data_root() / "KageLink" / "data" / "kage_pilot" / "templates"


def normalize_template_mode(mode: str | int) -> str:
    value = str(mode).strip()
    if value not in {"32", "64"}:
        raise ValueError(f"DOJO_TEMPLATE_MODE_INVALID:{value}")
    return value


def _decode_png_unchanged(raw: bytes) -> np.ndarray:
    if not raw or not bytes(raw).startswith(PNG_SIGNATURE):
        raise ValueError("DOJO_RAW_TEMPLATE_NOT_PNG")
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None or image.size == 0:
        raise ValueError("DOJO_RAW_TEMPLATE_DECODE_FAILED")
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] not in {3, 4}:
        raise ValueError("DOJO_RAW_TEMPLATE_FORMAT_INVALID")
    image.setflags(write=False)
    return image


def _validate_canonical_bytes(mode: str | int, raw: bytes) -> np.ndarray:
    value = normalize_template_mode(mode)
    payload = bytes(raw)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != RAW_TEMPLATE_SHA256[value]:
        raise ValueError(
            f"DOJO_RAW_TEMPLATE_HASH_INVALID:mode={value}:got={digest}:expected={RAW_TEMPLATE_SHA256[value]}"
        )
    image = _decode_png_unchanged(payload)
    height, width = image.shape[:2]
    if (width, height) != RAW_TEMPLATE_PIXEL_SIZE[value]:
        raise ValueError(
            f"DOJO_RAW_TEMPLATE_DIMENSIONS_INVALID:mode={value}:got={width}x{height}:"
            f"expected={RAW_TEMPLATE_PIXEL_SIZE[value][0]}x{RAW_TEMPLATE_PIXEL_SIZE[value][1]}"
        )
    return image


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
    cell_size: int | None = None
    raw: bool = True

    def to_public_dict(self) -> dict:
        return {
            "mode": self.mode,
            "configured": self.configured,
            "width": self.width,
            "height": self.height,
            "cell_size": self.cell_size,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "updated_at": self.updated_at,
            "original_filename": self.original_filename,
            "raw": self.raw,
            "template_modified": False,
        }


class DojoTemplateStore:
    """Persist only the exact two RAW PNG byte streams supplied by Rafael."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_template_root()
        self.metadata_path = self.root / "templates.json"

    def template_path(self, mode: str | int) -> Path:
        return self.root / RAW_TEMPLATE_FILENAMES[normalize_template_mode(mode)]

    def _read_metadata(self) -> dict:
        try:
            value = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return {"version": 2, "templates": {}}
        templates = value.get("templates") if isinstance(value, dict) else None
        return {"version": 2, "templates": templates if isinstance(templates, dict) else {}}

    def _write_metadata(self, value: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.metadata_path)

    @staticmethod
    def _decode_image(raw: bytes) -> np.ndarray:
        return _decode_png_unchanged(bytes(raw))

    def save(self, mode: str | int, raw: bytes, *, original_filename: str = "") -> DojoTemplateRecord:
        value = normalize_template_mode(mode)
        payload = bytes(raw)
        image = _validate_canonical_bytes(value, payload)
        height, width = image.shape[:2]
        updated_at = datetime.now(timezone.utc).isoformat()
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.template_path(value)
        temporary = destination.with_suffix(".png.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, destination)
        metadata = self._read_metadata()
        metadata["templates"][value] = {
            "file": destination.name,
            "width": width,
            "height": height,
            "cell_size": int(RAW_TEMPLATE_CELL_SIZE[value]),
            "size_bytes": len(payload),
            "sha256": RAW_TEMPLATE_SHA256[value],
            "updated_at": updated_at,
            "original_filename": Path(original_filename).name or f"dojo_trainer_{value}_raw.png",
            "raw": True,
            "template_modified": False,
        }
        self._write_metadata(metadata)
        return self.record(value)

    def remove(self, mode: str | int) -> DojoTemplateRecord:
        value = normalize_template_mode(mode)
        try:
            self.template_path(value).unlink()
        except FileNotFoundError:
            pass
        metadata = self._read_metadata()
        metadata["templates"].pop(value, None)
        self._write_metadata(metadata)
        return self.record(value)

    def record(self, mode: str | int) -> DojoTemplateRecord:
        value = normalize_template_mode(mode)
        path = self.template_path(value)
        if not path.exists():
            return DojoTemplateRecord(value, path, False, cell_size=int(RAW_TEMPLATE_CELL_SIZE[value]))
        try:
            raw = path.read_bytes()
            image = _validate_canonical_bytes(value, raw)
        except (OSError, ValueError):
            return DojoTemplateRecord(value, path, False, cell_size=int(RAW_TEMPLATE_CELL_SIZE[value]))
        metadata = self._read_metadata()["templates"].get(value, {})
        height, width = image.shape[:2]
        return DojoTemplateRecord(
            value,
            path,
            True,
            width,
            height,
            len(raw),
            RAW_TEMPLATE_SHA256[value],
            str(metadata.get("updated_at") or "") or None,
            str(metadata.get("original_filename") or "") or None,
            int(RAW_TEMPLATE_CELL_SIZE[value]),
            True,
        )

    def records(self) -> dict[str, DojoTemplateRecord]:
        return {mode: self.record(mode) for mode in ("32", "64")}

    def has_any(self) -> bool:
        return any(value.configured for value in self.records().values())

    def public_status(self) -> dict:
        records = self.records()
        modes = [mode for mode, value in records.items() if value.configured]
        return {
            "ready": len(modes) == 2,
            "storage": str(self.root),
            "configured_modes": modes,
            "raw_only": True,
            "template_processing": "denied",
            "templates": {mode: value.to_public_dict() for mode, value in records.items()},
        }

    def image_base64(self, mode: str | int) -> str:
        record = self.record(mode)
        if not record.configured:
            raise FileNotFoundError("DOJO_TEMPLATE_NOT_CONFIGURED")
        return base64.b64encode(record.path.read_bytes()).decode("ascii")


DEFAULT_DOJO_TEMPLATE_STORE = DojoTemplateStore()


def ensure_canonical_raw_templates(store: DojoTemplateStore | None = None) -> dict[str, DojoTemplateRecord]:
    target = store or DEFAULT_DOJO_TEMPLATE_STORE
    result = {}
    for mode in ("32", "64"):
        record = target.record(mode)
        if not record.configured or record.sha256 != RAW_TEMPLATE_SHA256[mode]:
            reason = "missing" if not record.path.exists() else "hash-mismatch"
            record = target.save(mode, RAW_TEMPLATE_BYTES[mode], original_filename=f"dojo_trainer_{mode}_raw.png")
            print(
                "DOJO_RAW_TEMPLATE_MATERIALIZED "
                f"mode={mode} reason={reason} size={record.width}x{record.height} "
                f"sha256={record.sha256} modified=false"
            )
        result[mode] = record
    return result


@dataclass(frozen=True, slots=True)
class RawDojoTemplate:
    mode: str
    cell_size: float
    path: Path
    sha256: str
    pixels: np.ndarray

    @property
    def width(self) -> int:
        return int(self.pixels.shape[1])

    @property
    def height(self) -> int:
        return int(self.pixels.shape[0])


class RawDojoLeaderDetector:
    """Direct BGR pixel matcher: no resize, grayscale, filters, masks or fallback."""

    def __init__(
        self,
        *,
        threshold: float = 0.88,
        template_path=None,
        memory_seconds: float = 180.0,
        scales=(1.0,),
        template_root: Path | str | None = None,
    ) -> None:
        del template_path, scales
        self.threshold = max(0.97, min(0.999999, float(threshold)))
        self.memory_seconds = max(1.0, min(300.0, float(memory_seconds)))
        self.store = DojoTemplateStore(template_root)
        ensure_canonical_raw_templates(self.store)
        rows = []
        for mode in ("32", "64"):
            record = self.store.record(mode)
            raw = record.path.read_bytes()
            pixels = _validate_canonical_bytes(mode, raw)
            row = RawDojoTemplate(mode, RAW_TEMPLATE_CELL_SIZE[mode], record.path, RAW_TEMPLATE_SHA256[mode], pixels)
            rows.append(row)
            print(
                "DOJO_RAW_TEMPLATE_LOADED "
                f"mode={mode} cell={int(row.cell_size)} size={row.width}x{row.height} "
                f"channels={pixels.shape[2]} sha256={row.sha256} path={record.path} modified=false"
            )
        self._raw_templates = tuple(rows)
        self._visual_templates = tuple((row.mode, f"raw-{row.mode}-{row.sha256[:12]}", row.pixels, self.threshold, (1.0,)) for row in rows)
        self._template_rows = tuple(item[:4] for item in self._visual_templates)
        self.template_source = self._visual_templates[0][1]
        self.template_mode = self._visual_templates[0][0]
        self.scales = self.auto_scales = self.active_scan_scales = (1.0,)
        self.active_scan_mode = "32,64"
        self.last_raw_score = -1.0
        self.last_raw_scale = 1.0
        self.last_raw_location = None
        self.last_raw_template_mode = "-"
        self.last_raw_template_source = "-"
        self.last_accepted_template_mode = None
        self.last_accepted_template_source = None
        self.last_accepted_template_scale = None
        self.last_rejection_reason = ""
        self.effective_tile_size = None
        self.last_search_roi = None
        self._last_visual = None
        self._last_visual_at = -1e9

    @property
    def has_anchor(self) -> bool:
        return self._last_visual is not None

    def describe(self) -> str:
        sizes = ",".join(f"{row.mode}:{row.width}x{row.height}" for row in self._raw_templates)
        return (
            f"raw=true modes=32,64 sizes={sizes} threshold={self.threshold:.6f} "
            "scales=1.00 template_processing=denied"
        )

    def diagnostics_text(self, *, limit: int = 8) -> str:
        del limit
        cell = "-" if self.effective_tile_size is None else f"{self.effective_tile_size:.0f}px"
        return (
            f"raw={self.last_raw_score:.6f} need={self.threshold:.6f} scale=1.000 "
            f"mode={self.last_raw_template_mode} effective_tile={cell} "
            f"template={self.last_raw_template_source} roi={self.last_search_roi} "
            f"modified=false rejection={self.last_rejection_reason or '-'}"
        )

    @staticmethod
    def _shift(match: LeaderMatchV2, flow) -> LeaderMatchV2:
        dx = float(getattr(flow, "dx", 0.0) or 0.0)
        dy = float(getattr(flow, "dy", 0.0) or 0.0)
        left, top, width, height = match.bbox
        return LeaderMatchV2(match.score, (round(left + dx), round(top + dy), width, height), (match.foot[0] + dx, match.foot[1] + dy), "memory", 1.0)

    def _best_visual(self, frame_bgr: np.ndarray, *, arena_rect=None) -> LeaderMatchV2 | None:
        del arena_rect
        if not isinstance(frame_bgr, np.ndarray) or frame_bgr.dtype != np.uint8 or frame_bgr.ndim != 3 or frame_bgr.shape[2] not in {3, 4}:
            raise ValueError("DOJO_RAW_FRAME_INVALID")
        frame = frame_bgr[:, :, :3]
        frame_height, frame_width = frame.shape[:2]
        self.last_search_roi = (0, 0, frame_width, frame_height)
        candidates = []
        for template in self._raw_templates:
            color = template.pixels[:, :, :3]
            if template.height > frame_height or template.width > frame_width:
                continue
            result = cv2.matchTemplate(frame, color, cv2.TM_SQDIFF_NORMED)
            minimum, _, location, _ = cv2.minMaxLoc(result)
            candidates.append((max(0.0, min(1.0, 1.0 - float(minimum))), int(template.cell_size), template, location))
        self.last_accepted_template_mode = self.last_accepted_template_source = self.last_accepted_template_scale = None
        self.effective_tile_size = None
        if not candidates:
            self.last_rejection_reason = "template-larger-than-frame"
            return None
        score, _, template, location = max(candidates, key=lambda item: (item[0], item[1]))
        left, top = int(location[0]), int(location[1])
        source = f"raw-{template.mode}-{template.sha256[:12]}"
        self.last_raw_score = float(score)
        self.last_raw_scale = 1.0
        self.last_raw_location = (left, top)
        self.last_raw_template_mode = template.mode
        self.last_raw_template_source = source
        self.last_rejection_reason = "below-threshold"
        print(
            "DOJO_RAW_MATCH_CANDIDATE "
            f"mode={template.mode} bbox={left},{top},{template.width},{template.height} "
            f"score={score:.6f} need={self.threshold:.6f} scale=1.000 "
            "frame_resized=false template_modified=false"
        )
        if score < self.threshold:
            return None
        self.last_accepted_template_mode = template.mode
        self.last_accepted_template_source = source
        self.last_accepted_template_scale = 1.0
        self.effective_tile_size = template.cell_size
        self.last_rejection_reason = ""
        try:
            from . import dojo_resolution_bridge_v351 as bridge
            bridge._write_geometry(template.mode, 1.0)
        except Exception:
            pass
        print(
            "DOJO_RAW_MATCH_CONFIRMED "
            f"mode={template.mode} cell={int(template.cell_size)} "
            f"bbox={left},{top},{template.width},{template.height} score={score:.6f} "
            "scale=1.000 frame_resized=false template_modified=false"
        )
        return LeaderMatchV2(float(score), (left, top, template.width, template.height), (left + template.width * 0.50, top + template.height * 0.88), "visual", 1.0)

    def find(self, frame_bgr: np.ndarray, *, arena_rect=None, flow=None, now: float | None = None):
        timestamp = time.monotonic() if now is None else float(now)
        if self._last_visual is not None and flow is not None:
            self._last_visual = self._shift(self._last_visual, flow)
        visual = self._best_visual(frame_bgr, arena_rect=arena_rect)
        if visual is not None:
            self._last_visual = visual
            self._last_visual_at = timestamp
            return visual
        if self._last_visual is not None and timestamp - self._last_visual_at <= self.memory_seconds:
            value = self._last_visual
            return LeaderMatchV2(value.score, value.bbox, value.foot, "memory", 1.0)
        return None


class RawWindowsGameFrameSource:
    """Original client pixels, losslessly transported as PNG through the frame contract."""

    def __init__(self, *, jpeg_quality: int = 100, output_size=None) -> None:
        del jpeg_quality, output_size
        from pc_agent.game_capture import GameCapture
        self.capture_engine = GameCapture(output_size=(960, 540), jpeg_quality=90)
        self._last_signature = None

    def capture(self):
        from pc_agent.game_capture import CapturedFrame, GameCaptureError, GameWindowMinimized, GameWindowMissing
        from pc_agent.game_window import locate_capture_target, show_state
        engine = self.capture_engine
        with engine._lock:
            target = locate_capture_target(engine.title)
            if target is None:
                raise GameWindowMissing("GAME_NOT_FOUND")
            if target.minimized:
                raise GameWindowMinimized("GAME_MINIMIZED")
            image, target = engine._capture_source(target)
            rgb = np.asarray(image)
            if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
                raise GameCaptureError("RAW_CLIENT_FRAME_INVALID")
            bgr = np.ascontiguousarray(rgb[:, :, ::-1])
            ok, encoded = cv2.imencode(".png", bgr, [int(cv2.IMWRITE_PNG_COMPRESSION), 0])
            if not ok:
                raise GameCaptureError("RAW_CLIENT_FRAME_ENCODE_FAILED")
            height, width = bgr.shape[:2]
            try:
                from . import dojo_resolution_bridge_v351 as bridge
                bridge._LAST_SOURCE_WIDTH = width
                bridge._LAST_SOURCE_HEIGHT = height
                bridge._LAST_CONTENT_RECT = (0, 0, width, height)
            except Exception:
                pass
            signature = (width, height, int(target.left), int(target.top))
            if signature != self._last_signature:
                print(
                    "DOJO_CAPTURE_CONTEXT "
                    f"client={width}x{height} capture={width}x{height} detection={width}x{height} "
                    f"detection_resized=false encoding=png-lossless origin={target.left},{target.top}"
                )
                self._last_signature = signature
            return CapturedFrame(bytes(encoded), width, height, target, "raw", show_state(target.game_hwnd))

    def close(self) -> None:
        self.capture_engine.close()


def raw_search_trainer_until_visible_safe(*args, **kwargs):
    """Run the validated search with RAW source/detector injected only for this call."""

    global _ORIGINAL_TRAINER_SEARCH
    from . import post_combat_v03c, recorder
    if _ORIGINAL_TRAINER_SEARCH is None:
        raise RuntimeError("DOJO_RAW_SEARCH_PROVIDER_MISSING")
    old_source = recorder.WindowsGameFrameSource
    old_detector = post_combat_v03c.PersistentDojoLeaderDetector
    recorder.WindowsGameFrameSource = RawWindowsGameFrameSource
    post_combat_v03c.PersistentDojoLeaderDetector = RawDojoLeaderDetector
    print("DOJO_TRAINER_SEARCH_STARTED frame=raw-client roi=full-frame scales=1.00 template_processing=denied")
    try:
        return _ORIGINAL_TRAINER_SEARCH(*args, **kwargs)
    finally:
        recorder.WindowsGameFrameSource = old_source
        post_combat_v03c.PersistentDojoLeaderDetector = old_detector


def install_raw_trainer_pipeline() -> None:
    global _INSTALLED, _ORIGINAL_TRAINER_SEARCH
    ensure_canonical_raw_templates()
    from . import dojo_fight_v03i, dojo_resolution_bridge_v351, dojo_templates, dojo_templates_v35, post_combat_v03c, trainer_search_v03k
    if _ORIGINAL_TRAINER_SEARCH is None:
        _ORIGINAL_TRAINER_SEARCH = trainer_search_v03k.search_trainer_until_visible_safe
    dojo_templates_v35.UserDojoLeaderDetector = RawDojoLeaderDetector
    dojo_templates.UserDojoLeaderDetector = RawDojoLeaderDetector
    trainer_search_v03k.PersistentDojoLeaderDetector = RawDojoLeaderDetector
    trainer_search_v03k.search_trainer_until_visible_safe = raw_search_trainer_until_visible_safe
    dojo_fight_v03i.search_trainer_until_visible = raw_search_trainer_until_visible_safe
    dojo_resolution_bridge_v351.ResolutionIndependentDojoLeaderDetector = RawDojoLeaderDetector
    for module_name, attribute in (
        ("pc_agent.kage_pilot.dojo_resolution_scope_compat_v351", "ResolutionIndependentDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_resolution_runtime_fix_v351", "BoundedResolutionIndependentDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_position_bridge", "UserDojoLeaderDetector"),
    ):
        module = sys.modules.get(module_name)
        if module is not None:
            setattr(module, attribute, RawDojoLeaderDetector)
    legacy = getattr(dojo_templates_v35, "_PersistentDojoLeaderDetector", None)
    if legacy is not None:
        post_combat_v03c.PersistentDojoLeaderDetector = legacy
    _INSTALLED = True
    print("DOJO_RAW_PIPELINE_INSTALLED modes=32,64 scales=1.00 frame=raw-client template_processing=denied")


__all__ = [
    "DEFAULT_DOJO_TEMPLATE_STORE",
    "DojoTemplateRecord",
    "DojoTemplateStore",
    "RAW_TEMPLATE_BYTES",
    "RAW_TEMPLATE_CELL_SIZE",
    "RAW_TEMPLATE_FILENAMES",
    "RAW_TEMPLATE_PIXEL_SIZE",
    "RAW_TEMPLATE_SHA256",
    "RawDojoLeaderDetector",
    "RawDojoTemplate",
    "RawWindowsGameFrameSource",
    "default_template_root",
    "ensure_canonical_raw_templates",
    "install_raw_trainer_pipeline",
    "normalize_template_mode",
    "raw_search_trainer_until_visible_safe",
]
