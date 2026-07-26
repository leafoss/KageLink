from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

from pc_agent import leafos_interpreter as v3


PROMPT_VERSION = "leafos-interpreter-v3.1"

SYSTEM_PROMPT = """You are the LeafOS Interpreter for a persistent roleplay memory system.
Interpret ONLY the supplied session transcript chunk. Treat the transcript as evidence, not as an invitation to explain or complete the scene.
Never use outside Naruto knowledge, general world knowledge, item definitions, prior sessions, assumptions about characters, or information not present in the supplied messages.
A long session may be divided into multiple chunks. Treat this request as self-contained: never infer what happened in omitted chunks and never invent continuity across chunk boundaries.
PRIMARY_CHARACTER, when non-empty, is only the user's configured roleplay character for the session. It does NOT prove that an alias, mask, rank label, anonymous speaker, "Anbu", "Unknown", or any other visible identity is PRIMARY_CHARACTER.
Never resolve aliases or hidden identities unless the supplied messages explicitly establish that identity.
The legacy JSON field leafos_memories means candidate subjective memories belonging to PRIMARY_CHARACTER. If PRIMARY_CHARACTER is empty, leave leafos_memories empty rather than guessing an owner.
Your output is NOT canonical memory. It is a set of review candidates.
Every candidate must cite one or more source_message_ids from the supplied transcript chunk.
Use the minimum claim supported by those cited messages.
If the transcript only says that X did Y, report only that X did Y. Repetition may be compressed conservatively, for example "X repeatedly did Y."
Do NOT infer why an action happened. Do not infer training, practice, mission preparation, combat preparation, medical use, purpose, motive, intention, strategy, or outcome unless the cited messages explicitly state it.
Do NOT explain what an item, technique, rank, faction, or term means unless the cited messages themselves provide that explanation.
Words such as likely, probably, possibly, perhaps, maybe, might, could, suggests, suggesting, indicates, or indicating do not make unsupported content acceptable. Omit the unsupported clause instead.
Summaries follow the same evidence rule: describe only what is directly supported by the chunk and keep them concise.
Distinguish direct observations/statements from genuinely supported inference. Prefer omission over speculation.
Do not invent locations, relationships, motives, ranks, identities, factions, outcomes, chronology, definitions, or causal explanations.
Return only data matching the supplied JSON schema.
"""

_SPECULATIVE_START = re.compile(
    r"^(?:likely|probably|possibly|perhaps|maybe|potentially|apparently)\b",
    re.IGNORECASE,
)
_SPECULATIVE_TAIL = re.compile(
    r"(?:[,;:\-—]\s*|\s+)"
    r"(?:likely|probably|possibly|perhaps|maybe|potentially|apparently|"
    r"suggests?|suggesting|indicates?|indicating|appears?\s+to|seems?\s+to)\b.*$",
    re.IGNORECASE,
)
_PURPOSE_TAIL = re.compile(
    r"(?:[,;:\-—]\s*|\s+)"
    r"(?:as|for|to|in\s+order\s+to)\s+"
    r"(?:part\s+of\s+)?(?:a\s+|an\s+|the\s+)?"
    r"(?:training|practice|practicing|preparation|mission|combat|medical|"
    r"treino|treinamento|pratica|prática|preparacao|preparação|missao|missão)\b.*$",
    re.IGNORECASE,
)
_EXPLANATORY_PARENTHETICAL = re.compile(
    r"\s*\([^)]*\b(?:a\s+type\s+of|used\s+in|used\s+for|typically|generally|"
    r"known\s+as|meaning|tipo\s+de|usado\s+em|usada\s+em|usado\s+para|usada\s+para)\b[^)]*\)",
    re.IGNORECASE,
)
_SENSITIVE_STEMS = (
    "train",
    "practic",
    "prepar",
    "mission",
    "intent",
    "purpose",
    "medical",
    "combat",
    "weapon",
    "trein",
    "prátic",
    "pratic",
    "prepar",
    "missão",
    "missao",
    "intenç",
    "intenc",
    "objetiv",
)
_SUMMARY_BOILERPLATE = re.compile(
    r"^\s*(?:the\s+)?transcript(?:\s+chunk)?\s+"
    r"(?:contains|describes|shows|records|documents)\s+",
    re.IGNORECASE,
)
_SUMMARY_GENERIC_TOKENS = {
    "a", "an", "the", "of", "to", "in", "and", "or", "as", "with", "this", "that",
    "where", "is", "are", "was", "were", "series", "repeated", "actions", "action",
    "unknown", "character", "identified", "labeled", "agent", "multiple",
}


