from __future__ import annotations

import argparse
import hashlib
import json
import logging
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from pc_agent.config import load_config
from pc_agent.history import HistoryStore
from pc_agent.primary_character import resolve_primary_character


PROMPT_VERSION = "leafos-interpreter-v3"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:14b"
DEFAULT_CHUNK_CHARS = 9000
DEFAULT_MAX_TRANSCRIPT_CHARS = DEFAULT_CHUNK_CHARS
DEFAULT_CHUNK_OVERLAP_MESSAGES = 2
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 600.0
CHECKPOINT_SCHEMA_VERSION = 1

INTERPRETATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "event_type": {"type": "string"},
                    "confidence": {"type": "number"},
                    "source_message_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["title", "description", "event_type", "confidence", "source_message_ids"],
            },
        },
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "observation": {"type": "string"},
                    "confidence": {"type": "number"},
                    "source_message_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["name", "observation", "confidence", "source_message_ids"],
            },
        },
        "locations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "observation": {"type": "string"},
                    "confidence": {"type": "number"},
                    "source_message_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["name", "observation", "confidence", "source_message_ids"],
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "observation": {"type": "string"},
                    "confidence": {"type": "number"},
                    "source_message_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["source", "target", "observation", "confidence", "source_message_ids"],
            },
        },
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "kind": {"type": "string"},
                    "confidence": {"type": "number"},
                    "source_message_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["statement", "kind", "confidence", "source_message_ids"],
            },
        },
        "leafos_memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "memory": {"type": "string"},
                    "perspective": {"type": "string", "enum": ["observed", "said", "inferred"]},
                    "confidence": {"type": "number"},
                    "source_message_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["memory", "perspective", "confidence", "source_message_ids"],
            },
        },
    },
    "required": ["summary", "events", "characters", "locations", "relationships", "facts", "leafos_memories"],
}

