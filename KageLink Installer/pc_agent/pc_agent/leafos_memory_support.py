from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEWER_SCHEMA_VERSION = 1
CANONICAL_MEMORY_SCHEMA_VERSION = 1
INTERPRETER_CATEGORIES = (
    "events",
    "characters",
    "locations",
    "relationships",
    "facts",
    "leafos_memories",
)
CANONICAL_CATEGORY_MAP = {
    "events": "events",
    "characters": "characters",
    "locations": "locations",
    "relationships": "relationships",
    "facts": "lore",
    "leafos_memories": "memories",
}
MEMORY_PERSPECTIVES = {"observed", "said", "inferred"}
IMMUTABLE_EDIT_FIELDS = {"source_message_ids", "confidence", "review_status"}
_RAW_BEGIN = re.compile(r"<!--\s*kagelink-raw-begin\s+(?P<meta>\{.*?\})\s*-->")


class ReviewerError(RuntimeError):
    """Base error for controlled Reviewer failures."""


class EvidenceError(ReviewerError):
    """Raised when candidate evidence cannot be traced to Processor + RAW."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: Any) -> str:
    text = str(value or "").strip()
    safe = "".join(ch if ch.isalnum() or ch in "-_ ." else "_" for ch in text)
    return safe[:160] or "unknown"


def _read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewerError(f"INVALID_JSON: {path}") from error
    if not isinstance(value, dict):
        raise ReviewerError(f"JSON_ROOT_MUST_BE_OBJECT: {path}")

    # Existing persisted Reviewer/Canonical state is fail-closed. When callers
    # provide a schema-shaped default, a present container field must keep the
    # same container type. Treating {"entries":"oops"} as an empty list (or a
    # malformed reviews field as {}) could silently erase durable decisions.
    for key, expected in (default or {}).items():
        if key not in value:
            continue
        actual = value[key]
        if isinstance(expected, dict) and not isinstance(actual, dict):
            raise ReviewerError(f"INVALID_JSON_FIELD_TYPE: {path}: {key}")
        if isinstance(expected, list) and not isinstance(actual, list):
            raise ReviewerError(f"INVALID_JSON_FIELD_TYPE: {path}: {key}")

    return value


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    temp.replace(path)


def _relative_or_absolute(path: Path, vault: Path) -> str:
    try:
        return str(path.resolve().relative_to(vault.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        return str(path.resolve()).replace("\\", "/")


def _candidate_digest(session_id: str, category: str, index: int, candidate: dict[str, Any]) -> str:
    encoded = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    raw = f"{session_id}|{category}|{index}|{encoded}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _raw_records(path: Path) -> dict[int, dict[str, Any]]:
    content = path.read_text(encoding="utf-8-sig")
    result: dict[int, dict[str, Any]] = {}
    cursor = 0
    while True:
        match = _RAW_BEGIN.search(content, cursor)
        if match is None:
            break
        text_start = match.end()
        if content.startswith("\r\n", text_start):
            text_start += 2
        elif content.startswith("\n", text_start):
            text_start += 1
        end_marker = "\n<!-- kagelink-raw-end -->"
        end_at = content.find(end_marker, text_start)
        if end_at < 0:
            break
        try:
            metadata = json.loads(match.group("meta"))
            message_id = int(metadata.get("id"))
        except (json.JSONDecodeError, TypeError, ValueError):
            cursor = match.end()
            continue
        record = dict(metadata)
        record["id"] = message_id
        record["text"] = content[text_start:end_at]
        result[message_id] = record
        cursor = end_at + len(end_marker)
    return result


def _display_candidate(candidate: dict[str, Any]) -> str:
    for key in ("title", "statement", "memory", "observation", "description", "name"):
        value = str(candidate.get(key, "") or "").strip()
        if value:
            return value
    return "Candidate"


def render_memory_markdown(path: Path, payload: dict[str, Any]) -> None:
    groups = {name: [] for name in ("events", "characters", "locations", "relationships", "lore", "memories")}
    for entry in payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category", ""))
        if category in groups:
            groups[category].append(entry)

    lines = [
        "# LeafOS Canonical Memory",
        "",
        "> **DERIVED VIEW.** The canonical source is `memory.json`. This Markdown file is regenerated from it and must not be edited as a second source of truth.",
        "",
        f"Updated: `{payload.get('updated_at', '')}`",
        "",
    ]
    labels = {
        "events": "Events",
        "characters": "Characters",
        "locations": "Locations",
        "relationships": "Relationships",
        "lore": "Lore",
        "memories": "Memories",
    }
    for category, label in labels.items():
        lines.extend([f"## {label}", ""])
        entries = groups[category]
        if not entries:
            lines.extend(["_No approved entries._", ""])
            continue
        for entry in entries:
            content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
            title = _display_candidate(content)
            lines.append(f"### {title}")
            lines.append("")
            lines.append(f"- Memory ID: `{entry.get('memory_id', '')}`")
            lines.append(f"- Session: `{entry.get('session_id', '')}`")
            primary = str(entry.get("primary_character", "") or "")
            if primary:
                lines.append(f"- Primary character: **{primary}**")
            epistemic = entry.get("epistemic") if isinstance(entry.get("epistemic"), dict) else {}
            lines.append(f"- Epistemic type: `{epistemic.get('type', 'reviewed_world')}`")
            if epistemic.get("perspective"):
                lines.append(f"- Perspective: `{epistemic.get('perspective')}`")
            if epistemic.get("speaker"):
                lines.append(f"- Speaker: **{epistemic.get('speaker')}**")
            if epistemic.get("known_by"):
                lines.append(f"- Known by: **{epistemic.get('known_by')}**")
            source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
            lines.append(f"- Source message IDs: `{source.get('source_message_ids', [])}`")
            lines.append(f"- Review status: `{entry.get('review_status', '')}`")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(content, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")
    _atomic_text(path, "\n".join(lines).rstrip() + "\n")


def validate_edit(original: dict[str, Any], edited: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(edited, dict):
        raise ReviewerError("EDITED_CANDIDATE_MUST_BE_OBJECT")
    approved = deepcopy(edited)
    for field in IMMUTABLE_EDIT_FIELDS:
        if field in original:
            if field in approved and approved[field] != original[field]:
                raise ReviewerError(f"IMMUTABLE_FIELD_CHANGED: {field}")
            approved[field] = deepcopy(original[field])
    if "perspective" in approved:
        perspective = str(approved.get("perspective", "") or "")
        if perspective and perspective not in MEMORY_PERSPECTIVES:
            raise ReviewerError("INVALID_PERSPECTIVE")
    return approved


def epistemic_metadata(record: dict[str, Any], approved: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    category = record["category"]
    primary_character = record.get("primary_character") or ""
    unique_speakers = sorted({str(item.get("speaker")) for item in evidence if item.get("speaker")})
    speaker = unique_speakers[0] if len(unique_speakers) == 1 else None

    if category == "leafos_memories":
        perspective = str(approved.get("perspective", "") or "")
        if perspective not in MEMORY_PERSPECTIVES:
            raise ReviewerError("MEMORY_REQUIRES_VALID_PERSPECTIVE")
        if not primary_character:
            raise ReviewerError("MEMORY_REQUIRES_PRIMARY_CHARACTER")
        return {
            "type": "character_memory",
            "perspective": perspective,
            "known_by": primary_character,
            "speaker": speaker if perspective == "said" else None,
        }

    if category == "facts":
        kind = str(approved.get("kind", "") or "").strip().lower()
        if "infer" in kind:
            return {
                "type": "inference",
                "perspective": "inferred",
                "known_by": primary_character or None,
                "speaker": None,
            }
        if kind in {"statement", "claim", "said", "report", "reported"}:
            return {
                "type": "claim",
                "perspective": "said",
                "known_by": primary_character or None,
                "speaker": speaker,
            }

    return {
        "type": "reviewed_world",
        "perspective": None,
        "known_by": None,
        "speaker": speaker,
    }