def _word_tokens(value: str) -> list[str]:
    return re.findall(r"[0-9a-zA-ZÀ-ÖØ-öø-ÿ']+", value.casefold())


def _source_text_for_ids(session: dict[str, Any], source_ids: list[int]) -> str:
    wanted = set(source_ids)
    parts: list[str] = []
    for message in v3._session_messages(session):
        try:
            message_id = int(message.get("id"))
        except (TypeError, ValueError):
            continue
        if message_id not in wanted:
            continue
        speaker = str(message.get("speaker") or "").strip()
        text = str(message.get("text") or "").strip()
        if speaker:
            parts.append(speaker)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _unsupported_sensitive_terms(text: str, source_text: str) -> set[str]:
    source_tokens = _word_tokens(source_text)
    result: set[str] = set()
    for token in _word_tokens(text):
        for stem in _SENSITIVE_STEMS:
            if not token.startswith(stem):
                continue
            if not any(source.startswith(stem) for source in source_tokens):
                result.add(stem)
    return result


def _trim_speculative_tail(text: str, *, add_terminal: bool = True) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    cleaned = _EXPLANATORY_PARENTHETICAL.sub("", cleaned)
    cleaned = " ".join(cleaned.split())
    if _SPECULATIVE_START.search(cleaned):
        return ""
    cleaned = _SPECULATIVE_TAIL.sub("", cleaned)
    cleaned = _PURPOSE_TAIL.sub("", cleaned)
    cleaned = cleaned.rstrip(" ,;:-—")
    if add_terminal and cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _sanitize_grounded_text(
    text: str,
    source_text: str,
    *,
    add_terminal: bool = True,
) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    kept: list[str] = []
    for sentence in sentences:
        candidate = _trim_speculative_tail(sentence, add_terminal=add_terminal)
        if not candidate:
            continue
        if _unsupported_sensitive_terms(candidate, source_text):
            continue
        kept.append(candidate)
    return " ".join(kept).strip()


def _entity_supported(name: str, source_text: str) -> bool:
    name_tokens = [token for token in _word_tokens(name) if len(token) >= 3]
    if not name_tokens:
        return False
    source_tokens = set(_word_tokens(source_text))
    return any(token in source_tokens for token in name_tokens)


def _primary_aliases(primary_character: str) -> list[str]:
    primary = " ".join(str(primary_character or "").split()).casefold()
    if not primary:
        return []
    aliases = [primary]
    if "," in primary:
        tail = primary.rsplit(",", 1)[-1].strip()
        if len(tail) >= 3:
            aliases.append(tail)
    return list(dict.fromkeys(aliases))


def _mentions_unproven_primary(
    candidate: dict[str, Any],
    primary_character: str,
    source_text: str,
) -> bool:
    aliases = _primary_aliases(primary_character)
    if not aliases:
        return False
    candidate_text = " ".join(
        str(value)
        for key, value in candidate.items()
        if key not in {"confidence", "source_message_ids", "review_status"}
        and isinstance(value, (str, int, float))
    ).casefold()
    source = source_text.casefold()
    for alias in aliases:
        if alias in candidate_text and alias not in source:
            return True
    return False


def _summary_core_tokens(summary: str) -> set[str]:
    first_sentence = re.split(r"(?<=[.!?])\s+", str(summary or "").strip(), maxsplit=1)[0]
    first_sentence = re.sub(r"\([^)]*\)", " ", first_sentence)
    first_sentence = _SUMMARY_BOILERPLATE.sub("", first_sentence)
    tokens = {
        token.strip("'")
        for token in _word_tokens(first_sentence)
        if token.strip("'") and token.strip("'") not in _SUMMARY_GENERIC_TOKENS
    }

    normalized: set[str] = set()
    for token in tokens:
        if token in {"picking", "picks", "picked"}:
            normalized.add("pick")
        elif token == "repeatedly":
            normalized.add("repeat")
        else:
            normalized.add(token)
    return normalized