SYSTEM_PROMPT = """You are the LeafOS Interpreter for a persistent roleplay memory system.
Interpret ONLY the supplied session transcript chunk. Never use outside Naruto knowledge, prior knowledge, assumptions about characters, or information not present in the supplied messages.
A long session may be divided into multiple chunks. Treat this request as self-contained: never infer what happened in omitted chunks and never invent continuity across chunk boundaries.
PRIMARY_CHARACTER, when non-empty, is the user's configured roleplay character for this session. Never assume the user's character is Leafos or any other fixed identity.
The legacy JSON field leafos_memories means candidate subjective memories belonging to PRIMARY_CHARACTER. If PRIMARY_CHARACTER is empty, leave leafos_memories empty rather than guessing an owner.
Your output is NOT canonical memory. It is a set of review candidates.
Every candidate must cite one or more source_message_ids from the supplied transcript chunk.
If the supplied chunk does not support something, omit it.
Distinguish direct observations/statements from inference. Prefer omission over speculation.
Do not invent locations, relationships, motives, ranks, identities, factions, outcomes, or chronology.
Return only data matching the supplied JSON schema.
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return dict(default or {})
    return value if isinstance(value, dict) else dict(default or {})


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _safe_session_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value.strip())
    return safe[:120] or "unknown_session"


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _clean_text(value: Any, limit: int = 8000) -> str:
    return str(value or "").strip()[:limit]


def _clean_source_ids(value: Any, allowed_ids: set[int]) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        try:
            message_id = int(item)
        except (TypeError, ValueError):
            continue
        if message_id in allowed_ids and message_id not in result:
            result.append(message_id)
    return result


def _session_messages(session: dict[str, Any]) -> list[dict[str, Any]]:
    raw_messages = session.get("messages", [])
    if not isinstance(raw_messages, list):
        return []
    return [dict(item) for item in raw_messages if isinstance(item, dict)]


def _render_message(item: dict[str, Any]) -> str:
    return (
        f'[{item.get("id")}] timestamp={item.get("timestamp", "")} '
        f'speaker={item.get("speaker") or "UNKNOWN"}\n{item.get("text", "")}'
    )


def _select_messages(session: dict[str, Any], max_chars: int) -> tuple[list[dict[str, Any]], bool]:
    """Legacy head/tail selector retained for source compatibility.

    Interpreter v3 no longer uses this lossy selector for normal processing; it
    uses `_chunk_messages` so every session message reaches the model.
    """

    messages = _session_messages(session)
    rendered = [f'[{item.get("id")}] {item.get("speaker") or "UNKNOWN"}: {item.get("text", "")}' for item in messages]
    if sum(len(line) + 1 for line in rendered) <= max_chars:
        return messages, False

    head_budget = int(max_chars * 0.65)
    tail_budget = max_chars - head_budget
    head: list[dict[str, Any]] = []
    tail: list[dict[str, Any]] = []
    used = 0
    for item, line in zip(messages, rendered):
        if used + len(line) + 1 > head_budget:
            break
        head.append(item)
        used += len(line) + 1

    used = 0
    for item, line in reversed(list(zip(messages, rendered))):
        if used + len(line) + 1 > tail_budget:
            break
        tail.append(item)
        used += len(line) + 1
    tail.reverse()

    selected: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in head + tail:
        try:
            message_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if message_id in seen:
            continue
        seen.add(message_id)
        selected.append(item)
    return selected, True


def _chunk_messages(
    session: dict[str, Any],
    max_chars: int,
    overlap_messages: int = DEFAULT_CHUNK_OVERLAP_MESSAGES,
) -> list[list[dict[str, Any]]]:
    """Split a session into ordered prompt-sized chunks without dropping messages."""

    messages = _session_messages(session)
    if not messages:
        return []

    safe_budget = max(4000, int(max_chars))
    safe_overlap = max(0, int(overlap_messages))
    chunks: list[list[dict[str, Any]]] = []
    start = 0

    while start < len(messages):
        used = 0
        end = start
        while end < len(messages):
            cost = len(_render_message(messages[end])) + 2
            if end > start and used + cost > safe_budget:
                break
            used += cost
            end += 1
            if used >= safe_budget:
                break

        if end <= start:
            end = start + 1

        chunks.append(messages[start:end])
        if end >= len(messages):
            break

        start = max(start + 1, end - safe_overlap)

    return chunks


def _message_ids(messages: Iterable[dict[str, Any]]) -> list[int]:
    result: list[int] = []
    for item in messages:
        try:
            message_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if message_id not in result:
            result.append(message_id)
    return result


def _session_fingerprint(
    session: dict[str, Any],
    *,
    chunk_chars: int,
    overlap_messages: int,
) -> str:
    """Fingerprint semantic input so stale partial checkpoints are never reused."""

    payload = {
        "prompt_version": PROMPT_VERSION,
        "session_id": str(session.get("session_id", "")),
        "started_at": session.get("started_at"),
        "ended_at": session.get("ended_at"),
        "primary_character": str(session.get("primary_character", "") or ""),
        "chunk_chars": int(chunk_chars),
        "overlap_messages": int(overlap_messages),
        "messages": [
            {
                "id": item.get("id"),
                "timestamp": item.get("timestamp"),
                "channel": item.get("channel"),
                "speaker": item.get("speaker"),
                "text": item.get("text"),
                "raw_source": item.get("raw_source"),
            }
            for item in _session_messages(session)
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _build_user_prompt(session: dict[str, Any], messages: list[dict[str, Any]], truncated: bool) -> str:
    transcript_lines = [_render_message(item) for item in messages]
    participants = session.get("participants", [])
    if not isinstance(participants, list):
        participants = []

    chunk_index = max(1, int(session.get("_interpreter_chunk_index", 1) or 1))
    chunk_count = max(1, int(session.get("_interpreter_chunk_count", 1) or 1))
    chunk_ids = _message_ids(messages)
    return (
        f'SESSION_ID: {session.get("session_id", "")}\n'
        f'STARTED_AT: {session.get("started_at", "")}\n'
        f'ENDED_AT: {session.get("ended_at", "")}\n'
        f'PRIMARY_CHARACTER: {session.get("primary_character", "")}\n'
        f'PARTICIPANTS_DETECTED: {json.dumps(participants, ensure_ascii=False)}\n'
        f'SESSION_CHUNK: {chunk_index}/{chunk_count}\n'
        f'SESSION_CHUNKED: {str(chunk_count > 1).lower()}\n'
        f'CHUNK_MESSAGE_IDS: {json.dumps(chunk_ids)}\n'
        f'TRANSCRIPT_TRUNCATED: {str(truncated).lower()}\n\n'
        'TRANSCRIPT_CHUNK:\n' + "\n\n".join(transcript_lines)
    )


class OllamaInterpreterProvider:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model.strip() or DEFAULT_MODEL
        self.timeout_seconds = max(5.0, float(timeout_seconds))

    def interpret(self, session: dict[str, Any], messages: list[dict[str, Any]], truncated: bool) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": INTERPRETATION_SCHEMA,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(session, messages, truncated)},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detail = error.read().decode("utf-8", errors="replace").strip()
            except Exception:
                detail = ""
            suffix = detail[-1200:] if detail else str(error.reason or error)
            raise RuntimeError(f"OLLAMA_HTTP_{error.code}: {suffix}") from error
        except TimeoutError as error:
            raise RuntimeError(f"OLLAMA_TIMEOUT: {self.timeout_seconds:.0f}s") from error
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            if isinstance(reason, TimeoutError):
                raise RuntimeError(f"OLLAMA_TIMEOUT: {self.timeout_seconds:.0f}s") from error
            raise RuntimeError(f"OLLAMA_UNAVAILABLE: {reason}") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("OLLAMA_INVALID_RESPONSE") from error

        message = response_payload.get("message") if isinstance(response_payload, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OLLAMA_EMPTY_RESPONSE")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as error:
            raise RuntimeError("OLLAMA_INVALID_JSON") from error
        if not isinstance(result, dict):
            raise RuntimeError("OLLAMA_INVALID_INTERPRETATION")
        return result


ProgressCallback = Callable[[dict[str, Any]], None]


class LeafOSInterpreter:
    """Turns closed Processor sessions into non-canonical review candidates."""

    CATEGORIES = ("events", "characters", "locations", "relationships", "facts", "leafos_memories")

    def __init__(
        self,
        vault_path: Path,
        provider: Any,
        *,
        max_transcript_chars: int = DEFAULT_MAX_TRANSCRIPT_CHARS,
        chunk_overlap_messages: int = DEFAULT_CHUNK_OVERLAP_MESSAGES,
        logger: logging.Logger | None = None,
        primary_character_resolver: Any | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.vault_path = Path(vault_path)
        self.provider = provider
        self.max_transcript_chars = max(4000, int(max_transcript_chars))
        self.chunk_overlap_messages = max(0, int(chunk_overlap_messages))
        self.logger = logger or logging.getLogger("kagelink.leafos.interpreter")
        self.primary_character_resolver = primary_character_resolver
        self.progress_callback = progress_callback

    @property
    def sessions_dir(self) -> Path:
        return self.vault_path / "80 - Processor" / "Sessions"

    @property
    def state_path(self) -> Path:
        return self.vault_path / "80 - Interpreter" / "interpreter_state.json"

    @property
    def checkpoints_dir(self) -> Path:
        return self.vault_path / "80 - Interpreter" / "Checkpoints"

    @property
    def inbox_dir(self) -> Path:
        return self.vault_path / "70 - LeafOS Inbox" / "Interpretations"

    def _emit_progress(self, event: str, **payload: Any) -> None:
        callback = self.progress_callback
        if callback is None:
            return
        try:
            callback({"event": event, **payload})
        except Exception:
            self.logger.exception("[LeafOS Interpreter] Progress callback failed")

    def _normalize_result(
        self,
        session: dict[str, Any],
        raw: dict[str, Any],
        allowed_ids: set[int],
        *,
        truncated: bool,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": "interpretation_bundle",
            "schema_version": 1,
            "prompt_version": PROMPT_VERSION,
            "session_id": str(session.get("session_id", "")),
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "primary_character": str(session.get("primary_character", "") or ""),
            "participants": session.get("participants", []),
            "message_ids": session.get("message_ids", []),
            "raw_sources": session.get("raw_sources", []),
            "transcript_truncated": truncated,
            "summary": _clean_text(raw.get("summary"), 6000),
            "status": "pending_review",
            "created_at": _utc_now(),
            "provider": "ollama",
            "model": getattr(self.provider, "model", "unknown"),
        }

        for category in self.CATEGORIES:
            cleaned: list[dict[str, Any]] = []
            values = raw.get(category, [])
            if not isinstance(values, list):
                values = []
            for candidate in values:
                if not isinstance(candidate, dict):
                    continue
                source_ids = _clean_source_ids(candidate.get("source_message_ids"), allowed_ids)
                if not source_ids:
                    continue
                item = {key: value for key, value in candidate.items() if key not in {"source_message_ids", "confidence"}}
                for key, value in list(item.items()):
                    if isinstance(value, str):
                        item[key] = _clean_text(value)
                item["confidence"] = _clamp_confidence(candidate.get("confidence"))
                item["source_message_ids"] = source_ids
                item["review_status"] = "pending_review"
                cleaned.append(item)
            result[category] = cleaned
        return result

    def _partial_result(
        self,
        session: dict[str, Any],
        raw: dict[str, Any],
        allowed_ids: set[int],
    ) -> dict[str, Any]:
        normalized = self._normalize_result(session, raw, allowed_ids, truncated=False)
        partial: dict[str, Any] = {"summary": normalized.get("summary", "")}
        for category in self.CATEGORIES:
            partial[category] = normalized.get(category, [])
        return partial

    @staticmethod
    def _candidate_key(candidate: dict[str, Any]) -> str:
        semantic: dict[str, Any] = {}
        for key, value in candidate.items():
            if key in {"confidence", "source_message_ids", "review_status"}:
                continue
            if isinstance(value, str):
                semantic[key] = " ".join(value.split()).casefold()
            else:
                semantic[key] = value
        return json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    def _merge_chunk_results(
        self,
        session: dict[str, Any],
        chunk_results: list[dict[str, Any]],
        *,
        chunk_count: int,
    ) -> dict[str, Any]:
        summaries: list[str] = []
        for partial in chunk_results:
            summary = _clean_text(partial.get("summary"), 6000)
            if summary and summary not in summaries:
                summaries.append(summary)

        result: dict[str, Any] = {
            "type": "interpretation_bundle",
            "schema_version": 1,
            "prompt_version": PROMPT_VERSION,
            "session_id": str(session.get("session_id", "")),
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "primary_character": str(session.get("primary_character", "") or ""),
            "participants": session.get("participants", []),
            "message_ids": session.get("message_ids", []),
            "raw_sources": session.get("raw_sources", []),
            "transcript_truncated": False,
            "interpretation_mode": "chunked" if chunk_count > 1 else "single",
            "chunk_count": chunk_count,
            "chunk_chars": self.max_transcript_chars,
            "chunk_overlap_messages": self.chunk_overlap_messages,
            "summary": _clean_text("\n\n".join(summaries), 12000),
            "status": "pending_review",
            "created_at": _utc_now(),
            "provider": "ollama",
            "model": getattr(self.provider, "model", "unknown"),
        }

        allowed_session_ids = set(_message_ids(_session_messages(session)))
        for category in self.CATEGORIES:
            merged: dict[str, dict[str, Any]] = {}
            order: list[str] = []
            for partial in chunk_results:
                values = partial.get(category, [])
                if not isinstance(values, list):
                    continue
                for candidate in values:
                    if not isinstance(candidate, dict):
                        continue
                    key = self._candidate_key(candidate)
                    if key not in merged:
                        merged[key] = deepcopy(candidate)
                        order.append(key)
                        continue

                    existing = merged[key]
                    existing_ids = _clean_source_ids(existing.get("source_message_ids"), allowed_session_ids)
                    incoming_ids = _clean_source_ids(candidate.get("source_message_ids"), allowed_session_ids)
                    existing["source_message_ids"] = sorted(set(existing_ids + incoming_ids))
                    existing["confidence"] = max(
                        _clamp_confidence(existing.get("confidence")),
                        _clamp_confidence(candidate.get("confidence")),
                    )
            result[category] = [merged[key] for key in order]
        return result

    def _checkpoint_path(self, session_id: str) -> Path:
        return self.checkpoints_dir / f"{_safe_session_id(session_id)}.json"

    def _load_checkpoint(
        self,
        *,
        session_id: str,
        chunks: list[list[dict[str, Any]]],
        fingerprint: str,
    ) -> dict[str, Any]:
        path = self._checkpoint_path(session_id)
        existing = _read_json(path)
        try:
            valid = (
                existing.get("type") == "leafos_interpreter_checkpoint"
                and int(existing.get("schema_version", 0) or 0) == CHECKPOINT_SCHEMA_VERSION
                and existing.get("prompt_version") == PROMPT_VERSION
                and existing.get("session_id") == session_id
                and existing.get("session_fingerprint") == fingerprint
                and int(existing.get("chunk_chars", 0) or 0) == self.max_transcript_chars
                and int(existing.get("chunk_overlap_messages", -1) or -1) == self.chunk_overlap_messages
                and int(existing.get("total_chunks", 0) or 0) == len(chunks)
                and isinstance(existing.get("chunks"), dict)
            )
        except (TypeError, ValueError):
            valid = False
        if valid:
            return existing

        if existing:
            self.logger.warning("[LeafOS Interpreter] Resetting stale checkpoint for session %s", session_id)

        return {
            "type": "leafos_interpreter_checkpoint",
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "prompt_version": PROMPT_VERSION,
            "session_id": session_id,
            "session_fingerprint": fingerprint,
            "chunk_chars": self.max_transcript_chars,
            "chunk_overlap_messages": self.chunk_overlap_messages,
            "total_chunks": len(chunks),
            "chunks": {},
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "last_error": "",
            "failed_chunk": None,
        }

    def _save_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        checkpoint["updated_at"] = _utc_now()
        _atomic_json(self._checkpoint_path(str(checkpoint.get("session_id", ""))), checkpoint)

    def _session_files(self) -> list[Path]:
        if not self.sessions_dir.exists():
            return []
        return sorted(self.sessions_dir.glob("*.json"))

    @staticmethod
    def _target_set(session_ids: Iterable[str] | None) -> set[str] | None:
        if session_ids is None:
            return None
        return {str(value).strip() for value in session_ids if str(value).strip()}

    @staticmethod
    def _failure_record(
        failed_state: dict[str, Any],
        session_id: str,
        error_text: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous = failed_state.get(session_id)
        attempts = 0
        if isinstance(previous, dict):
            try:
                attempts = max(0, int(previous.get("attempts", 0) or 0))
            except (TypeError, ValueError):
                attempts = 0
        record: dict[str, Any] = {
            "error": str(error_text),
            "attempts": attempts + 1,
            "last_failed_at": _utc_now(),
        }
        if details:
            record.update(details)
        failed_state[session_id] = record
        return record

    def run_once(
        self,
        *,
        max_sessions: int | None = None,
        session_ids: Iterable[str] | None = None,
        include_details: bool = False,
    ) -> dict[str, Any]:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        state = _read_json(
            self.state_path,
            {
                "schema_version": 1,
                "processed_sessions": [],
                "failed_sessions": {},
                "last_run": "",
                "last_error": "",
            },
        )
        processed = {str(value) for value in state.get("processed_sessions", []) if str(value)}
        failed_state_raw = state.get("failed_sessions", {})
        failed_state = dict(failed_state_raw) if isinstance(failed_state_raw, dict) else {}
        targets = self._target_set(session_ids)
        found_targets: set[str] = set()

        interpreted = 0
        skipped = 0
        failed = 0
        interpreted_sessions: list[str] = []
        skipped_sessions: list[str] = []
        failures: list[dict[str, Any]] = []

        for path in self._session_files():
            session = _read_json(path)
            session_id = str(session.get("session_id") or path.stem)
            if targets is not None and session_id not in targets:
                continue
            if targets is not None:
                found_targets.add(session_id)

            if session_id in processed:
                failed_state.pop(session_id, None)
                skipped += 1
                skipped_sessions.append(session_id)
                continue

            output_path = self.inbox_dir / f"{_safe_session_id(session_id)}.json"
            if output_path.exists():
                processed.add(session_id)
                failed_state.pop(session_id, None)
                skipped += 1
                skipped_sessions.append(session_id)
                continue

            if not str(session.get("primary_character", "") or "").strip() and self.primary_character_resolver is not None:
                try:
                    resolved = self.primary_character_resolver(session)
                    session["primary_character"] = str(resolved or "").strip()
                except Exception:
                    self.logger.exception(
                        "[LeafOS Interpreter ERROR] Could not resolve primary character for session %s",
                        session_id,
                    )
                    session["primary_character"] = ""

            all_messages = _session_messages(session)
            if not set(_message_ids(all_messages)):
                error_text = f"SESSION_WITHOUT_MESSAGES: {session_id}"
                failed += 1
                self._failure_record(failed_state, session_id, error_text)
                failures.append({"session_id": session_id, "error": error_text})
                continue

            chunks = _chunk_messages(session, self.max_transcript_chars, self.chunk_overlap_messages)
            fingerprint = _session_fingerprint(
                session,
                chunk_chars=self.max_transcript_chars,
                overlap_messages=self.chunk_overlap_messages,
            )
            checkpoint = self._load_checkpoint(
                session_id=session_id,
                chunks=chunks,
                fingerprint=fingerprint,
            )
            completed_raw = checkpoint.get("chunks", {})
            completed = dict(completed_raw) if isinstance(completed_raw, dict) else {}
            chunk_results: list[dict[str, Any]] = []
            session_failed = False

            self._emit_progress(
                "session_start",
                session_id=session_id,
                total_chunks=len(chunks),
                completed_chunks=sum(
                    1
                    for item in completed.values()
                    if isinstance(item, dict) and item.get("status") == "complete"
                ),
            )

            for index, messages in enumerate(chunks):
                chunk_number = index + 1
                key = str(index)
                expected_ids = _message_ids(messages)
                cached = completed.get(key)
                if (
                    isinstance(cached, dict)
                    and cached.get("status") == "complete"
                    and cached.get("message_ids") == expected_ids
                    and isinstance(cached.get("result"), dict)
                ):
                    chunk_results.append(dict(cached["result"]))
                    self._emit_progress(
                        "chunk_reused",
                        session_id=session_id,
                        chunk_number=chunk_number,
                        total_chunks=len(chunks),
                    )
                    continue

                chunk_session = dict(session)
                chunk_session["_interpreter_chunk_index"] = chunk_number
                chunk_session["_interpreter_chunk_count"] = len(chunks)
                allowed_ids = set(expected_ids)
                self._emit_progress(
                    "chunk_start",
                    session_id=session_id,
                    chunk_number=chunk_number,
                    total_chunks=len(chunks),
                )

                try:
                    raw_result = self.provider.interpret(chunk_session, messages, False)
                    partial = self._partial_result(session, raw_result, allowed_ids)
                    completed[key] = {
                        "status": "complete",
                        "chunk_index": index,
                        "chunk_number": chunk_number,
                        "message_ids": expected_ids,
                        "result": partial,
                        "completed_at": _utc_now(),
                    }
                    checkpoint["chunks"] = completed
                    checkpoint["last_error"] = ""
                    checkpoint["failed_chunk"] = None
                    self._save_checkpoint(checkpoint)
                    chunk_results.append(partial)
                    self._emit_progress(
                        "chunk_complete",
                        session_id=session_id,
                        chunk_number=chunk_number,
                        total_chunks=len(chunks),
                    )
                except Exception as error:
                    error_text = str(error) or error.__class__.__name__
                    checkpoint["chunks"] = completed
                    checkpoint["last_error"] = error_text
                    checkpoint["failed_chunk"] = chunk_number
                    self._save_checkpoint(checkpoint)
                    completed_count = sum(
                        1
                        for item in completed.values()
                        if isinstance(item, dict) and item.get("status") == "complete"
                    )
                    details = {
                        "chunk_number": chunk_number,
                        "total_chunks": len(chunks),
                        "completed_chunks": completed_count,
                    }
                    failed += 1
                    self._failure_record(failed_state, session_id, error_text, details=details)
                    failures.append({"session_id": session_id, "error": error_text, **details})
                    self._emit_progress(
                        "chunk_failed",
                        session_id=session_id,
                        chunk_number=chunk_number,
                        total_chunks=len(chunks),
                        error=error_text,
                    )
                    self.logger.exception(
                        "[LeafOS Interpreter ERROR] Session %s chunk %s/%s failed",
                        session_id,
                        chunk_number,
                        len(chunks),
                    )
                    session_failed = True
                    break

            if session_failed:
                continue

            try:
                bundle = self._merge_chunk_results(session, chunk_results, chunk_count=len(chunks))
                _atomic_json(output_path, bundle)
            except Exception as error:
                error_text = str(error) or error.__class__.__name__
                failed += 1
                details = {
                    "chunk_number": len(chunks),
                    "total_chunks": len(chunks),
                    "completed_chunks": len(chunks),
                }
                self._failure_record(failed_state, session_id, error_text, details=details)
                failures.append({"session_id": session_id, "error": error_text, **details})
                self.logger.exception("[LeafOS Interpreter ERROR] Session %s merge failed", session_id)
                continue

            processed.add(session_id)
            failed_state.pop(session_id, None)
            interpreted += 1
            interpreted_sessions.append(session_id)
            checkpoint_path = self._checkpoint_path(session_id)
            try:
                checkpoint_path.unlink(missing_ok=True)
            except OSError:
                self.logger.warning("[LeafOS Interpreter] Could not remove completed checkpoint %s", checkpoint_path)
            self._emit_progress(
                "session_complete",
                session_id=session_id,
                total_chunks=len(chunks),
                completed_chunks=len(chunks),
            )
            self.logger.info(
                "[LeafOS Interpreter] Candidate bundle created: %s (%s chunk%s)",
                session_id,
                len(chunks),
                "" if len(chunks) == 1 else "s",
            )
            if max_sessions is not None and interpreted >= max(1, int(max_sessions)):
                break

        if targets is not None:
            for missing in sorted(targets - found_targets):
                error_text = f"PROCESSOR_SESSION_NOT_FOUND: {missing}"
                failed += 1
                self._failure_record(failed_state, missing, error_text)
                failures.append({"session_id": missing, "error": error_text})

        state["processed_sessions"] = sorted(processed)
        state["failed_sessions"] = failed_state
        state["last_run"] = _utc_now()
        state["last_error"] = f'{failures[-1]["session_id"]}: {failures[-1]["error"]}' if failures else ""
        state["last_result"] = {
            "interpreted": interpreted,
            "skipped": skipped,
            "failed": failed,
        }
        _atomic_json(self.state_path, state)

        result: dict[str, Any] = {
            "interpreted": interpreted,
            "skipped": skipped,
            "failed": failed,
        }
        if include_details:
            result.update(
                {
                    "interpreted_sessions": interpreted_sessions,
                    "skipped_sessions": skipped_sessions,
                    "failures": failures,
                }
            )
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Interpret closed LeafOS sessions into review candidates.")
    parser.add_argument("--vault", required=True, help="Path to the LeafOS Obsidian vault")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help="Ollama base URL")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        help="Ollama request timeout in seconds, applied independently to each chunk",
    )
    parser.add_argument("--max-sessions", type=int, default=None, help="Maximum newly interpreted sessions in this run")
    parser.add_argument(
        "--max-transcript-chars",
        "--chunk-chars",
        dest="max_transcript_chars",
        type=int,
        default=DEFAULT_MAX_TRANSCRIPT_CHARS,
        help=f"Approximate maximum transcript characters per chunk (default: {DEFAULT_MAX_TRANSCRIPT_CHARS})",
    )
    parser.add_argument(
        "--chunk-overlap-messages",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP_MESSAGES,
        help=f"Messages repeated across chunk boundaries (default: {DEFAULT_CHUNK_OVERLAP_MESSAGES})",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    provider = OllamaInterpreterProvider(
        base_url=args.ollama_url,
        model=args.model,
        timeout_seconds=args.timeout,
    )
    agent_config = load_config()
    history = HistoryStore(agent_config.database_path)
    interpreter = LeafOSInterpreter(
        Path(args.vault),
        provider,
        max_transcript_chars=args.max_transcript_chars,
        chunk_overlap_messages=args.chunk_overlap_messages,
        primary_character_resolver=lambda session: resolve_primary_character(
            history,
            session.get("started_at"),
        ),
    )
    result = interpreter.run_once(max_sessions=args.max_sessions)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
