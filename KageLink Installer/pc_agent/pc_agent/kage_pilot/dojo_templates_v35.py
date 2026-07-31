"""Canonical user-owned RAW Dojo Trainer template boundary."""

from __future__ import annotations

from pathlib import Path

from .dojo_user_templates_v351 import (
    DEFAULT_DOJO_TEMPLATE_STORE,
    DojoTemplateRecord,
    DojoTemplateStore,
    RAW_TEMPLATE_BYTES,
    RAW_TEMPLATE_CELL_SIZE,
    RAW_TEMPLATE_FILENAMES,
    RAW_TEMPLATE_PIXEL_SIZE,
    RAW_TEMPLATE_SHA256,
    UserDojoLeaderDetector,
    default_template_root,
    ensure_canonical_raw_templates,
    ensure_factory_defaults,
    install_user_owned_template_pipeline,
    normalize_template_mode,
)
from .post_combat_v03c import (
    PersistentDojoLeaderDetector as _PersistentDojoLeaderDetector,
)


DOJO_TEMPLATE_MODES = ("32", "64")
TEMPLATE_FILENAMES = dict(RAW_TEMPLATE_FILENAMES)


def legacy_source_template_path() -> Path:
    """Compatibility path for the initial 32-mode factory default only."""

    return default_template_root() / RAW_TEMPLATE_FILENAMES["32"]


def install_user_dojo_leader_detector() -> None:
    """Install exact native-size matching from the active Images-tab PNG files."""

    install_user_owned_template_pipeline()


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
    "ensure_factory_defaults",
    "install_user_dojo_leader_detector",
    "install_user_owned_template_pipeline",
    "legacy_source_template_path",
    "normalize_template_mode",
]
