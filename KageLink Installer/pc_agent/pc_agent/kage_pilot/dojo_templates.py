"""Canonical immutable RAW Dojo Trainer template boundary."""

from __future__ import annotations

from .dojo_templates_v35 import (
    DEFAULT_DOJO_TEMPLATE_STORE,
    DOJO_TEMPLATE_MODES,
    DojoTemplateRecord,
    DojoTemplateStore,
    RAW_TEMPLATE_BYTES,
    RAW_TEMPLATE_CELL_SIZE,
    RAW_TEMPLATE_PIXEL_SIZE,
    RAW_TEMPLATE_SHA256,
    UserDojoLeaderDetector,
    default_template_root,
    ensure_canonical_raw_templates,
    install_user_dojo_leader_detector,
    legacy_source_template_path,
    normalize_template_mode,
)

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
