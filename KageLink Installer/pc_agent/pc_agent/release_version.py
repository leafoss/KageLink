from __future__ import annotations

import re
import sys
from pathlib import Path


_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def release_version_path() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle).resolve() / "RELEASE_VERSION"
    return Path(__file__).resolve().parents[3] / "RELEASE_VERSION"


def release_version() -> str:
    path = release_version_path()
    try:
        value = path.read_text(encoding="utf-8-sig").strip()
    except OSError as error:
        raise RuntimeError(f"RELEASE_VERSION_UNAVAILABLE: {path}") from error
    if not _SEMVER.fullmatch(value):
        raise RuntimeError(f"RELEASE_VERSION_INVALID: {value!r}")
    return value


__all__ = ["release_version", "release_version_path"]
