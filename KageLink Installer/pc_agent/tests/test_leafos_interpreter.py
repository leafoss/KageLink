from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pc_agent.leafos_interpreter import LeafOSInterpreter, _chunk_messages, _select_messages


class FakeProvider:
    model = "test-model"

    def __init__(self, result: dict | None = None, error: Exception | None = None) -> None:
        self.result = result or {}
        self.error = error
        self.calls = 0

    def interpret(self, session, messages, truncated):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class RecordingProvider:
    model = "test-model"

    def __init__(self, *, fail_on_call: int | None = None, duplicate_fact: bool = False) -> None:
        self.fail_on_call = fail_on_call
        self.duplicate_fact = duplicate_fact
        self.calls: list[list[int]] = []

    def interpret(self, session, messages, truncated):
        ids = [int(item["id"]) for item in messages]
        self.calls.append(ids)
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise RuntimeError("OLLAMA_TIMEOUT: 600s")

        result = valid_result(f"Chunk {session.get('_interpreter_chunk_index', 1)}")
        if self.duplicate_fact:
            result["facts"] = [
                {
                    "statement": "The same supported observation.",
                    "kind": "statement",
                    "confidence": 0.8,
                    "source_message_ids": [ids[0]],
                }
            ]
        return result


def valid_result(summary: str = "Summary") -> dict:
    return {
        "summary": summary,
        "events": [],
        "characters": [],
        "locations": [],
        "relationships": [],
        "facts": [],
        "leafos_memories": [],
    }


