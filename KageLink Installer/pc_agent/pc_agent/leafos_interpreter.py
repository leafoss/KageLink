from __future__ import annotations

import argparse
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROMPT_VERSION = "leafos-interpreter-v1"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:14b"
DEFAULT_MAX_TRANSCRIPT_CHARS = 48000

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
Interpret ONLY the supplied session transcript. Never use outside Naruto knowledge, prior knowledge, assumptions about characters, or information not present in the supplied messages.
Your output is NOT canonical memory. It is a set of review candidates.
Every candidate must cite one or more source_message_ids from the supplied transcript.
If the transcript does not support something, omit it.
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


def _select_messages(session: dict[str, Any], max_chars: int) -> tuple[list[dict[str, Any]], bool]:
    raw_messages = session.get("messages", [])
    if not isinstance(raw_messages, list):
        return [], False
    messages = [dict(item) for item in raw_messages if isinstance(item, dict)]
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


def _build_user_prompt(session: dict[str, Any], messages: list[dict[str, Any]], truncated: bool) -> str:
    transcript_lines = []
    for item in messages:
        transcript_lines.append(
            f'[{item.get("id")}] timestamp={item.get("timestamp", "")} '
            f'speaker={item.get("speaker") or "UNKNOWN"}\n{item.get("text", "")}'
        )
    participants = session.get("participants", [])
    if not isinstance(participants, list):
        participants = []
    return (
        f'SESSION_ID: {session.get("session_id", "")}\n'
        f'STARTED_AT: {session.get("started_at", "")}\n'
        f'ENDED_AT: {session.get("ended_at", "")}\n'
        f'PARTICIPANTS_DETECTED: {json.dumps(participants, ensure_ascii=False)}\n'
        f'TRANSCRIPT_TRUNCATED: {str(truncated).lower()}\n\n'
        'TRANSCRIPT:\n' + "\n\n".join(transcript_lines)
    )


class OllamaInterpreterProvider:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 180.0,
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
        except urllib.error.URLError as error:
            raise RuntimeError(f"OLLAMA_UNAVAILABLE: {error}") from error
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


class LeafOSInterpreter:
    """Turns closed Processor sessions into non-canonical review candidates."""

    CATEGORIES = ("events", "characters", "locations", "relationships", "facts", "leafos_memories")

    def __init__(
        self,
        vault_path: Path,
        provider: Any,
        *,
        max_transcript_chars: int = DEFAULT_MAX_TRANSCRIPT_CHARS,
        logger: logging.Logger | None = None,
    ) -> None:
        self.vault_path = Path(vault_path)
        self.provider = provider
        self.max_transcript_chars = max(4000, int(max_transcript_chars))
        self.logger = logger or logging.getLogger("kagelink.leafos.interpreter")

    @property
    def sessions_dir(self) -> Path:
        return self.vault_path / "80 - Processor" / "Sessions"

    @property
    def state_path(self) -> Path:
        return self.vault_path / "80 - Interpreter" / "interpreter_state.json"

    @property
    def inbox_dir(self) -> Path:
        return self.vault_path / "70 - LeafOS Inbox" / "Interpretations"

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

    def _session_files(self) -> list[Path]:
        if not self.sessions_dir.exists():
            return []
        return sorted(self.sessions_dir.glob("*.json"))

    def run_once(self, *, max_sessions: int | None = None) -> dict[str, int]:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        state = _read_json(
            self.state_path,
            {
                "schema_version": 1,
                "processed_sessions": [],
                "last_run": "",
                "last_error": "",
            },
        )
        processed = {str(value) for value in state.get("processed_sessions", []) if str(value)}
        interpreted = 0
        skipped = 0
        failed = 0

        for path in self._session_files():
            session = _read_json(path)
            session_id = str(session.get("session_id") or path.stem)
            if session_id in processed:
                skipped += 1
                continue
            output_path = self.inbox_dir / f"{_safe_session_id(session_id)}.json"
            if output_path.exists():
                processed.add(session_id)
                skipped += 1
                continue

            messages, truncated = _select_messages(session, self.max_transcript_chars)
            allowed_ids: set[int] = set()
            for item in messages:
                try:
                    allowed_ids.add(int(item.get("id")))
                except (TypeError, ValueError):
                    pass
            if not allowed_ids:
                failed += 1
                state["last_error"] = f"SESSION_WITHOUT_MESSAGES: {session_id}"
                continue

            try:
                raw_result = self.provider.interpret(session, messages, truncated)
                bundle = self._normalize_result(
                    session,
                    raw_result,
                    allowed_ids,
                    truncated=truncated,
                )
                _atomic_json(output_path, bundle)
            except Exception as error:
                failed += 1
                state["last_error"] = f"{session_id}: {error}"
                self.logger.exception("[LeafOS Interpreter ERROR] Session %s failed", session_id)
                continue

            processed.add(session_id)
            interpreted += 1
            state["last_error"] = ""
            self.logger.info("[LeafOS Interpreter] Candidate bundle created: %s", session_id)
            if max_sessions is not None and interpreted >= max(1, int(max_sessions)):
                break

        state["processed_sessions"] = sorted(processed)
        state["last_run"] = _utc_now()
        _atomic_json(self.state_path, state)
        return {"interpreted": interpreted, "skipped": skipped, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Interpret closed LeafOS sessions into review candidates.")
    parser.add_argument("--vault", required=True, help="Path to the LeafOS Obsidian vault")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help="Ollama base URL")
    parser.add_argument("--timeout", type=float, default=180.0, help="Ollama request timeout in seconds")
    parser.add_argument("--max-sessions", type=int, default=None, help="Maximum newly interpreted sessions in this run")
    parser.add_argument("--max-transcript-chars", type=int, default=DEFAULT_MAX_TRANSCRIPT_CHARS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    provider = OllamaInterpreterProvider(
        base_url=args.ollama_url,
        model=args.model,
        timeout_seconds=args.timeout,
    )
    interpreter = LeafOSInterpreter(
        Path(args.vault),
        provider,
        max_transcript_chars=args.max_transcript_chars,
    )
    result = interpreter.run_once(max_sessions=args.max_sessions)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
