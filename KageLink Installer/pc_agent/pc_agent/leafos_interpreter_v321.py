from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any

from pc_agent import leafos_interpreter as v3
from pc_agent import leafos_interpreter_v31 as v31
from pc_agent import leafos_interpreter_v32 as v32


PROMPT_VERSION = "leafos-interpreter-v3.2.1"
DURABLE_SYSTEM_SCHEMA_VERSION = 1

_PRIMARY_ELEMENT = re.compile(
    r"^\s*(?:your\s+)?primary\s+element\s+is\s*:\s*(?P<value>[^\r\n]+?)\s*$",
    re.IGNORECASE,
)
_SECONDARY_ELEMENT = re.compile(
    r"^\s*(?:your\s+)?secondary\s+element\s+is\s*:\s*(?P<value>[^\r\n]+?)\s*$",
    re.IGNORECASE,
)


def _clean_revelation_value(value: str) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    return cleaned.strip(" .,:;!?()[]{}")[:120]


def _durable_system_revelations(session: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract only explicit, durable system revelations with known log syntax.

    v3.2.1 intentionally starts narrow. It recognizes the exact Element result
    lines observed in Shinobi Story Online and does not infer who owns the result.
    Additional durable system formats should be added only after their real log
    syntax is observed and regression-tested.
    """

    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()

    for message in v3._session_messages(session):
        try:
            message_id = int(message.get("id"))
        except (TypeError, ValueError):
            continue

        text = str(message.get("text") or "").strip()
        if not text:
            continue

        match = _PRIMARY_ELEMENT.match(text)
        field = "primary_element"
        label = "primary Element"
        if match is None:
            match = _SECONDARY_ELEMENT.match(text)
            field = "secondary_element"
            label = "secondary Element"
        if match is None:
            continue

        value = _clean_revelation_value(match.group("value"))
        if not value:
            continue

        key = (field, value.casefold(), message_id)
        if key in seen:
            continue
        seen.add(key)

        result.append(
            {
                "field": field,
                "value": value,
                "source_message_ids": [message_id],
                "candidate": {
                    "statement": f"The system reported the {label} as {value}.",
                    "kind": "system_revelation",
                    "confidence": 1.0,
                    "source_message_ids": [message_id],
                    "review_status": "pending_review",
                },
            }
        )

    return result


def _same_revelation_candidate(
    candidate: dict[str, Any],
    revelation: dict[str, Any],
) -> bool:
    candidate_ids = set(
        v3._clean_source_ids(
            candidate.get("source_message_ids"),
            set(revelation.get("source_message_ids", [])),
        )
    )
    revelation_ids = set(revelation.get("source_message_ids", []))
    if candidate_ids != revelation_ids:
        return False

    text = v32._candidate_text(candidate).casefold()
    value = str(revelation.get("value") or "").casefold()
    field = str(revelation.get("field") or "")
    marker = "primary" if field == "primary_element" else "secondary"
    return bool(value and value in text and marker in text and "element" in text)


def _refresh_salience_metadata(result: dict[str, Any]) -> None:
    kept_count = 0
    for category in v32.LeafOSInterpreter.CATEGORIES:
        values = result.get(category, [])
        if isinstance(values, list):
            kept_count += sum(1 for item in values if isinstance(item, dict))

    suppressed = result.get("suppressed_candidates", [])
    if not isinstance(suppressed, list):
        suppressed = []
        result["suppressed_candidates"] = suppressed

    decisions: dict[str, int] = {}
    for item in suppressed:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision") or "unknown")
        decisions[decision] = decisions.get(decision, 0) + 1

    salience = result.get("salience")
    if not isinstance(salience, dict):
        salience = {}
        result["salience"] = salience
    salience["schema_version"] = v32.SALIENCE_SCHEMA_VERSION
    salience["mode"] = "deterministic"
    salience["review_threshold"] = v32.SALIENCE_REVIEW_THRESHOLD
    salience["review_candidates"] = kept_count
    salience["suppressed_candidates"] = len(suppressed)
    salience["decisions"] = decisions


class OllamaInterpreterProvider(v32.OllamaInterpreterProvider):
    """Keep the proven v3.1 evidence-only model prompt unchanged in v3.2.1."""


class LeafOSInterpreter(v32.LeafOSInterpreter):
    """v3.2.1: v3.2 salience plus deterministic durable system revelations."""

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
        result["salience_base_version"] = v32.PROMPT_VERSION

        revelations = _durable_system_revelations(session)
        facts = result.get("facts")
        if not isinstance(facts, list):
            facts = []
            result["facts"] = facts

        suppressed = result.get("suppressed_candidates")
        if not isinstance(suppressed, list):
            suppressed = []

        promoted = 0
        detected_fields: list[str] = []
        for revelation in revelations:
            field = str(revelation.get("field") or "")
            if field and field not in detected_fields:
                detected_fields.append(field)

            # If v3.2 already suppressed a model-produced version of exactly the
            # same explicit system revelation, remove only that matching audit
            # record before adding the deterministic grounded fact.
            filtered_suppressed: list[dict[str, Any]] = []
            for item in suppressed:
                if not isinstance(item, dict) or item.get("category") != "facts":
                    filtered_suppressed.append(item)
                    continue
                candidate = item.get("candidate")
                if not isinstance(candidate, dict) or not _same_revelation_candidate(
                    candidate,
                    revelation,
                ):
                    filtered_suppressed.append(item)
            suppressed = filtered_suppressed

            deterministic_candidate = deepcopy(revelation["candidate"])
            if any(
                isinstance(existing, dict)
                and _same_revelation_candidate(existing, revelation)
                for existing in facts
            ):
                continue
            facts.append(deterministic_candidate)
            promoted += 1

        result["suppressed_candidates"] = suppressed
        result["durable_system_revelations"] = {
            "schema_version": DURABLE_SYSTEM_SCHEMA_VERSION,
            "mode": "deterministic_explicit_patterns",
            "detected": len(revelations),
            "promoted": promoted,
            "fields": detected_fields,
            "identity_attribution": "not_inferred",
        }
        _refresh_salience_metadata(result)
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
                "[LeafOS Interpreter] Resetting stale pre-v3.2.1 checkpoint for session %s",
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
