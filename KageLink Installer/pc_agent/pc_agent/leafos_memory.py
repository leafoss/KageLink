from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from pc_agent.leafos_memory_support import (
    CANONICAL_CATEGORY_MAP,
    CANONICAL_MEMORY_SCHEMA_VERSION,
    INTERPRETER_CATEGORIES,
    REVIEWER_SCHEMA_VERSION,
    EvidenceError,
    ReviewerError,
    _atomic_json,
    _candidate_digest,
    _read_json,
    _raw_records,
    _relative_or_absolute,
    _safe_name,
    _utc_now,
    epistemic_metadata,
    render_memory_markdown,
    validate_edit,
)


class LeafOSMemoryReviewer:
    """Human-gated promotion of Interpreter candidates into canonical memory.

    The Reviewer never mutates RAW, Processor sessions, or Interpreter bundles.
    Its writable surface is limited to Reviewer state and Canonical Memory.
    """

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = Path(vault_path)

    @property
    def interpretations_dir(self) -> Path:
        return self.vault_path / "70 - LeafOS Inbox" / "Interpretations"

    @property
    def sessions_dir(self) -> Path:
        return self.vault_path / "80 - Processor" / "Sessions"

    @property
    def reviewer_root(self) -> Path:
        return self.vault_path / "80 - Memory Reviewer"

    @property
    def reviews_dir(self) -> Path:
        return self.reviewer_root / "Reviews"

    @property
    def canonical_root(self) -> Path:
        return self.vault_path / "60 - Canonical Memory"

    @property
    def canonical_memory_path(self) -> Path:
        return self.canonical_root / "memory.json"

    @property
    def canonical_markdown_path(self) -> Path:
        return self.canonical_root / "MEMORY.md"

    def _bundle_files(self) -> list[Path]:
        if not self.interpretations_dir.exists():
            return []
        return sorted(self.interpretations_dir.glob("*.json"))

    def _bundle_by_session(self, session_id: str) -> tuple[Path, dict[str, Any]]:
        expected = self.interpretations_dir / f"{_safe_name(session_id)}.json"
        if expected.exists():
            bundle = _read_json(expected)
            if str(bundle.get("session_id") or expected.stem) == session_id:
                return expected, bundle
        for path in self._bundle_files():
            bundle = _read_json(path)
            if str(bundle.get("session_id") or path.stem) == session_id:
                return path, bundle
        raise ReviewerError(f"INTERPRETATION_BUNDLE_NOT_FOUND: {session_id}")

    def _processor_session(self, session_id: str) -> tuple[Path, dict[str, Any]]:
        expected = self.sessions_dir / f"{_safe_name(session_id)}.json"
        if not expected.exists():
            raise EvidenceError(f"PROCESSOR_SESSION_NOT_FOUND: {session_id}")
        session = _read_json(expected)
        if str(session.get("session_id") or expected.stem) != session_id:
            raise EvidenceError(f"PROCESSOR_SESSION_ID_MISMATCH: {session_id}")
        return expected, session

    def _review_path(self, session_id: str) -> Path:
        return self.reviews_dir / f"{_safe_name(session_id)}.json"

    def _load_reviews(self, session_id: str) -> dict[str, Any]:
        payload = _read_json(
            self._review_path(session_id),
            {
                "type": "leafos_memory_reviews",
                "schema_version": REVIEWER_SCHEMA_VERSION,
                "session_id": session_id,
                "updated_at": "",
                "reviews": {},
            },
        )
        reviews = payload.get("reviews")
        if not isinstance(reviews, dict):
            payload["reviews"] = {}
        return payload

    def _save_reviews(self, session_id: str, payload: dict[str, Any]) -> None:
        payload["type"] = "leafos_memory_reviews"
        payload["schema_version"] = REVIEWER_SCHEMA_VERSION
        payload["session_id"] = session_id
        payload["updated_at"] = _utc_now()
        _atomic_json(self._review_path(session_id), payload)

    def _load_memory(self) -> dict[str, Any]:
        payload = _read_json(
            self.canonical_memory_path,
            {
                "type": "leafos_canonical_memory",
                "schema_version": CANONICAL_MEMORY_SCHEMA_VERSION,
                "canonical_source": True,
                "updated_at": "",
                "entries": [],
            },
        )
        entries = payload.get("entries")
        if not isinstance(entries, list):
            payload["entries"] = []
        return payload

    def _save_memory(self, payload: dict[str, Any]) -> None:
        payload["type"] = "leafos_canonical_memory"
        payload["schema_version"] = CANONICAL_MEMORY_SCHEMA_VERSION
        payload["canonical_source"] = True
        payload["updated_at"] = _utc_now()
        _atomic_json(self.canonical_memory_path, payload)
        render_memory_markdown(self.canonical_markdown_path, payload)

    def _candidate_records(self, bundle_path: Path, bundle: dict[str, Any]) -> list[dict[str, Any]]:
        session_id = str(bundle.get("session_id") or bundle_path.stem)
        primary_character = str(bundle.get("primary_character", "") or "").strip()
        reviews = self._load_reviews(session_id).get("reviews", {})
        result: list[dict[str, Any]] = []
        for category in INTERPRETER_CATEGORIES:
            values = bundle.get(category, [])
            if not isinstance(values, list):
                continue
            for index, raw_candidate in enumerate(values):
                if not isinstance(raw_candidate, dict):
                    continue
                candidate = deepcopy(raw_candidate)
                candidate_id = _candidate_digest(session_id, category, index, candidate)
                review = reviews.get(candidate_id) if isinstance(reviews, dict) else None
                result.append(
                    {
                        "candidate_id": candidate_id,
                        "session_id": session_id,
                        "bundle_path": bundle_path,
                        "category": category,
                        "canonical_category": CANONICAL_CATEGORY_MAP[category],
                        "index": index,
                        "primary_character": primary_character,
                        "confidence": candidate.get("confidence"),
                        "perspective": candidate.get("perspective"),
                        "candidate": candidate,
                        "review": deepcopy(review) if isinstance(review, dict) else None,
                    }
                )
        return result

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for path in self._bundle_files():
            bundle = _read_json(path)
            if str(bundle.get("status", "pending_review")) != "pending_review":
                continue
            records = self._candidate_records(path, bundle)
            pending = [item for item in records if not item.get("review")]
            if not pending:
                continue
            sessions.append(
                {
                    "session_id": str(bundle.get("session_id") or path.stem),
                    "summary": str(bundle.get("summary", "") or ""),
                    "primary_character": str(bundle.get("primary_character", "") or ""),
                    "pending_count": len(pending),
                    "bundle_path": path,
                }
            )
        return sessions

    def list_candidates(self, session_id: str, *, include_reviewed: bool = False) -> list[dict[str, Any]]:
        bundle_path, bundle = self._bundle_by_session(session_id)
        records = self._candidate_records(bundle_path, bundle)
        if include_reviewed:
            return records
        return [item for item in records if not item.get("review")]

    def _find_candidate(self, candidate_id: str) -> dict[str, Any]:
        for path in self._bundle_files():
            bundle = _read_json(path)
            for record in self._candidate_records(path, bundle):
                if record["candidate_id"] == candidate_id:
                    return record
        raise ReviewerError(f"CANDIDATE_NOT_FOUND: {candidate_id}")

    def validate_evidence(self, candidate_id: str) -> dict[str, Any]:
        record = self._find_candidate(candidate_id)
        bundle_path = Path(record["bundle_path"])
        bundle = _read_json(bundle_path)
        session_id = record["session_id"]
        candidate = record["candidate"]
        session_path, session = self._processor_session(session_id)

        source_ids_raw = candidate.get("source_message_ids")
        if not isinstance(source_ids_raw, list) or not source_ids_raw:
            raise EvidenceError("CANDIDATE_WITHOUT_SOURCE_MESSAGE_IDS")
        try:
            source_ids = [int(value) for value in source_ids_raw]
        except (TypeError, ValueError) as error:
            raise EvidenceError("INVALID_SOURCE_MESSAGE_IDS") from error
        if len(set(source_ids)) != len(source_ids):
            raise EvidenceError("DUPLICATE_SOURCE_MESSAGE_IDS")

        bundle_message_ids = bundle.get("message_ids", [])
        session_message_ids = session.get("message_ids", [])
        try:
            bundle_ids = {int(value) for value in bundle_message_ids}
            session_ids = {int(value) for value in session_message_ids}
        except (TypeError, ValueError) as error:
            raise EvidenceError("INVALID_SESSION_MESSAGE_IDS") from error
        if not set(source_ids).issubset(bundle_ids):
            raise EvidenceError("SOURCE_ID_NOT_IN_INTERPRETATION_BUNDLE")
        if not set(source_ids).issubset(session_ids):
            raise EvidenceError("SOURCE_ID_NOT_IN_PROCESSOR_SESSION")

        bundle_sources = {str(value) for value in bundle.get("raw_sources", []) if str(value)}
        session_sources = {str(value) for value in session.get("raw_sources", []) if str(value)}
        if bundle_sources and not bundle_sources.issubset(session_sources):
            raise EvidenceError("BUNDLE_RAW_SOURCE_NOT_IN_PROCESSOR_SESSION")

        messages = session.get("messages", [])
        if not isinstance(messages, list):
            raise EvidenceError("PROCESSOR_MESSAGES_INVALID")
        by_id: dict[int, dict[str, Any]] = {}
        for item in messages:
            if not isinstance(item, dict):
                continue
            try:
                message_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            by_id[message_id] = item

        evidence: list[dict[str, Any]] = []
        raw_cache: dict[Path, dict[int, dict[str, Any]]] = {}
        raw_paths: list[Path] = []
        for source_id in source_ids:
            message = by_id.get(source_id)
            if message is None:
                raise EvidenceError(f"SOURCE_MESSAGE_MISSING: {source_id}")
            raw_reference = str(message.get("raw_source", "") or "").strip()
            if not raw_reference:
                raise EvidenceError(f"RAW_SOURCE_MISSING: {source_id}")
            if session_sources and raw_reference not in session_sources:
                raise EvidenceError(f"MESSAGE_RAW_SOURCE_NOT_IN_SESSION: {source_id}")
            raw_path = Path(raw_reference)
            if not raw_path.is_absolute():
                raw_path = self.vault_path / raw_path
            raw_path = raw_path.resolve()
            if not raw_path.exists() or not raw_path.is_file():
                raise EvidenceError(f"RAW_FILE_NOT_FOUND: {raw_reference}")
            if raw_path not in raw_cache:
                raw_cache[raw_path] = _raw_records(raw_path)
                raw_paths.append(raw_path)
            raw_record = raw_cache[raw_path].get(source_id)
            if raw_record is None:
                raise EvidenceError(f"SOURCE_ID_NOT_IN_RAW: {source_id}")
            if str(raw_record.get("timestamp", "")) != str(message.get("timestamp", "")):
                raise EvidenceError(f"RAW_TIMESTAMP_MISMATCH: {source_id}")
            if str(raw_record.get("channel", "")) != str(message.get("channel", "")):
                raise EvidenceError(f"RAW_CHANNEL_MISMATCH: {source_id}")
            raw_speaker = raw_record.get("speaker")
            message_speaker = message.get("speaker")
            if (raw_speaker or None) != (message_speaker or None):
                raise EvidenceError(f"RAW_SPEAKER_MISMATCH: {source_id}")
            if str(raw_record.get("text", "")) != str(message.get("text", "")):
                raise EvidenceError(f"RAW_TEXT_MISMATCH: {source_id}")
            evidence.append(
                {
                    "id": source_id,
                    "timestamp": message.get("timestamp"),
                    "speaker": message.get("speaker"),
                    "text": message.get("text"),
                    "raw_source": _relative_or_absolute(raw_path, self.vault_path),
                }
            )

        return {
            "record": record,
            "bundle_path": bundle_path,
            "bundle": bundle,
            "session_path": session_path,
            "session": session,
            "source_message_ids": source_ids,
            "evidence": evidence,
            "raw_paths": raw_paths,
        }

    def approve(self, candidate_id: str, *, edited_candidate: dict[str, Any] | None = None) -> dict[str, Any]:
        evidence_context = self.validate_evidence(candidate_id)
        record = evidence_context["record"]
        session_id = record["session_id"]
        reviews_payload = self._load_reviews(session_id)
        reviews = reviews_payload.setdefault("reviews", {})
        existing_review = reviews.get(candidate_id)
        memory_id = f"mem-{candidate_id}"

        if isinstance(existing_review, dict):
            status = str(existing_review.get("status", ""))
            if status == "rejected":
                raise ReviewerError("CANDIDATE_ALREADY_REJECTED")
            if status in {"approved", "edited_and_approved"}:
                memory = self._load_memory()
                for entry in memory.get("entries", []):
                    if isinstance(entry, dict) and entry.get("memory_id") == memory_id:
                        return deepcopy(entry)
                raise ReviewerError("APPROVED_REVIEW_WITHOUT_MEMORY_ENTRY")

        original = deepcopy(record["candidate"])
        approved = deepcopy(original) if edited_candidate is None else validate_edit(original, edited_candidate)
        edited = approved != original
        epistemic = epistemic_metadata(record, approved, evidence_context["evidence"])

        memory = self._load_memory()
        entries = memory.setdefault("entries", [])
        if not isinstance(entries, list):
            entries = []
            memory["entries"] = entries
        existing_entry = next(
            (item for item in entries if isinstance(item, dict) and item.get("memory_id") == memory_id),
            None,
        )
        reviewed_at = _utc_now()
        review_status = "edited_and_approved" if edited else "approved"
        source = {
            "interpretation_bundle": _relative_or_absolute(Path(record["bundle_path"]), self.vault_path),
            "processor_session": _relative_or_absolute(evidence_context["session_path"], self.vault_path),
            "raw_sources": sorted({_relative_or_absolute(path, self.vault_path) for path in evidence_context["raw_paths"]}),
            "source_message_ids": list(evidence_context["source_message_ids"]),
            "evidence": deepcopy(evidence_context["evidence"]),
        }
        entry = {
            "memory_id": memory_id,
            "category": record["canonical_category"],
            "origin_category": record["category"],
            "session_id": session_id,
            "primary_character": record.get("primary_character") or "",
            "interpreter_confidence": original.get("confidence"),
            "epistemic": epistemic,
            "content": deepcopy(approved),
            "source": source,
            "review_status": review_status,
            "reviewed_at": reviewed_at,
            "review": {
                "human_reviewed": True,
                "action": review_status,
                "original_candidate": original,
                "approved_candidate": deepcopy(approved),
            },
        }
        if existing_entry is None:
            entries.append(entry)
        else:
            existing_entry.clear()
            existing_entry.update(entry)
            entry = existing_entry
        self._save_memory(memory)

        reviews[candidate_id] = {
            "candidate_id": candidate_id,
            "category": record["category"],
            "status": review_status,
            "reviewed_at": reviewed_at,
            "memory_id": memory_id,
            "source_message_ids": list(evidence_context["source_message_ids"]),
            "original_candidate": original,
            "approved_candidate": deepcopy(approved),
        }
        self._save_reviews(session_id, reviews_payload)
        return deepcopy(entry)

    def reject(self, candidate_id: str, *, reason: str = "") -> dict[str, Any]:
        record = self._find_candidate(candidate_id)
        session_id = record["session_id"]
        reviews_payload = self._load_reviews(session_id)
        reviews = reviews_payload.setdefault("reviews", {})
        existing = reviews.get(candidate_id)
        if isinstance(existing, dict):
            return deepcopy(existing)

        evidence_valid = True
        evidence_error = ""
        source_message_ids: list[int] = []
        try:
            evidence_context = self.validate_evidence(candidate_id)
            source_message_ids = list(evidence_context["source_message_ids"])
        except EvidenceError as error:
            evidence_valid = False
            evidence_error = str(error)
            raw_ids = record["candidate"].get("source_message_ids", [])
            if isinstance(raw_ids, list):
                for value in raw_ids:
                    try:
                        message_id = int(value)
                    except (TypeError, ValueError):
                        continue
                    if message_id not in source_message_ids:
                        source_message_ids.append(message_id)

        reviewed_at = _utc_now()
        review = {
            "candidate_id": candidate_id,
            "category": record["category"],
            "status": "rejected",
            "reviewed_at": reviewed_at,
            "reason": str(reason or "").strip()[:4000],
            "source_message_ids": source_message_ids,
            "evidence_valid": evidence_valid,
            "evidence_error": evidence_error,
            "original_candidate": deepcopy(record["candidate"]),
        }
        reviews[candidate_id] = review
        self._save_reviews(session_id, reviews_payload)
        return deepcopy(review)

    def candidate_detail(self, candidate_id: str) -> dict[str, Any]:
        context = self.validate_evidence(candidate_id)
        record = context["record"]
        return {
            **{key: value for key, value in record.items() if key != "bundle_path"},
            "bundle_path": _relative_or_absolute(Path(record["bundle_path"]), self.vault_path),
            "processor_session": _relative_or_absolute(context["session_path"], self.vault_path),
            "evidence": context["evidence"],
        }
