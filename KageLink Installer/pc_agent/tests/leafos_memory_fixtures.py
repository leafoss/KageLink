from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_raw(vault: Path, messages: list[dict]) -> Path:
    path = vault / "RAW" / "IC" / "2026-07-24.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = []
    for item in messages:
        meta = {
            "id": item["id"],
            "timestamp": item["timestamp"],
            "channel": "ic",
            "speaker": item.get("speaker"),
        }
        chunks.append(
            "<!-- kagelink-raw-begin "
            + json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
            + " -->\n"
            + item["text"]
            + "\n<!-- kagelink-raw-end -->\n\n"
        )
    path.write_text("".join(chunks), encoding="utf-8")
    return path


def write_session_and_bundle(
    vault: Path,
    *,
    session_id: str = "2026-07-24_001",
    primary_character: str = "Matsunaya, Raika",
    candidate_overrides: dict | None = None,
) -> tuple[Path, Path, Path]:
    messages = [
        {
            "id": 101,
            "timestamp": "2026-07-24T20:00:00+00:00",
            "speaker": "Uzumaki, Urahara",
            "text": "Uzumaki, Urahara Says: The Mizukage is heading east.",
        },
        {
            "id": 102,
            "timestamp": "2026-07-24T20:01:00+00:00",
            "speaker": primary_character or None,
            "text": f"{primary_character} Says: Understood." if primary_character else "(*Someone nods.*)",
        },
        {
            "id": 103,
            "timestamp": "2026-07-24T20:02:00+00:00",
            "speaker": None,
            "text": "(*A shadow crosses the eastern road.*)",
        },
    ]
    raw_path = write_raw(vault, messages)
    raw_ref = str(raw_path.relative_to(vault)).replace("\\", "/")
    session = {
        "session_id": session_id,
        "started_at": messages[0]["timestamp"],
        "ended_at": messages[-1]["timestamp"],
        "participants": [name for name in ["Uzumaki, Urahara", primary_character] if name],
        "message_count": len(messages),
        "message_ids": [item["id"] for item in messages],
        "raw_sources": [raw_ref],
        "messages": [
            {
                "id": item["id"],
                "timestamp": item["timestamp"],
                "channel": "ic",
                "speaker": item.get("speaker"),
                "text": item["text"],
                "raw_source": raw_ref,
            }
            for item in messages
        ],
    }
    session_path = vault / "80 - Processor" / "Sessions" / f"{session_id}.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    bundle = {
        "type": "interpretation_bundle",
        "schema_version": 1,
        "prompt_version": "leafos-interpreter-v2",
        "session_id": session_id,
        "started_at": session["started_at"],
        "ended_at": session["ended_at"],
        "primary_character": primary_character,
        "participants": session["participants"],
        "message_ids": session["message_ids"],
        "raw_sources": session["raw_sources"],
        "summary": "Urahara reports movement east and the primary character acknowledges it.",
        "status": "pending_review",
        "events": [
            {
                "title": "Report about eastern movement",
                "description": "Urahara reports that the Mizukage is heading east.",
                "event_type": "report",
                "confidence": 0.93,
                "source_message_ids": [101],
                "review_status": "pending_review",
            }
        ],
        "characters": [
            {
                "name": "Uzumaki, Urahara",
                "observation": "Urahara reports enemy movement.",
                "confidence": 0.88,
                "source_message_ids": [101],
                "review_status": "pending_review",
            }
        ],
        "locations": [],
        "relationships": [],
        "facts": [
            {
                "statement": "Urahara said that the Mizukage is heading east.",
                "kind": "statement",
                "confidence": 0.98,
                "source_message_ids": [101],
                "review_status": "pending_review",
            }
        ],
        "leafos_memories": [
            {
                "memory": "Urahara reported that the Mizukage was heading east.",
                "perspective": "said",
                "confidence": 0.95,
                "source_message_ids": [101],
                "review_status": "pending_review",
            },
            {
                "memory": "A shadow crossed the eastern road.",
                "perspective": "observed",
                "confidence": 0.82,
                "source_message_ids": [103],
                "review_status": "pending_review",
            },
            {
                "memory": "The eastern road may be dangerous.",
                "perspective": "inferred",
                "confidence": 0.61,
                "source_message_ids": [101, 103],
                "review_status": "pending_review",
            },
        ],
    }
    if candidate_overrides:
        bundle.update(candidate_overrides)
    bundle_path = vault / "70 - LeafOS Inbox" / "Interpretations" / f"{session_id}.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw_path, session_path, bundle_path
