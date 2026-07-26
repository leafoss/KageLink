from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pc_agent import leafos_interpreter as v3
from pc_agent import leafos_interpreter_v31 as v31
from pc_agent import leafos_interpreter_v32 as v32
from pc_agent.leafos_memory import LeafOSMemoryReviewer


class StaticProvider:
    model = "test-model"

    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls = 0

    def interpret(self, session, messages, truncated):
        self.calls += 1
        return self.result


def _write_session(
    vault: Path,
    session_id: str,
    messages: list[dict],
    *,
    primary_character: str = "Uchiha, Leafos",
) -> Path:
    path = vault / "80 - Processor" / "Sessions" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = [int(item["id"]) for item in messages]
    payload = {
        "session_id": session_id,
        "started_at": "2026-07-26T20:00:00+00:00",
        "ended_at": "2026-07-26T20:10:00+00:00",
        "primary_character": primary_character,
        "participants": [],
        "message_count": len(messages),
        "message_ids": ids,
        "raw_sources": ["RAW/IC/2026-07-26.md"],
        "messages": messages,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _base_result() -> dict:
    return {
        "summary": "",
        "events": [],
        "characters": [],
        "locations": [],
        "relationships": [],
        "facts": [],
        "leafos_memories": [],
    }


class LeafOSInterpreterV32Tests(unittest.TestCase):
    def test_v31_remains_available_as_working_baseline(self) -> None:
        self.assertEqual(v31.PROMPT_VERSION, "leafos-interpreter-v3.1")
        self.assertEqual(v32.PROMPT_VERSION, "leafos-interpreter-v3.2")
        self.assertTrue(issubclass(v32.OllamaInterpreterProvider, v31.OllamaInterpreterProvider))
        self.assertTrue(issubclass(v32.LeafOSInterpreter, v31.LeafOSInterpreter))

    def test_mechanical_anbu_candidates_are_hidden_but_preserved_for_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            messages = [
                {
                    "id": 13661,
                    "timestamp": "2026-07-26T20:00:00+00:00",
                    "channel": "ic",
                    "speaker": None,
                    "text": "(***Anbu** picks up Senbon*)",
                    "raw_source": "RAW/IC/2026-07-26.md",
                },
            ]
            for offset, text in enumerate(
                [
                    "(***Anbu** picks up Large Kunai*)",
                    "(***Anbu** drops Large Kunai*)",
                    "(***Anbu** picks up Large Kunai*)",
                    "(***Anbu** drops Large Kunai*)",
                    "(***Anbu** picks up Large Kunai*)",
                    "(***Anbu** drops Large Kunai*)",
                    "(***Anbu** picks up Large Kunai*)",
                    "(***Anbu** drops Large Kunai*)",
                    "(***Anbu** picks up Large Kunai*)",
                    "(***Anbu** drops Large Kunai*)",
                ],
                start=13700,
            ):
                messages.append(
                    {
                        "id": offset,
                        "timestamp": "2026-07-26T20:00:01+00:00",
                        "channel": "ic",
                        "speaker": None,
                        "text": text,
                        "raw_source": "RAW/IC/2026-07-26.md",
                    }
                )

            _write_session(vault, "2026-07-26_001", messages)
            result = _base_result()
            result["summary"] = "Anbu repeatedly picks up and drops objects."
            result["characters"] = [
                {
                    "name": "Anbu",
                    "observation": "Anbu was interacting with objects, specifically picking up and dropping a Large Kunai multiple times and picking up a Senbon once.",
                    "confidence": 1.0,
                    "source_message_ids": [13661, 13700, 13701, 13702, 13703, 13704, 13705],
                }
            ]
            result["events"] = [
                {
                    "title": "Anbu repeatedly picks up and drops Large Kunai",
                    "description": "Anbu repeatedly picked up and dropped a Large Kunai multiple times.",
                    "event_type": "object_interaction",
                    "confidence": 1.0,
                    "source_message_ids": [13700, 13701, 13702, 13703, 13704, 13705],
                },
                {
                    "title": "Anbu picks up Senbon",
                    "description": "Anbu picked up a Senbon.",
                    "event_type": "object_interaction",
                    "confidence": 1.0,
                    "source_message_ids": [13661],
                },
            ]

            run = v32.LeafOSInterpreter(vault, StaticProvider(result)).run_once()
            self.assertEqual(run, {"interpreted": 1, "skipped": 0, "failed": 0})

            output = vault / "70 - LeafOS Inbox" / "Interpretations" / "2026-07-26_001.json"
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["prompt_version"], v32.PROMPT_VERSION)
            self.assertEqual(payload["grounding_prompt_version"], v31.PROMPT_VERSION)
            self.assertEqual(payload["events"], [])
            self.assertEqual(payload["characters"], [])
            self.assertEqual(payload["salience"]["review_candidates"], 0)
            self.assertEqual(payload["salience"]["suppressed_candidates"], 3)

            decisions = [item["decision"] for item in payload["suppressed_candidates"]]
            self.assertEqual(decisions.count("invalid_category"), 1)
            self.assertEqual(decisions.count("low_salience"), 2)
            self.assertTrue(
                any(
                    "transient_character_observation" in item["signals"]
                    for item in payload["suppressed_candidates"]
                    if item["decision"] == "invalid_category"
                )
            )
            self.assertTrue(
                any(
                    item["candidate"].get("title") == "Anbu picks up Senbon"
                    for item in payload["suppressed_candidates"]
                )
            )

            reviewer = LeafOSMemoryReviewer(vault)
            self.assertEqual(reviewer.list_candidates("2026-07-26_001"), [])
            self.assertEqual(reviewer.list_sessions(), [])

    def test_meaningful_transfer_reaches_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            messages = [
                {
                    "id": 20001,
                    "timestamp": "2026-07-26T21:00:00+00:00",
                    "channel": "ic",
                    "speaker": "Kaede",
                    "text": "Kaede Says: Take this sealed scroll and deliver it to the Hokage.",
                    "raw_source": "RAW/IC/2026-07-26.md",
                },
                {
                    "id": 20002,
                    "timestamp": "2026-07-26T21:00:01+00:00",
                    "channel": "ic",
                    "speaker": None,
                    "text": "(***Kaede** gives Sealed Scroll to **Anbu***)",
                    "raw_source": "RAW/IC/2026-07-26.md",
                },
            ]
            _write_session(vault, "2026-07-26_002", messages)
            result = _base_result()
            result["events"] = [
                {
                    "title": "Kaede gives Anbu a Sealed Scroll",
                    "description": "Kaede gave Anbu a Sealed Scroll and instructed Anbu to deliver it to the Hokage.",
                    "event_type": "transfer",
                    "confidence": 1.0,
                    "source_message_ids": [20001, 20002],
                }
            ]

            v32.LeafOSInterpreter(vault, StaticProvider(result)).run_once()
            output = vault / "70 - LeafOS Inbox" / "Interpretations" / "2026-07-26_002.json"
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["events"]), 1)
            self.assertEqual(payload["events"][0]["title"], "Kaede gives Anbu a Sealed Scroll")
            self.assertGreaterEqual(payload["salience"]["review_candidates"], 1)
            self.assertEqual(payload["salience"]["suppressed_candidates"], 0)

    def test_durable_character_revelation_survives_category_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            messages = [
                {
                    "id": 21001,
                    "timestamp": "2026-07-26T21:10:00+00:00",
                    "channel": "ic",
                    "speaker": "Kaede",
                    "text": "Kaede Says: I am a medic.",
                    "raw_source": "RAW/IC/2026-07-26.md",
                }
            ]
            _write_session(vault, "2026-07-26_003", messages)
            result = _base_result()
            result["characters"] = [
                {
                    "name": "Kaede",
                    "observation": "Kaede is a medic.",
                    "confidence": 1.0,
                    "source_message_ids": [21001],
                }
            ]

            v32.LeafOSInterpreter(vault, StaticProvider(result)).run_once()
            output = vault / "70 - LeafOS Inbox" / "Interpretations" / "2026-07-26_003.json"
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["characters"]), 1)
            self.assertEqual(payload["characters"][0]["name"], "Kaede")

    def test_v31_checkpoint_is_not_reused_by_v32(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            messages = [
                {
                    "id": 22001,
                    "timestamp": "2026-07-26T21:20:00+00:00",
                    "channel": "ic",
                    "speaker": "Kaede",
                    "text": "Kaede Says: Hello.",
                    "raw_source": "RAW/IC/2026-07-26.md",
                }
            ]
            path = _write_session(vault, "2026-07-26_004", messages)
            session = json.loads(path.read_text(encoding="utf-8"))
            chunks = v3._chunk_messages(session, 9000, 2)
            fingerprint = v3._session_fingerprint(session, chunk_chars=9000, overlap_messages=2)

            checkpoint_path = vault / "80 - Interpreter" / "Checkpoints" / "2026-07-26_004.json"
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "type": "leafos_interpreter_checkpoint",
                        "schema_version": v3.CHECKPOINT_SCHEMA_VERSION,
                        "prompt_version": v31.PROMPT_VERSION,
                        "session_id": "2026-07-26_004",
                        "session_fingerprint": "old-v31-fingerprint",
                        "chunk_chars": 9000,
                        "chunk_overlap_messages": 2,
                        "total_chunks": len(chunks),
                        "chunks": {"0": {"status": "complete", "result": _base_result()}},
                    }
                ),
                encoding="utf-8",
            )

            interpreter = v32.LeafOSInterpreter(vault, StaticProvider(_base_result()))
            loaded = interpreter._load_checkpoint(
                session_id="2026-07-26_004",
                chunks=chunks,
                fingerprint=fingerprint,
            )
            self.assertEqual(loaded["prompt_version"], v32.PROMPT_VERSION)
            self.assertEqual(loaded["chunks"], {})


if __name__ == "__main__":
    unittest.main()
