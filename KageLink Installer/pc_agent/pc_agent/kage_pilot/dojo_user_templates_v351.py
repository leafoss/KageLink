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

import numpy as np

from . import dojo_raw_trainer_v351 as legacy


RAW_TEMPLATE_BYTES = legacy.RAW_TEMPLATE_BYTES
RAW_TEMPLATE_CELL_SIZE = legacy.RAW_TEMPLATE_CELL_SIZE
RAW_TEMPLATE_FILENAMES = legacy.RAW_TEMPLATE_FILENAMES
RAW_TEMPLATE_PIXEL_SIZE = legacy.RAW_TEMPLATE_PIXEL_SIZE
RAW_TEMPLATE_SHA256 = legacy.RAW_TEMPLATE_SHA256

_ORIGINAL_TRAINER_SEARCH = None
_PIPELINE_INSTALLED = False


def default_template_root() -> Path:
    return legacy.default_template_root()


def normalize_template_mode(mode: str | int) -> str:
    return legacy.normalize_template_mode(mode)


def _decode_png_unchanged(raw: bytes) -> np.ndarray:
    """Decode only for matching; never rewrite, resize or filter the supplied PNG."""

    return legacy._decode_png_unchanged(bytes(raw))


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
    active: bool = False
    source: str = "none"
    removed_by_user: bool = False

    def to_public_dict(self) -> dict:
        return {
            "mode": self.mode,
            "active": self.active,
            "configured": self.configured,
            "source": self.source,
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "cell_size": self.cell_size,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "updated_at": self.updated_at,
            "original_filename": self.original_filename,
            "removed_by_user": self.removed_by_user,
            "raw": self.raw,
            "template_modified": False,
        }