def write_session(vault: Path, *, session_id: str = "2026-07-24_001") -> Path:
    path = vault / "80 - Processor" / "Sessions" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "started_at": "2026-07-24T20:00:00+00:00",
        "ended_at": "2026-07-24T20:05:00+00:00",
        "participants": ["Uchiha, Leafos", "Uzumaki, Urahara"],
        "message_count": 3,
        "message_ids": [101, 102, 103],
        "raw_sources": ["90 - KageAgent/Raw/IC/2026-07-24.md"],
        "messages": [
            {
                "id": 101,
                "timestamp": "2026-07-24T20:00:00+00:00",
                "channel": "ic",
                "speaker": "Uchiha, Leafos",
                "text": "Uchiha, Leafos Says: We should move before nightfall.",
                "raw_source": "90 - KageAgent/Raw/IC/2026-07-24.md",
            },
            {
                "id": 102,
                "timestamp": "2026-07-24T20:01:00+00:00",
                "channel": "ic",
                "speaker": "Uzumaki, Urahara",
                "text": "Uzumaki, Urahara Says: Agreed.",
                "raw_source": "90 - KageAgent/Raw/IC/2026-07-24.md",
            },
            {
                "id": 103,
                "timestamp": "2026-07-24T20:05:00+00:00",
                "channel": "ic",
                "speaker": None,
                "text": "(*Leafos looks toward the gate.*)",
                "raw_source": "90 - KageAgent/Raw/IC/2026-07-24.md",
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_large_session(
    vault: Path,
    *,
    session_id: str = "2026-07-24_010",
    count: int = 10,
    text_chars: int = 1500,
) -> Path:
    path = vault / "80 - Processor" / "Sessions" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    messages = []
    ids = []
    for offset in range(count):
        message_id = 1000 + offset
        ids.append(message_id)
        messages.append(
            {
                "id": message_id,
                "timestamp": f"2026-07-24T20:{offset:02d}:00+00:00",
                "channel": "ic",
                "speaker": "Uchiha, Leafos" if offset % 2 == 0 else "Uzumaki, Urahara",
                "text": f"message-{offset}-" + ("x" * text_chars),
                "raw_source": "90 - KageAgent/Raw/IC/2026-07-24.md",
            }
        )
    payload = {
        "session_id": session_id,
        "started_at": "2026-07-24T20:00:00+00:00",
        "ended_at": "2026-07-24T21:00:00+00:00",
        "primary_character": "Uchiha, Leafos",
        "participants": ["Uchiha, Leafos", "Uzumaki, Urahara"],
        "message_count": len(messages),
        "message_ids": ids,
        "raw_sources": ["90 - KageAgent/Raw/IC/2026-07-24.md"],
        "messages": messages,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class LeafOSInterpreterTests(unittest.TestCase):
    def test_creates_pending_review_bundle_with_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            write_session(vault)
            provider = FakeProvider(
                {
                    "summary": "Leafos proposes moving before nightfall and Urahara agrees.",
                    "events": [
                        {
                            "title": "Decision to move",
                            "description": "Leafos proposes moving before nightfall; Urahara agrees.",
                            "event_type": "decision",
                            "confidence": 0.96,
                            "source_message_ids": [101, 102],
                        }
                    ],
                    "characters": [],
                    "locations": [],
                    "relationships": [],
                    "facts": [
                        {
                            "statement": "Leafos proposed moving before nightfall.",
                            "kind": "statement",
                            "confidence": 1.4,
                            "source_message_ids": [101],
                        },
                        {
                            "statement": "This unsupported candidate must be discarded.",
                            "kind": "inference",
                            "confidence": 0.5,
                            "source_message_ids": [9999],
                        },
                    ],
                    "leafos_memories": [
                        {
                            "memory": "Urahara agreed with the proposal to move.",
                            "perspective": "observed",
                            "confidence": 0.9,
                            "source_message_ids": [102],
                        }
                    ],
                }
            )

            result = LeafOSInterpreter(vault, provider).run_once()

            self.assertEqual(result, {"interpreted": 1, "skipped": 0, "failed": 0})
            output = vault / "70 - LeafOS Inbox" / "Interpretations" / "2026-07-24_001.json"
            self.assertTrue(output.exists())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pending_review")
            self.assertEqual(payload["session_id"], "2026-07-24_001")
            self.assertEqual(payload["events"][0]["source_message_ids"], [101, 102])
            self.assertEqual(payload["events"][0]["review_status"], "pending_review")
            self.assertEqual(payload["facts"][0]["confidence"], 1.0)
            self.assertEqual(len(payload["facts"]), 1)
            self.assertEqual(payload["leafos_memories"][0]["source_message_ids"], [102])
            self.assertEqual(payload["interpretation_mode"], "single")
            self.assertEqual(payload["chunk_count"], 1)
            self.assertFalse(payload["transcript_truncated"])

    def test_second_run_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            write_session(vault)
            provider = FakeProvider(valid_result())
            interpreter = LeafOSInterpreter(vault, provider)
            self.assertEqual(interpreter.run_once()["interpreted"], 1)
            second = interpreter.run_once()
            self.assertEqual(second["interpreted"], 0)
            self.assertEqual(second["skipped"], 1)
            self.assertEqual(provider.calls, 1)

    def test_provider_failure_does_not_mark_session_processed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            write_session(vault)
            failing = FakeProvider(error=RuntimeError("offline"))
            first = LeafOSInterpreter(vault, failing).run_once()
            self.assertEqual(first["failed"], 1)

            state_path = vault / "80 - Interpreter" / "interpreter_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertNotIn("2026-07-24_001", state["processed_sessions"])
            self.assertEqual(state["failed_sessions"]["2026-07-24_001"]["error"], "offline")

            provider = FakeProvider(valid_result("Recovered"))
            second = LeafOSInterpreter(vault, provider).run_once()
            self.assertEqual(second["interpreted"], 1)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertNotIn("2026-07-24_001", state["failed_sessions"])

    def test_failure_details_are_returned_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            write_session(vault)

            result = LeafOSInterpreter(
                vault,
                FakeProvider(error=RuntimeError("OLLAMA_TIMEOUT: 600s")),
            ).run_once(include_details=True)

            self.assertEqual(result["failed"], 1)
            self.assertEqual(result["failures"][0]["session_id"], "2026-07-24_001")
            self.assertEqual(result["failures"][0]["error"], "OLLAMA_TIMEOUT: 600s")
            self.assertEqual(result["failures"][0]["chunk_number"], 1)
            self.assertEqual(result["failures"][0]["total_chunks"], 1)

    def test_targeted_retry_ignores_other_failed_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            write_session(vault, session_id="2026-07-24_001")
            write_session(vault, session_id="2026-07-24_002")

            first = LeafOSInterpreter(
                vault,
                FakeProvider(error=RuntimeError("offline")),
            ).run_once(include_details=True)
            self.assertEqual(first["failed"], 2)

            recovered = LeafOSInterpreter(vault, FakeProvider(valid_result("Recovered")))
            result = recovered.run_once(
                session_ids=["2026-07-24_002"],
                include_details=True,
            )

            self.assertEqual(result["interpreted"], 1)
            self.assertEqual(result["failed"], 0)
            self.assertEqual(result["interpreted_sessions"], ["2026-07-24_002"])
            state = json.loads(
                (vault / "80 - Interpreter" / "interpreter_state.json").read_text(encoding="utf-8")
            )
            self.assertIn("2026-07-24_001", state["failed_sessions"])
            self.assertNotIn("2026-07-24_002", state["failed_sessions"])

    def test_missing_target_is_reported_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            result = LeafOSInterpreter(vault, FakeProvider(valid_result())).run_once(
                session_ids=["2026-07-24_999"],
                include_details=True,
            )
            self.assertEqual(result["failed"], 1)
            self.assertEqual(
                result["failures"][0]["error"],
                "PROCESSOR_SESSION_NOT_FOUND: 2026-07-24_999",
            )

    def test_transcript_truncation_keeps_head_and_tail_for_legacy_callers(self) -> None:
        session = {
            "messages": [
                {"id": index, "speaker": "A", "text": "x" * 1000}
                for index in range(1, 21)
            ]
        }
        selected, truncated = _select_messages(session, 5000)
        ids = [int(item["id"]) for item in selected]
        self.assertTrue(truncated)
        self.assertIn(1, ids)
        self.assertIn(20, ids)
        self.assertLess(len(ids), 20)

    def test_large_session_is_chunked_without_dropping_middle_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            session_path = write_large_session(vault, count=10, text_chars=1500)
            session = json.loads(session_path.read_text(encoding="utf-8"))
            expected_ids = set(session["message_ids"])
            provider = RecordingProvider()

            result = LeafOSInterpreter(
                vault,
                provider,
                max_transcript_chars=4000,
                chunk_overlap_messages=1,
            ).run_once()

            self.assertEqual(result["interpreted"], 1)
            self.assertGreater(len(provider.calls), 1)
            seen_ids = {message_id for call in provider.calls for message_id in call}
            self.assertEqual(seen_ids, expected_ids)
            self.assertIn(session["message_ids"][len(session["message_ids"]) // 2], seen_ids)

            output = vault / "70 - LeafOS Inbox" / "Interpretations" / "2026-07-24_010.json"
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["interpretation_mode"], "chunked")
            self.assertEqual(payload["chunk_count"], len(provider.calls))
            self.assertFalse(payload["transcript_truncated"])

    def test_failed_chunk_retry_reuses_completed_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            session_path = write_large_session(vault, count=9, text_chars=1500)
            session = json.loads(session_path.read_text(encoding="utf-8"))
            chunks = _chunk_messages(session, 4000, 1)
            self.assertGreaterEqual(len(chunks), 3)

            failing = RecordingProvider(fail_on_call=2)
            first = LeafOSInterpreter(
                vault,
                failing,
                max_transcript_chars=4000,
                chunk_overlap_messages=1,
            ).run_once(include_details=True)

            self.assertEqual(first["failed"], 1)
            self.assertEqual(first["failures"][0]["chunk_number"], 2)
            self.assertEqual(first["failures"][0]["completed_chunks"], 1)

            checkpoint = vault / "80 - Interpreter" / "Checkpoints" / "2026-07-24_010.json"
            self.assertTrue(checkpoint.exists())
            checkpoint_payload = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertEqual(len(checkpoint_payload["chunks"]), 1)

            recovered = RecordingProvider()
            second = LeafOSInterpreter(
                vault,
                recovered,
                max_transcript_chars=4000,
                chunk_overlap_messages=1,
            ).run_once(include_details=True)

            self.assertEqual(second["interpreted"], 1)
            self.assertEqual(second["failed"], 0)
            self.assertEqual(len(recovered.calls), len(chunks) - 1)
            self.assertFalse(checkpoint.exists())

    def test_overlap_duplicates_are_merged_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            write_large_session(vault, count=8, text_chars=1500)
            provider = RecordingProvider(duplicate_fact=True)

            LeafOSInterpreter(
                vault,
                provider,
                max_transcript_chars=4000,
                chunk_overlap_messages=1,
            ).run_once()

            output = vault / "70 - LeafOS Inbox" / "Interpretations" / "2026-07-24_010.json"
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["facts"]), 1)
            expected_sources = sorted({call[0] for call in provider.calls})
            self.assertEqual(payload["facts"][0]["source_message_ids"], expected_sources)

    def test_changed_session_invalidates_partial_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            session_path = write_large_session(vault, count=8, text_chars=1500)
            first_provider = RecordingProvider(fail_on_call=2)
            LeafOSInterpreter(
                vault,
                first_provider,
                max_transcript_chars=4000,
                chunk_overlap_messages=1,
            ).run_once()

            payload = json.loads(session_path.read_text(encoding="utf-8"))
            payload["messages"][0]["text"] += " changed"
            session_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            retry_provider = RecordingProvider()
            LeafOSInterpreter(
                vault,
                retry_provider,
                max_transcript_chars=4000,
                chunk_overlap_messages=1,
            ).run_once()

            self.assertGreaterEqual(len(retry_provider.calls), 1)
            self.assertIn(payload["messages"][0]["id"], retry_provider.calls[0])

    def test_progress_reports_chunk_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            write_large_session(vault, count=7, text_chars=1500)
            events: list[dict] = []

            LeafOSInterpreter(
                vault,
                RecordingProvider(),
                max_transcript_chars=4000,
                chunk_overlap_messages=1,
                progress_callback=events.append,
            ).run_once()

            names = [event["event"] for event in events]
            self.assertIn("session_start", names)
            self.assertIn("chunk_start", names)
            self.assertIn("chunk_complete", names)
            self.assertEqual(names[-1], "session_complete")


if __name__ == "__main__":
    unittest.main()
