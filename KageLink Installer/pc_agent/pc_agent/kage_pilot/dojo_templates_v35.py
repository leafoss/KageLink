"""Canonical RAW-only Dojo Trainer template boundary."""

from __future__ import annotations

from pathlib import Path

from .dojo_raw_trainer_v351 import (
    DEFAULT_DOJO_TEMPLATE_STORE,
    DojoTemplateRecord,
    DojoTemplateStore,
    RAW_TEMPLATE_BYTES,
    RAW_TEMPLATE_CELL_SIZE,
    RAW_TEMPLATE_FILENAMES,
    RAW_TEMPLATE_PIXEL_SIZE,
    RAW_TEMPLATE_SHA256,
    RawDojoLeaderDetector,
    default_template_root,
    ensure_canonical_raw_templates,
    normalize_template_mode,
)
from .post_combat_v03c import (
    PersistentDojoLeaderDetector as _PersistentDojoLeaderDetector,
)


DOJO_TEMPLATE_MODES = ("32", "64")
TEMPLATE_FILENAMES = dict(RAW_TEMPLATE_FILENAMES)
UserDojoLeaderDetector = RawDojoLeaderDetector


def legacy_source_template_path() -> Path:
    """Compatibility path; no legacy/fallback image is ever loaded."""

    return default_template_root() / RAW_TEMPLATE_FILENAMES["32"]


def install_user_dojo_leader_detector() -> None:
    """Install exact RAW matching without resize, filtering or fallback assets."""

    ensure_canonical_raw_templates()
    from . import post_combat_v03c

    post_combat_v03c.PersistentDojoLeaderDetector = RawDojoLeaderDetector


__all__ = [
    "DEFAULT_DOJO_TEMPLATE_STORE",
    "DOJO_TEMPLATE_MODES",
    "DojoTemplateRecord",
    "DojoTemplateStore",
    "RAW_TEMPLATE_BYTES",
    "RAW_TEMPLATE_CELL_SIZE",
    "RAW_TEMPLATE_PIXEL_SIZE",
    "RAW_TEMPLATE_SHA256",
    "UserDojoLeaderDetector",
    "default_template_root",
    "ensure_canonical_raw_templates",
    "install_user_dojo_leader_detector",
    "legacy_source_template_path",
    "normalize_template_mode",
]