class DojoTemplateStore:
    """Persist the exact PNG selected in the Images tab as detector authority."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_template_root()
        self.metadata_path = self.root / "templates.json"

    @staticmethod
    def _empty_metadata() -> dict:
        return {"version": 3, "templates": {}}

    def template_path(self, mode: str | int) -> Path:
        return self.root / RAW_TEMPLATE_FILENAMES[normalize_template_mode(mode)]

    def _read_metadata(self) -> dict:
        try:
            value = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._empty_metadata()
        templates = value.get("templates") if isinstance(value, dict) else None
        return {
            "version": 3,
            "templates": templates if isinstance(templates, dict) else {},
        }

    def _write_metadata(self, value: dict) -> None:
        payload = {
            "version": 3,
            "templates": value.get("templates", {}) if isinstance(value, dict) else {},
        }
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.metadata_path)

    @staticmethod
    def _decode_image(raw: bytes) -> np.ndarray:
        return _decode_png_unchanged(raw)

    def _entry_for_valid_file(
        self,
        mode: str,
        raw: bytes,
        image: np.ndarray,
        *,
        source: str,
        original_filename: str,
        updated_at: str | None = None,
    ) -> dict:
        height, width = image.shape[:2]
        return {
            "file": self.template_path(mode).name,
            "active": True,
            "configured": True,
            "source": source,
            "width": int(width),
            "height": int(height),
            "cell_size": int(RAW_TEMPLATE_CELL_SIZE[mode]),
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
            "original_filename": Path(original_filename).name or self.template_path(mode).name,
            "removed_by_user": False,
            "raw": True,
            "template_modified": False,
        }

    def initialize_factory_default(self, mode: str | int) -> DojoTemplateRecord:
        """Create a factory default only when this mode has never had saved state."""

        value = normalize_template_mode(mode)
        metadata = self._read_metadata()
        if value in metadata["templates"]:
            return self.record(value)

        path = self.template_path(value)
        if path.exists():
            try:
                raw = path.read_bytes()
                image = _decode_png_unchanged(raw)
                digest = hashlib.sha256(raw).hexdigest()
                source = "default" if digest == RAW_TEMPLATE_SHA256[value] else "user"
                metadata["templates"][value] = self._entry_for_valid_file(
                    value,
                    raw,
                    image,
                    source=source,
                    original_filename=path.name,
                )
                self._write_metadata(metadata)
                return self.record(value)
            except (OSError, ValueError):
                # There is no trustworthy saved state. Treat this as first-run setup.
                pass

        return self.restore_default(value, initial=True)

    def save(
        self,
        mode: str | int,
        raw: bytes,
        *,
        original_filename: str = "",
    ) -> DojoTemplateRecord:
        value = normalize_template_mode(mode)
        payload = bytes(raw)
        image = _decode_png_unchanged(payload)
        destination = self.template_path(value)
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".png.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, destination)

        metadata = self._read_metadata()
        metadata["templates"][value] = self._entry_for_valid_file(
            value,
            payload,
            image,
            source="user",
            original_filename=original_filename or destination.name,
        )
        self._write_metadata(metadata)
        record = self.record(value)
        print(
            "DOJO_USER_TEMPLATE_SAVED "
            f"mode={value} size={record.width}x{record.height} sha256={record.sha256} "
            "source=user modified=false"
        )
        return record

    def remove(self, mode: str | int) -> DojoTemplateRecord:
        value = normalize_template_mode(mode)
        try:
            self.template_path(value).unlink()
        except FileNotFoundError:
            pass
        metadata = self._read_metadata()
        metadata["templates"][value] = {
            "file": self.template_path(value).name,
            "active": False,
            "configured": False,
            "source": "none",
            "cell_size": int(RAW_TEMPLATE_CELL_SIZE[value]),
            "removed_by_user": True,
            "raw": True,
            "template_modified": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_metadata(metadata)
        print(f"DOJO_USER_TEMPLATE_REMOVED mode={value} source=none")
        return self.record(value)

    def restore_default(self, mode: str | int, *, initial: bool = False) -> DojoTemplateRecord:
        value = normalize_template_mode(mode)
        payload = bytes(RAW_TEMPLATE_BYTES[value])
        image = _decode_png_unchanged(payload)
        destination = self.template_path(value)
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".png.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, destination)

        metadata = self._read_metadata()
        metadata["templates"][value] = self._entry_for_valid_file(
            value,
            payload,
            image,
            source="default",
            original_filename=f"dojo_trainer_{value}_default.png",
        )
        self._write_metadata(metadata)
        record = self.record(value)
        event = "DOJO_DEFAULT_TEMPLATE_INITIALIZED" if initial else "DOJO_DEFAULT_TEMPLATE_RESTORED"
        print(f"{event} mode={value} source=default sha256={record.sha256}")
        return record

    def record(self, mode: str | int) -> DojoTemplateRecord:
        value = normalize_template_mode(mode)
        metadata = self._read_metadata()
        entry = metadata["templates"].get(value)
        if not isinstance(entry, dict):
            entry = {}
        path = self.root / str(entry.get("file") or RAW_TEMPLATE_FILENAMES[value])
        removed = bool(entry.get("removed_by_user"))
        explicitly_disabled = entry.get("configured") is False or entry.get("active") is False
        if removed or explicitly_disabled:
            return DojoTemplateRecord(
                value,
                path,
                False,
                cell_size=int(RAW_TEMPLATE_CELL_SIZE[value]),
                active=False,
                source="none",
                removed_by_user=removed,
            )
        if not path.exists():
            return DojoTemplateRecord(
                value,
                path,
                False,
                cell_size=int(RAW_TEMPLATE_CELL_SIZE[value]),
                active=False,
                source=str(entry.get("source") or "none"),
                removed_by_user=removed,
            )
        try:
            raw = path.read_bytes()
            image = _decode_png_unchanged(raw)
        except (OSError, ValueError):
            return DojoTemplateRecord(
                value,
                path,
                False,
                cell_size=int(RAW_TEMPLATE_CELL_SIZE[value]),
                active=False,
                source=str(entry.get("source") or "none"),
                removed_by_user=removed,
            )
        height, width = image.shape[:2]
        digest = hashlib.sha256(raw).hexdigest()
        source = str(entry.get("source") or "").strip().lower()
        if source not in {"user", "default"}:
            source = "default" if digest == RAW_TEMPLATE_SHA256[value] else "user"
        return DojoTemplateRecord(
            value,
            path,
            True,
            int(width),
            int(height),
            len(raw),
            digest,
            str(entry.get("updated_at") or "") or None,
            str(entry.get("original_filename") or path.name),
            int(RAW_TEMPLATE_CELL_SIZE[value]),
            True,
            True,
            source,
            False,
        )

    def records(self) -> dict[str, DojoTemplateRecord]:
        return {mode: self.record(mode) for mode in ("32", "64")}

    def has_any(self) -> bool:
        return any(record.configured for record in self.records().values())

    def public_status(self) -> dict:
        records = self.records()
        modes = [mode for mode, record in records.items() if record.configured]
        return {
            "ready": bool(modes),
            "storage": str(self.root),
            "configured_modes": modes,
            "raw_only": True,
            "template_processing": "denied",
            "templates": {mode: record.to_public_dict() for mode, record in records.items()},
        }

    def image_base64(self, mode: str | int) -> str:
        record = self.record(mode)
        if not record.configured:
            raise FileNotFoundError("DOJO_TEMPLATE_NOT_CONFIGURED")
        return base64.b64encode(record.path.read_bytes()).decode("ascii")


DEFAULT_DOJO_TEMPLATE_STORE = DojoTemplateStore()


def ensure_factory_defaults(
    store: DojoTemplateStore | None = None,
) -> dict[str, DojoTemplateRecord]:
    """Compatibility initialization that never overwrites saved or removed state."""

    target = store or DEFAULT_DOJO_TEMPLATE_STORE
    return {mode: target.initialize_factory_default(mode) for mode in ("32", "64")}


# Historical name retained for imports; semantics are now non-destructive.
ensure_canonical_raw_templates = ensure_factory_defaults


class UserDojoLeaderDetector(legacy.RawDojoLeaderDetector):
    """Exact native-size matcher backed only by active Images-tab PNG files."""

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
        ensure_factory_defaults(self.store)
        rows = []
        self._active_template_sources: dict[str, str] = {}
        for mode in ("32", "64"):
            record = self.store.record(mode)
            if not record.configured:
                continue
            raw = record.path.read_bytes()
            pixels = _decode_png_unchanged(raw)
            row = legacy.RawDojoTemplate(
                mode,
                RAW_TEMPLATE_CELL_SIZE[mode],
                record.path,
                str(record.sha256),
                pixels,
            )
            rows.append(row)
            self._active_template_sources[mode] = record.source
            print(
                "DOJO_ACTIVE_TEMPLATE_LOADED "
                f"mode={mode} cell={int(row.cell_size)} size={row.width}x{row.height} "
                f"channels={pixels.shape[2]} sha256={row.sha256} source={record.source} "
                f"path={record.path} modified=false"
            )
        if not rows:
            raise RuntimeError("DOJO_TRAINER_RAW_TEMPLATE_REQUIRED")
        self._raw_templates = tuple(rows)
        self._visual_templates = tuple(
            (
                row.mode,
                f"raw-{row.mode}-{row.sha256[:12]}",
                row.pixels,
                self.threshold,
                (1.0,),
            )
            for row in rows
        )
        self._template_rows = tuple(item[:4] for item in self._visual_templates)
        self.template_source = self._visual_templates[0][1]
        self.template_mode = self._visual_templates[0][0]
        self.scales = self.auto_scales = self.active_scan_scales = (1.0,)
        self.active_scan_mode = ",".join(row.mode for row in rows)
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


RawDojoLeaderDetector = UserDojoLeaderDetector
RawWindowsGameFrameSource = legacy.RawWindowsGameFrameSource
RawDojoTemplate = legacy.RawDojoTemplate


def raw_search_trainer_until_visible_safe(*args, **kwargs):
    """Run the validated search with the active user-owned templates injected."""

    from . import post_combat_v03c, recorder

    if _ORIGINAL_TRAINER_SEARCH is None:
        raise RuntimeError("DOJO_RAW_SEARCH_PROVIDER_MISSING")
    old_source = recorder.WindowsGameFrameSource
    old_detector = post_combat_v03c.PersistentDojoLeaderDetector
    recorder.WindowsGameFrameSource = RawWindowsGameFrameSource
    post_combat_v03c.PersistentDojoLeaderDetector = UserDojoLeaderDetector
    print(
        "DOJO_TRAINER_SEARCH_STARTED frame=raw-client roi=full-frame scales=1.00 "
        "template_processing=denied source=images-tab"
    )
    try:
        return _ORIGINAL_TRAINER_SEARCH(*args, **kwargs)
    finally:
        recorder.WindowsGameFrameSource = old_source
        post_combat_v03c.PersistentDojoLeaderDetector = old_detector


def install_user_owned_template_pipeline() -> None:
    """Make the persistent Images-tab files authoritative in every Dojo process."""

    global _ORIGINAL_TRAINER_SEARCH, _PIPELINE_INSTALLED
    ensure_factory_defaults()
    from . import dojo_fight_v03i, post_combat_v03c, trainer_search_v03k

    current_search = trainer_search_v03k.search_trainer_until_visible_safe
    if _ORIGINAL_TRAINER_SEARCH is None and not bool(
        getattr(current_search, "_kagelink_user_templates", False)
    ):
        if current_search is legacy.raw_search_trainer_until_visible_safe:
            candidate = getattr(legacy, "_ORIGINAL_TRAINER_SEARCH", None)
            if candidate is not None:
                _ORIGINAL_TRAINER_SEARCH = candidate
        else:
            _ORIGINAL_TRAINER_SEARCH = current_search
    raw_search_trainer_until_visible_safe._kagelink_user_templates = True

    legacy.DojoTemplateRecord = DojoTemplateRecord
    legacy.DojoTemplateStore = DojoTemplateStore
    legacy.DEFAULT_DOJO_TEMPLATE_STORE = DEFAULT_DOJO_TEMPLATE_STORE
    legacy.ensure_canonical_raw_templates = ensure_factory_defaults
    legacy.RawDojoLeaderDetector = UserDojoLeaderDetector
    legacy.raw_search_trainer_until_visible_safe = raw_search_trainer_until_visible_safe
    legacy.install_raw_trainer_pipeline = install_user_owned_template_pipeline

    trainer_search_v03k.PersistentDojoLeaderDetector = UserDojoLeaderDetector
    trainer_search_v03k.search_trainer_until_visible_safe = raw_search_trainer_until_visible_safe
    dojo_fight_v03i.search_trainer_until_visible = raw_search_trainer_until_visible_safe
    post_combat_v03c.PersistentDojoLeaderDetector = UserDojoLeaderDetector

    for module_name, attribute in (
        ("pc_agent.kage_pilot.dojo_templates_v35", "UserDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_templates", "UserDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_resolution_bridge_v351", "RawDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_resolution_bridge_v351", "ResolutionIndependentDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_resolution_scope_compat_v351", "ResolutionIndependentDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_resolution_runtime_fix_v351", "BoundedResolutionIndependentDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_position_bridge", "UserDojoLeaderDetector"),
    ):
        module = sys.modules.get(module_name)
        if module is not None:
            setattr(module, attribute, UserDojoLeaderDetector)

    _PIPELINE_INSTALLED = True
    print(
        "DOJO_USER_TEMPLATE_PIPELINE_INSTALLED modes=32,64 scales=1.00 "
        "frame=raw-client authority=images-tab"
    )


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
    "UserDojoLeaderDetector",
    "default_template_root",
    "ensure_canonical_raw_templates",
    "ensure_factory_defaults",
    "install_user_owned_template_pipeline",
    "normalize_template_mode",
    "raw_search_trainer_until_visible_safe",
]
