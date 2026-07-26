from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any

from pc_agent import leafos_interpreter as v3
from pc_agent import leafos_interpreter_v31 as v31


PROMPT_VERSION = "leafos-interpreter-v3.2"
SALIENCE_SCHEMA_VERSION = 1
SALIENCE_REVIEW_THRESHOLD = 2

_MECHANICAL_ACTION = re.compile(
    r"\b(?:pick(?:s|ed|ing)?\s+up|drop(?:s|ped|ping)?|put(?:s|ting)?\s+down|"
    r"equip(?:s|ped|ping)?|unequip(?:s|ped|ping)?|interact(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)
_TRANSIENT_ACTION = re.compile(
    r"\b(?:walk(?:s|ed|ing)?|look(?:s|ed|ing)?|turn(?:s|ed|ing)?|"
    r"sit(?:s|ting)?|sat|stand(?:s|ing)?|stood|open(?:s|ed|ing)?|"
    r"close(?:s|d|ing)?|move(?:s|d|ing)?|pick(?:s|ed|ing)?\s+up|"
    r"drop(?:s|ped|ping)?|interact(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)
_DURABLE_CHARACTER = re.compile(
    r"\b(?:member(?:ship)?|belongs?|rank|clan|family|brother|sister|mother|father|"
    r"son|daughter|parent|scar|hair|eyes?|ability|skill|trait|knows?|prefers?|"
    r"believes?|fears?|loyal|serves?|role|leader|medic|teacher|student|"
    r"personality|goal|origin|home|village)\b",
    re.IGNORECASE,
)
_RELATIONSHIP = re.compile(
    r"\b(?:trust(?:s|ed|ing)?|distrust(?:s|ed|ing)?|ally|allies|allied|friend|"
    r"enemy|rival|brother|sister|family|protect(?:s|ed|ing)?|betray(?:s|ed|ing)?|"
    r"owe(?:s|d)?|loyal|serve(?:s|d)?|threaten(?:s|ed|ing)?|captor|prisoner|"
    r"capture(?:s|d|ing)?)\b",
    re.IGNORECASE,
)
_DECISION = re.compile(
    r"\b(?:decid(?:e|ed|es|ing)|agree(?:d|s|ing)?|choose|chooses|chose|"
    r"plan(?:s|ned|ning)?|order(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)
_COMMITMENT = re.compile(
    r"\b(?:promise(?:s|d|ing)?|swear(?:s|ing)?|swore|vow(?:s|ed|ing)?|"
    r"commit(?:s|ted|ting)?|threaten(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)
_STATE_CHANGE = re.compile(
    r"\b(?:become(?:s)?|became|promot(?:e|ed|es|ing)|demot(?:e|ed|es|ing)|"
    r"captur(?:e|ed|es|ing)|releas(?:e|ed|es|ing)|reveal(?:s|ed|ing)?|"
    r"discover(?:s|ed|ing)?|learn(?:s|ed|t|ing)?|die(?:s|d)?|dead|killed|"
    r"defeat(?:s|ed|ing)?|injur(?:e|ed|es|ing)|rescu(?:e|ed|es|ing)|"
    r"escap(?:e|ed|es|ing)|save(?:s|d|ing)?)\b",
    re.IGNORECASE,
)
_TRANSFER = re.compile(
    r"\b(?:give(?:s)?|gave|given|hand(?:s|ed|ing)?|receive(?:s|d|ing)?|"
    r"pass(?:es|ed|ing)?|deliver(?:s|ed|ing)?|entrust(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)
_CONFLICT = re.compile(
    r"\b(?:attack(?:s|ed|ing)?|fight(?:s|ing)?|fought|strike(?:s)?|struck|"
    r"capture(?:s|d|ing)?|kill(?:s|ed|ing)?|injur(?:e|ed|es|ing)|"
    r"defeat(?:s|ed|ing)?|ambush(?:es|ed|ing)?)\b",
    re.IGNORECASE,
)
_TRAVEL = re.compile(
    r"\b(?:enter(?:s|ed|ing)?|arriv(?:e|ed|es|ing)|leave(?:s|d|ing)?|left|"
    r"return(?:s|ed|ing)?|travel(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in candidate.items():
        if key in {"confidence", "source_message_ids", "review_status"}:
            continue
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " ".join(parts)


def _messages_for_ids(session: dict[str, Any], source_ids: list[int]) -> list[dict[str, Any]]:
    wanted = set(source_ids)
    result: list[dict[str, Any]] = []
    for message in v3._session_messages(session):
        try:
            message_id = int(message.get("id"))
        except (TypeError, ValueError):
            continue
        if message_id in wanted:
            result.append(message)
    return result


def _has_dialogue(messages: list[dict[str, Any]]) -> bool:
    return any(str(item.get("speaker") or "").strip() for item in messages)


def _mechanical_repetition(messages: list[dict[str, Any]]) -> bool:
    if len(messages) < 3:
        return False
    texts = [str(item.get("text") or "") for item in messages]
    mechanical = sum(1 for text in texts if _MECHANICAL_ACTION.search(text))
    return mechanical / max(1, len(texts)) >= 0.70


def _explicit_primary_present(session: dict[str, Any], source_text: str) -> bool:
    source = source_text.casefold()
    for alias in v31._primary_aliases(str(session.get("primary_character", "") or "")):
        if alias and alias in source:
            return True
    return False


def _category_gate(
    category: str,
    candidate: dict[str, Any],
    source_text: str,
) -> tuple[bool, list[str]]:
    candidate_text = _candidate_text(candidate)
    combined = f"{candidate_text}\n{source_text}"

    if category == "characters":
        observation = str(candidate.get("observation", "") or "")
        has_transient = bool(_TRANSIENT_ACTION.search(observation))
        has_durable = bool(_DURABLE_CHARACTER.search(combined))
        if has_transient and not has_durable:
            return False, ["transient_character_observation"]

    if category == "relationships" and not _RELATIONSHIP.search(combined):
        return False, ["relationship_without_supported_relation"]

    return True, []


def _salience_score(
    category: str,
    candidate: dict[str, Any],
    session: dict[str, Any],
    source_ids: list[int],
) -> tuple[int, list[str]]:
    messages = _messages_for_ids(session, source_ids)
    source_text = v31._source_text_for_ids(session, source_ids)
    candidate_text = _candidate_text(candidate)
    evidence = f"{source_text}\n{candidate_text}"

    score = 0
    signals: list[str] = []

    def add(signal: str, delta: int) -> None:
        nonlocal score
        score += delta
        signals.append(f"{signal}:{delta:+d}")

    # Category priors are intentionally small. They do not make an otherwise
    # trivial action memorable by themselves.
    if category == "relationships":
        add("relationship_category", 2)
    elif category == "leafos_memories":
        add("subjective_memory_category", 2)
    elif category == "locations":
        add("location_candidate", 2)
    elif category == "facts":
        add("fact_candidate", 1)

    if category == "characters" and _DURABLE_CHARACTER.search(evidence):
        add("durable_character_revelation", 3)
    if _RELATIONSHIP.search(evidence):
        add("relationship_signal", 3)
    if _DECISION.search(evidence):
        add("decision_or_agreement", 3)
    if _COMMITMENT.search(evidence):
        add("commitment_or_threat", 2)
    if _STATE_CHANGE.search(evidence):
        add("state_change_or_consequence", 3)
    if _TRANSFER.search(evidence):
        add("meaningful_transfer", 2)
    if _CONFLICT.search(evidence):
        add("conflict_or_capture", 2)
    if _TRAVEL.search(evidence):
        add("travel_or_arrival", 1)
    if _has_dialogue(messages):
        add("dialogue_present", 1)
    if _explicit_primary_present(session, source_text):
        add("primary_character_explicit", 1)

    if _mechanical_repetition(messages):
        add("mechanical_repetition", -3)

    has_positive_context = any(
        pattern.search(evidence)
        for pattern in (
            _RELATIONSHIP,
            _DECISION,
            _COMMITMENT,
            _STATE_CHANGE,
            _TRANSFER,
            _CONFLICT,
        )
    )
    if _MECHANICAL_ACTION.search(evidence) and not has_positive_context:
        add("transient_object_interaction", -2)

    if (
        category == "events"
        and _TRANSIENT_ACTION.search(evidence)
        and not has_positive_context
        and not _TRAVEL.search(evidence)
        and not _MECHANICAL_ACTION.search(evidence)
    ):
        add("transient_action_without_consequence", -2)

    return score, signals


def _suppression_record(
    *,
    category: str,
    candidate: dict[str, Any],
    decision: str,
    score: int,
    signals: list[str],
) -> dict[str, Any]:
    return {
        "category": category,
        "decision": decision,
        "score": score,
        "signals": list(signals),
        "candidate": deepcopy(candidate),
    }


class OllamaInterpreterProvider(v31.OllamaInterpreterProvider):
    """Keep the proven v3.1 evidence-only prompt unchanged for v3.2."""


class LeafOSInterpreter(v31.LeafOSInterpreter):
    """Interpreter v3.2: v3.1 grounding plus deterministic category/salience gates."""

    def _merge_chunk_results(
        self,
        session: dict[str, Any],
        chunk_results: list[dict[str, Any]],
        *,
        chunk_count: int,
    ) -> dict[str, Any]:
        result = super()._merge_chunk_results(session, chunk_results, chunk_count=chunk_count)
        result["prompt_version"] = PROMPT_VERSION
        result["grounding_prompt_version"] = v31.PROMPT_VERSION

        allowed_session_ids = set(v3._message_ids(v3._session_messages(session)))
        suppressed: list[dict[str, Any]] = []
        kept_count = 0
        decision_counts = {"low_salience": 0, "invalid_category": 0}

        for category in self.CATEGORIES:
            values = result.get(category, [])
            if not isinstance(values, list):
                result[category] = []
                continue

            kept: list[dict[str, Any]] = []
            for candidate in values:
                if not isinstance(candidate, dict):
                    continue

                source_ids = v3._clean_source_ids(
                    candidate.get("source_message_ids"),
                    allowed_session_ids,
                )
                if not source_ids:
                    continue
                source_text = v31._source_text_for_ids(session, source_ids)

                valid_category, gate_signals = _category_gate(
                    category,
                    candidate,
                    source_text,
                )
                score, salience_signals = _salience_score(
                    category,
                    candidate,
                    session,
                    source_ids,
                )

                if not valid_category:
                    decision_counts["invalid_category"] += 1
                    suppressed.append(
                        _suppression_record(
                            category=category,
                            candidate=candidate,
                            decision="invalid_category",
                            score=score,
                            signals=gate_signals + salience_signals,
                        )
                    )
                    continue

                if score < SALIENCE_REVIEW_THRESHOLD:
                    decision_counts["low_salience"] += 1
                    suppressed.append(
                        _suppression_record(
                            category=category,
                            candidate=candidate,
                            decision="low_salience",
                            score=score,
                            signals=salience_signals,
                        )
                    )
                    continue

                kept.append(candidate)
                kept_count += 1

            result[category] = kept

        result["suppressed_candidates"] = suppressed
        result["salience"] = {
            "schema_version": SALIENCE_SCHEMA_VERSION,
            "mode": "deterministic",
            "review_threshold": SALIENCE_REVIEW_THRESHOLD,
            "review_candidates": kept_count,
            "suppressed_candidates": len(suppressed),
            "decisions": decision_counts,
        }
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
                and int(existing.get("schema_version", 0) or 0)
                == v3.CHECKPOINT_SCHEMA_VERSION
                and existing.get("prompt_version") == PROMPT_VERSION
                and existing.get("session_id") == session_id
                and existing.get("session_fingerprint") == effective_fingerprint
                and int(existing.get("chunk_chars", 0) or 0)
                == self.max_transcript_chars
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
                "[LeafOS Interpreter] Resetting stale pre-v3.2 checkpoint for session %s",
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
