from __future__ import annotations

import json
import locale
import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_CHANNELS = {"ooc", "ic"}
DEFAULT_MAX_MESSAGE_LENGTH = 32000
LEGACY_MAX_MESSAGE_LENGTH = 400


def _writable_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resource_root() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle).resolve()
    return Path(__file__).resolve().parent.parent


PROJECT_DIR = _writable_root()
RESOURCE_DIR = _resource_root()
CONFIG_PATH = PROJECT_DIR / "config.json"


@dataclass(slots=True)
class InputControlPreference:
    preferred_width: int
    preferred_height: int
    relative_left: int | None = None
    relative_top: int | None = None
    candidate_index: int | None = None
    parent_class: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_width": self.preferred_width,
            "preferred_height": self.preferred_height,
            "relative_left": self.relative_left,
            "relative_top": self.relative_top,
            "candidate_index": self.candidate_index,
            "parent_class": self.parent_class,
        }


@dataclass(slots=True)
class AppConfig:
    game_title: str
    chat_class: str
    input_class: str
    host: str
    port: int
    access_token: str
    poll_interval_seconds: float
    max_message_length: int
    min_send_interval_seconds: float
    input_controls: dict[str, InputControlPreference]
    database_path: Path
    ui_language: str
    external_enabled: bool
    leafos_enabled: bool
    leafos_vault_path: Path | None
    leafos_raw_output_path: Path | None
    leafos_export_ic: bool
    leafos_export_ooc: bool
    leafos_processor_interval_seconds: float
    leafos_session_idle_seconds: float

    def input_preference(self, channel: str) -> InputControlPreference:
        safe_channel = channel if channel in VALID_CHANNELS else "ooc"
        return self.input_controls[safe_channel]


def default_language() -> str:
    code = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    return "pt-BR" if code.startswith("pt") else "en-US"


def _default_input_controls() -> dict[str, dict[str, Any]]:
    return {
        "ooc": {
            "preferred_width": 536,
            "preferred_height": 53,
            "relative_left": None,
            "relative_top": None,
            "candidate_index": None,
            "parent_class": "",
        },
        # The known IC field is candidate 002 in the current sorted scan.
        # Calibration records its complete geometry on first confirmation.
        "ic": {
            "preferred_width": 0,
            "preferred_height": 0,
            "relative_left": None,
            "relative_top": None,
            "candidate_index": 2,
            "parent_class": "",
        },
    }


def default_config(language: str | None = None, port: int = 8765) -> dict[str, Any]:
    safe_port = port if 1024 <= int(port) <= 65535 else 8765
    return {
        "game_title": "shinobi story online",
        "chat_class": "RICHEDIT50W",
        "input_class": "Edit",
        "access_token": secrets.token_urlsafe(32),
        "poll_interval_seconds": 0.75,
        "max_message_length": DEFAULT_MAX_MESSAGE_LENGTH,
        "min_send_interval_seconds": 1.0,
        "database_path": "data/chat_history.db",
        # Kept for backward compatibility with older releases and web clients.
        "input_control": {"preferred_width": 536, "preferred_height": 53},
        "input_controls": _default_input_controls(),
        "server": {"host": "0.0.0.0", "port": safe_port},
        "ui_language": language or default_language(),
        "external_connection": {
            "enabled": True,
            "provider": "cloudflare_quick_tunnel",
        },
        "leafos": {
            "enabled": False,
            "vault_path": "",
            "raw_output_path": "",
            "export_ic": True,
            "export_ooc": False,
            "processor_interval_seconds": 30.0,
            "session_idle_seconds": 900.0,
        },
    }


def _merge_missing(target: dict[str, Any], defaults: dict[str, Any]) -> bool:
    changed = False
    for key, value in defaults.items():
        if key not in target or (target[key] is None and value is not None):
            target[key] = value
            changed = True
        elif isinstance(value, dict) and isinstance(target[key], dict):
            if _merge_missing(target[key], value):
                changed = True
    return changed


def _migrate_message_length(raw: dict[str, Any]) -> bool:
    value = raw.get("max_message_length")
    if value is None:
        return False
    try:
        current = int(value)
    except (TypeError, ValueError):
        current = 0

    if current == LEGACY_MAX_MESSAGE_LENGTH or current <= 0:
        raw["max_message_length"] = DEFAULT_MAX_MESSAGE_LENGTH
        return True
    return False


def _migrate_leafos(raw: dict[str, Any]) -> bool:
    leafos = raw.get("leafos")
    if not isinstance(leafos, dict):
        leafos = {}
        raw["leafos"] = leafos
        changed = True
    else:
        changed = False

    vault = str(leafos.get("vault_path", "") or "").strip()
    raw_path = str(leafos.get("raw_output_path", "") or "").strip()
    if vault and not raw_path:
        leafos["raw_output_path"] = str(Path(vault) / "90 - KageAgent" / "Raw")
        changed = True
    return changed


