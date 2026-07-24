from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pc_agent.leafos_interpreter import LeafOSInterpreter, _select_messages


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

    def test_second_run_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            write_session(vault)
            provider = FakeProvider(
                {
                    "summary": "Summary",
                    "events": [],
                    "characters": [],
                    "locations": [],
                    "relationships": [],
                    "facts": [],
                    "leafos_memories": [],
                }
            )
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

            provider = FakeProvider(
                {
                    "summary": "Recovered",
                    "events": [],
                    "characters": [],
                    "locations": [],
                    "relationships": [],
                    "facts": [],
                    "leafos_memories": [],
                }
            )
            second = LeafOSInterpreter(vault, provider).run_once()
            self.assertEqual(second["interpreted"], 1)

    def test_transcript_truncation_keeps_head_and_tail(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
