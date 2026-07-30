"""Canonical user-owned Dojo template boundary."""

from __future__ import annotations

from .dojo_templates_v35 import (
    DEFAULT_DOJO_TEMPLATE_STORE,
    DOJO_TEMPLATE_MODES,
    DojoTemplateRecord,
    DojoTemplateStore,
    UserDojoLeaderDetector,
    default_template_root,
    install_user_dojo_leader_detector,
    legacy_source_template_path,
    normalize_template_mode,
)

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