def _atomic_write(raw: dict[str, Any]) -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(CONFIG_PATH)


def _migrate_input_controls(raw: dict[str, Any]) -> bool:
    changed = False
    defaults = _default_input_controls()
    old = raw.get("input_control")
    controls = raw.get("input_controls")

    if not isinstance(controls, dict):
        controls = {}
        raw["input_controls"] = controls
        changed = True

    if "ooc" not in controls or not isinstance(controls.get("ooc"), dict):
        old_profile = old if isinstance(old, dict) else {}
        controls["ooc"] = {
            **defaults["ooc"],
            "preferred_width": int(old_profile.get("preferred_width", 536)),
            "preferred_height": int(old_profile.get("preferred_height", 53)),
        }
        changed = True

    if "ic" not in controls or not isinstance(controls.get("ic"), dict):
        controls["ic"] = dict(defaults["ic"])
        changed = True

    if _merge_missing(controls["ooc"], defaults["ooc"]):
        changed = True
    if _merge_missing(controls["ic"], defaults["ic"]):
        changed = True

    ooc = controls["ooc"]
    legacy = raw.setdefault("input_control", {})
    if not isinstance(legacy, dict):
        legacy = {}
        raw["input_control"] = legacy
        changed = True

    width = int(ooc.get("preferred_width", 536))
    height = int(ooc.get("preferred_height", 53))
    if legacy.get("preferred_width") != width:
        legacy["preferred_width"] = width
        changed = True
    if legacy.get("preferred_height") != height:
        legacy["preferred_height"] = height
        changed = True

    return changed


def ensure_config(language: str | None = None, port: int | None = None) -> dict[str, Any]:
    defaults = default_config(language=language, port=port or 8765)
    raw: dict[str, Any]

    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            raw = loaded if isinstance(loaded, dict) else {}
        except Exception:
            backup = CONFIG_PATH.with_name("config.invalid.backup.json")
            try:
                CONFIG_PATH.replace(backup)
            except OSError:
                pass
            raw = {}
    else:
        raw = {}

    changed = _migrate_input_controls(raw)
    if _migrate_leafos(raw):
        changed = True
    if _migrate_message_length(raw):
        changed = True
    if _merge_missing(raw, defaults):
        changed = True
    if _migrate_input_controls(raw):
        changed = True
    if _migrate_leafos(raw):
        changed = True

    token = str(raw.get("access_token", "")).strip()
    if len(token) < 16:
        raw["access_token"] = secrets.token_urlsafe(32)
        changed = True

    server = raw.setdefault("server", {})
    try:
        current_port = int(server.get("port", port or 8765))
    except (TypeError, ValueError):
        current_port = port or 8765
    if not 1024 <= current_port <= 65535:
        current_port = 8765
    if server.get("port") != current_port:
        server["port"] = current_port
        changed = True
    if not server.get("host"):
        server["host"] = "0.0.0.0"
        changed = True

    selected_language = str(raw.get("ui_language", language or default_language()))
    if selected_language not in {"pt-BR", "en-US"}:
        selected_language = language or default_language()
        raw["ui_language"] = selected_language
        changed = True

    if changed or not CONFIG_PATH.exists():
        _atomic_write(raw)
    return raw