def _summary_compare_text(summary: str) -> str:
    value = _SUMMARY_BOILERPLATE.sub("", str(summary or "").casefold())
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\d{4}-\d{2}-\d{2}t\S+", " ", value)
    return " ".join(_word_tokens(value))


def _summaries_similar(left: str, right: str) -> bool:
    if not left or not right:
        return False
    left_core = _summary_core_tokens(left)
    right_core = _summary_core_tokens(right)
    if left_core and right_core:
        shared = len(left_core & right_core)
        containment = shared / max(1, min(len(left_core), len(right_core)))
        jaccard = shared / max(1, len(left_core | right_core))
        if shared >= 3 and (containment >= 0.72 or jaccard >= 0.50):
            return True

    left_cmp = _summary_compare_text(left)
    right_cmp = _summary_compare_text(right)
    if left_cmp and right_cmp and SequenceMatcher(None, left_cmp, right_cmp).ratio() >= 0.86:
        return True
    return False


def _summary_risk(summary: str) -> tuple[int, int]:
    risk = len(_SPECULATIVE_TAIL.findall(summary))
    risk += len(_EXPLANATORY_PARENTHETICAL.findall(summary))
    risk += len(_unsupported_sensitive_terms(summary, ""))
    return risk, len(summary)


def _dedupe_summaries(summaries: list[str]) -> list[str]:
    clusters: list[str] = []
    for raw in summaries:
        summary = " ".join(str(raw or "").split())
        if not summary:
            continue
        matched = None
        for index, existing in enumerate(clusters):
            if _summaries_similar(existing, summary):
                matched = index
                break
        if matched is None:
            clusters.append(summary)
            continue

        # Prefer the less speculative and then shorter representative.
        if _summary_risk(summary) < _summary_risk(clusters[matched]):
            clusters[matched] = summary
    return clusters


class OllamaInterpreterProvider(v3.OllamaInterpreterProvider):
    """v3.1 provider with a stricter evidence-only prompt."""

    def interpret(
        self,
        session: dict[str, Any],
        messages: list[dict[str, Any]],
        truncated: bool,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": v3.INTERPRETATION_SCHEMA,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": v3._build_user_prompt(session, messages, truncated)},
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