def _default_database_path() -> Path:
    return PROJECT_DIR / "data" / "chat_history.db"


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_input_preference(raw: dict[str, Any], channel: str) -> InputControlPreference:
    defaults = _default_input_controls()[channel]
    controls = raw.get("input_controls", {})
    profile = controls.get(channel, {}) if isinstance(controls, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    return InputControlPreference(
        preferred_width=int(profile.get("preferred_width", defaults["preferred_width"])),
        preferred_height=int(profile.get("preferred_height", defaults["preferred_height"])),
        relative_left=_optional_int(profile.get("relative_left")),
        relative_top=_optional_int(profile.get("relative_top")),
        candidate_index=_optional_int(profile.get("candidate_index")),
        parent_class=str(profile.get("parent_class", "") or ""),
    )


def load_config() -> AppConfig:
    raw = ensure_config()
    server = raw.get("server", {})
    external = raw.get("external_connection", {})
    leafos = raw.get("leafos", {})
    if not isinstance(leafos, dict):
        leafos = {}

    database_value = raw.get("database_path")
    database_path = (
        (PROJECT_DIR / str(database_value)).resolve()
        if database_value
        else _default_database_path()
    )

    leafos_vault_value = str(leafos.get("vault_path", "") or "").strip()
    leafos_raw_value = str(leafos.get("raw_output_path", "") or "").strip()
    leafos_vault_path = (
        Path(os.path.expandvars(leafos_vault_value)).expanduser()
        if leafos_vault_value
        else None
    )
    leafos_raw_output_path = (
        Path(os.path.expandvars(leafos_raw_value)).expanduser()
        if leafos_raw_value
        else None
    )

    return AppConfig(
        game_title=str(raw.get("game_title", "shinobi story online")).lower(),
        chat_class=str(raw.get("chat_class", "RICHEDIT50W")),
        input_class=str(raw.get("input_class", "Edit")),
        host=str(server.get("host", "0.0.0.0")),
        port=int(server.get("port", 8765)),
        access_token=str(raw.get("access_token", "")),
        poll_interval_seconds=float(raw.get("poll_interval_seconds", 0.75)),
        max_message_length=int(
            raw.get("max_message_length", DEFAULT_MAX_MESSAGE_LENGTH)
        ),
        min_send_interval_seconds=float(raw.get("min_send_interval_seconds", 1.0)),
        input_controls={
            "ooc": _load_input_preference(raw, "ooc"),
            "ic": _load_input_preference(raw, "ic"),
        },
        database_path=database_path,
        ui_language=str(raw.get("ui_language", default_language())),
        external_enabled=bool(external.get("enabled", True)),
        leafos_enabled=bool(leafos.get("enabled", False)),
        leafos_vault_path=leafos_vault_path,
        leafos_raw_output_path=leafos_raw_output_path,
        leafos_export_ic=bool(leafos.get("export_ic", True)),
        leafos_export_ooc=bool(leafos.get("export_ooc", False)),
        leafos_processor_interval_seconds=max(5.0, float(leafos.get("processor_interval_seconds", 30.0))),
        leafos_session_idle_seconds=max(60.0, float(leafos.get("session_idle_seconds", 900.0))),
    )


def update_input_preference(
    channel: str,
    *,
    width: int,
    height: int,
    relative_left: int | None = None,
    relative_top: int | None = None,
    candidate_index: int | None = None,
    parent_class: str = "",
) -> InputControlPreference:
    safe_channel = str(channel).lower()
    if safe_channel not in VALID_CHANNELS:
        raise ValueError("INVALID_CHANNEL")

    raw = ensure_config()
    profile = raw.setdefault("input_controls", {}).setdefault(safe_channel, {})
    profile["preferred_width"] = int(width)
    profile["preferred_height"] = int(height)
    profile["relative_left"] = relative_left
    profile["relative_top"] = relative_top
    profile["candidate_index"] = candidate_index
    profile["parent_class"] = str(parent_class or "")

    if safe_channel == "ooc":
        raw.setdefault("input_control", {})["preferred_width"] = int(width)
        raw["input_control"]["preferred_height"] = int(height)

    _atomic_write(raw)
    return _load_input_preference(raw, safe_channel)


def update_user_settings(
    *,
    language: str,
    port: int,
    regenerate_token: bool = False,
    leafos_enabled: bool | None = None,
    leafos_vault_path: str | None = None,
    leafos_raw_output_path: str | None = None,
    leafos_export_ic: bool | None = None,
    leafos_export_ooc: bool | None = None,
) -> dict[str, Any]:
    raw = ensure_config()
    raw["ui_language"] = language if language in {"pt-BR", "en-US"} else "pt-BR"
    raw.setdefault("server", {})["port"] = int(port) if 1024 <= int(port) <= 65535 else 8765
    if regenerate_token:
        raw["access_token"] = secrets.token_urlsafe(32)

    leafos = raw.setdefault("leafos", {})
    if leafos_enabled is not None:
        leafos["enabled"] = bool(leafos_enabled)
    if leafos_vault_path is not None:
        leafos["vault_path"] = str(leafos_vault_path).strip()
    if leafos_raw_output_path is not None:
        leafos["raw_output_path"] = str(leafos_raw_output_path).strip()
    if leafos_export_ic is not None:
        leafos["export_ic"] = bool(leafos_export_ic)
    if leafos_export_ooc is not None:
        leafos["export_ooc"] = bool(leafos_export_ooc)

    if str(leafos.get("vault_path", "") or "").strip() and not str(
        leafos.get("raw_output_path", "") or ""
    ).strip():
        leafos["raw_output_path"] = str(
            Path(str(leafos["vault_path"])) / "90 - KageAgent" / "Raw"
        )

    _atomic_write(raw)
    return raw

def update_server_port(port: int) -> dict[str, Any]:
    raw = ensure_config()
    safe_port = int(port)
    if not 1024 <= safe_port <= 65535:
        raise ValueError("Server port must be between 1024 and 65535.")
    raw.setdefault("server", {})["port"] = safe_port
    _atomic_write(raw)
    return raw