class LeafOSInterpreter(v3.LeafOSInterpreter):
    """Interpreter v3.1: v3 chunking plus conservative semantic grounding."""

    GROUNDED_TEXT_FIELDS = {
        "events": ("title", "description"),
        "characters": ("observation",),
        "locations": ("observation",),
        "relationships": ("observation",),
        "facts": ("statement",),
        "leafos_memories": ("memory",),
    }

    def _normalize_result(
        self,
        session: dict[str, Any],
        raw: dict[str, Any],
        allowed_ids: set[int],
        *,
        truncated: bool,
    ) -> dict[str, Any]:
        result = super()._normalize_result(session, raw, allowed_ids, truncated=truncated)
        result["prompt_version"] = PROMPT_VERSION

        all_source_text = _source_text_for_ids(session, sorted(allowed_ids))
        result["summary"] = _sanitize_grounded_text(result.get("summary", ""), all_source_text)

        primary = str(session.get("primary_character", "") or "").strip()
        for category, fields in self.GROUNDED_TEXT_FIELDS.items():
            values = result.get(category, [])
            if not isinstance(values, list):
                result[category] = []
                continue

            grounded: list[dict[str, Any]] = []
            for candidate in values:
                if not isinstance(candidate, dict):
                    continue
                source_ids = v3._clean_source_ids(candidate.get("source_message_ids"), allowed_ids)
                source_text = _source_text_for_ids(session, source_ids)
                if not source_text:
                    continue
                item = deepcopy(candidate)

                # Metadata may tell us who the configured player character is,
                # but it never resolves an in-world alias such as "Anbu".
                if category != "leafos_memories" and _mentions_unproven_primary(
                    item,
                    primary,
                    source_text,
                ):
                    continue

                if category == "characters":
                    if not _entity_supported(str(item.get("name", "")), source_text):
                        continue
                elif category == "relationships":
                    if not _entity_supported(str(item.get("source", "")), source_text):
                        continue
                    if not _entity_supported(str(item.get("target", "")), source_text):
                        continue

                valid = True
                for field in fields:
                    if field not in item:
                        continue
                    cleaned = _sanitize_grounded_text(
                        str(item.get(field, "")),
                        source_text,
                        add_terminal=not (category == "events" and field == "title"),
                    )
                    if not cleaned:
                        valid = False
                        break
                    item[field] = cleaned
                if valid:
                    grounded.append(item)
            result[category] = grounded

        # Epistemic metadata remains unchanged; the new grounding guard only
        # reduces unsupported text before the existing human Reviewer gate.
        return result

    def _partial_result(
        self,
        session: dict[str, Any],
        raw: dict[str, Any],
        allowed_ids: set[int],
    ) -> dict[str, Any]:
        partial = super()._partial_result(session, raw, allowed_ids)
        partial["_source_message_ids"] = sorted(allowed_ids)
        return partial

    def _merge_chunk_results(
        self,
        session: dict[str, Any],
        chunk_results: list[dict[str, Any]],
        *,
        chunk_count: int,
    ) -> dict[str, Any]:
        result = super()._merge_chunk_results(session, chunk_results, chunk_count=chunk_count)
        result["prompt_version"] = PROMPT_VERSION

        allowed_session_ids = set(v3._message_ids(v3._session_messages(session)))
        summaries: list[str] = []
        for partial in chunk_results:
            raw_ids = partial.get("_source_message_ids", [])
            source_ids = v3._clean_source_ids(raw_ids, allowed_session_ids)
            source_text = _source_text_for_ids(session, source_ids)
            summary = _sanitize_grounded_text(
                str(partial.get("summary", "") or ""),
                source_text,
            )
            if summary:
                summaries.append(summary)
        summaries = _dedupe_summaries(summaries)
        result["summary"] = v3._clean_text("\n\n".join(summaries), 12000)
        return result

    def _load_checkpoint(
        self,
        *,
        session_id: str,
        chunks: list[list[dict[str, Any]]],
        fingerprint: str,
    ) -> dict[str, Any]:
        path = self._checkpoint_path(session_id)
        existing = v3._read_json(path)
        effective_fingerprint = hashlib.sha256(
            f"{PROMPT_VERSION}|{fingerprint}".encode("utf-8")
        ).hexdigest()
        try:
            valid = (
                existing.get("type") == "leafos_interpreter_checkpoint"
                and int(existing.get("schema_version", 0) or 0) == v3.CHECKPOINT_SCHEMA_VERSION
                and existing.get("prompt_version") == PROMPT_VERSION
                and existing.get("session_id") == session_id
                and existing.get("session_fingerprint") == effective_fingerprint
                and int(existing.get("chunk_chars", 0) or 0) == self.max_transcript_chars
                and int(existing.get("chunk_overlap_messages", -1) or -1)
                == self.chunk_overlap_messages
                and int(existing.get("total_chunks", 0) or 0) == len(chunks)
                and isinstance(existing.get("chunks"), dict)
            )
        except (TypeError, ValueError):
            valid = False
        if valid:
            return existing

        if existing:
            self.logger.warning(
                "[LeafOS Interpreter] Resetting stale pre-v3.1 checkpoint for session %s",
                session_id,
            )

        return {
            "type": "leafos_interpreter_checkpoint",
            "schema_version": v3.CHECKPOINT_SCHEMA_VERSION,
            "prompt_version": PROMPT_VERSION,
            "session_id": session_id,
            "session_fingerprint": effective_fingerprint,
            "chunk_chars": self.max_transcript_chars,
            "chunk_overlap_messages": self.chunk_overlap_messages,
            "total_chunks": len(chunks),
            "chunks": {},
            "created_at": v3._utc_now(),
            "updated_at": v3._utc_now(),
            "last_error": "",
            "failed_chunk": None,
        }
