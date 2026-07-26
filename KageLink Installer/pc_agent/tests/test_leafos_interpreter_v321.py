from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pc_agent import leafos_interpreter as v3
from pc_agent import leafos_interpreter_v31 as v31
from pc_agent import leafos_interpreter_v32 as v32
from pc_agent import leafos_interpreter_v321 as v321
from pc_agent.leafos_memory import LeafOSMemoryReviewer


class StaticProvider:
    model = "test-model"

    def __init__(self, result: dict) -> None:
        self.result = result

    def interpret(self, session, messages, truncated):
        return self.result


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


def _write_session(vault: Path, session_id: str, messages: list[dict]) -> Path:
    path = vault / "80 - Processor" / "Sessions" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "started_at": "2026-07-26T22:10:00+00:00",
        "ended_at": "2026-07-26T22:11:00+00:00",
        "primary_character": "Uchiha, Leafos",
        "participants": ["Anbu"],
        "message_count": len(messages),
        "message_ids": [int(item["id"]) for item in messages],
        "raw_sources": ["RAW/IC/2026-07-26.md"],
        "messages": messages,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _message(message_id: int, text: str, *, speaker: str | None = None) -> dict:
    return {
        "id": message_id,
        "timestamp": f"2026-07-26T22:10:{message_id % 60:02d}+00:00",
        "channel": "ic",
        "speaker": speaker,
        "text": text,
        "raw_source": "RAW/IC/2026-07-26.md",
    }


class LeafOSInterpreterV321Tests(unittest.TestCase):
    def test_previous_working_layers_remain_available(self) -> None:
        self.assertEqual(v31.PROMPT_VERSION, "leafos-interpreter-v3.1")
        self.assertEqual(v32.PROMPT_VERSION, "leafos-interpreter-v3.2")
        self.assertEqual(v321.PROMPT_VERSION, "leafos-interpreter-v3.2.1")
        self.assertTrue(issubclass(v321.OllamaInterpreterProvider, v32.OllamaInterpreterProvider))
        self.assertTrue(issubclass(v321.LeafOSInterpreter, v32.LeafOSInterpreter))
        self.assertTrue(issubclass(v321.LeafOSInterpreter, v31.LeafOSInterpreter))

    def test_chakra_paper_results_reach_reviewer_even_when_model_returns_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            messages = [
                _message(30001, "(***Anbu** drops Pick Axe*)"),
                _message(30002, "(***Anbu** applies Chakra to the Chakra Paper*)"),
                _message(30003, "(***Anbu** Your primary Element is: Fire*)"),
                _message(30004, "(***Anbu** Your secondary Element is: Earth*)"),
                _message(30005, "(***Anbu** drops Large Kunai*)"),
                _message(30006, "(***Anbu** picks up Large Kunai*)"),
            ]
            _write_session(vault, "2026-07-26_010", messages)

            run = v321.LeafOSInterpreter(vault, StaticProvider(_base_result())).run_once()
            self.assertEqual(run, {"interpreted": 1, "skipped": 0, "failed": 0})

            output = vault / "70 - LeafOS Inbox" / "Interpretations" / "2026-07-26_010.json"
            payload = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(payload["prompt_version"], v321.PROMPT_VERSION)
            self.assertEqual(payload["grounding_prompt_version"], v31.PROMPT_VERSION)
            self.assertEqual(payload["salience_base_version"], v32.PROMPT_VERSION)
            self.assertEqual(payload["events"], [])
            self.assertEqual(payload["characters"], [])
            self.assertEqual(len(payload["facts"]), 2)

            statements = [item["statement"] for item in payload["facts"]]
            self.assertIn("The system reported the primary Element as Fire.", statements)
            self.assertIn("The system reported the secondary Element as Earth.", statements)

            by_statement = {item["statement"]: item for item in payload["facts"]}
            self.assertEqual(
                by_statement["The system reported the primary Element as Fire."]["source_message_ids"],
                [30003],
            )
            self.assertEqual(
                by_statement["The system reported the secondary Element as Earth."]["source_message_ids"],
                [30004],
            )
            self.assertEqual(payload["salience"]["review_candidates"], 2)
            self.assertEqual(payload["durable_system_revelations"]["detected"], 2)
            self.assertEqual(payload["durable_system_revelations"]["promoted"], 2)
            self.assertTrue(payload["durable_system_revelations"]["wrapped_log_syntax_supported"])
            self.assertEqual(
                payload["durable_system_revelations"]["identity_attribution"],
                "not_inferred",
            )

            reviewer = LeafOSMemoryReviewer(vault)
            candidates = reviewer.list_candidates("2026-07-26_010")
            self.assertEqual(len(candidates), 2)
            self.assertTrue(all(item["category"] == "facts" for item in candidates))

    def test_real_validation_log_replaces_model_events_with_neutral_system_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            messages = [
                _message(13861, "(***Anbu** drops Chakra Paper*)"),
                _message(13862, "(***Anbu** picks up Chakra Paper*)"),
                _message(13863, "(***Anbu** Your primary Element is: Fire*)"),
                _message(13864, "(***Anbu** Your secondary Element is: Earth*)"),
            ]
            _write_session(vault, "2026-07-26_011", messages)

            model_result = _base_result()
            model_result["events"] = [
                {
                    "title": "Revealing Primary Element",
                    "description": "Anbu revealed the primary element as Fire.",
                    "event_type": "element_reveal",
                    "confidence": 1.0,
                    "source_message_ids": [13863],
                },
                {
                    "title": "Revealing Secondary Element",
                    "description": "Anbu revealed the secondary element as Earth.",
                    "event_type": "element_reveal",
                    "confidence": 1.0,
                    "source_message_ids": [13864],
                },
            ]

            v321.LeafOSInterpreter(vault, StaticProvider(model_result)).run_once()
            output = vault / "70 - LeafOS Inbox" / "Interpretations" / "2026-07-26_011.json"
            payload = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(payload["events"], [])
            self.assertEqual(len(payload["facts"]), 2)
            self.assertEqual(
                {item["statement"] for item in payload["facts"]},
                {
                    "The system reported the primary Element as Fire.",
                    "The system reported the secondary Element as Earth.",
                },
            )
            self.assertEqual(
                {tuple(item["source_message_ids"]) for item in payload["facts"]},
                {(13863,), (13864,)},
            )
            self.assertEqual(payload["durable_system_revelations"]["detected"], 2)
            self.assertEqual(payload["durable_system_revelations"]["promoted"], 2)
            self.assertEqual(payload["durable_system_revelations"]["replaced_model_candidates"], 2)
            self.assertEqual(payload["durable_system_revelations"]["identity_attribution"], "not_inferred")

            replacements = [
                item
                for item in payload["suppressed_candidates"]
                if item.get("decision") == "replaced_by_durable_system_revelation"
            ]
            self.assertEqual(len(replacements), 2)
            self.assertTrue(all(item.get("category") == "events" for item in replacements))

            reviewer = LeafOSMemoryReviewer(vault)
            candidates = reviewer.list_candidates("2026-07-26_011")
            self.assertEqual(len(candidates), 2)
            self.assertTrue(all(item["category"] == "facts" for item in candidates))
            self.assertTrue(all("Anbu" not in item["candidate"]["statement"] for item in candidates))
            self.assertTrue(all("Leafos" not in item["candidate"]["statement"] for item in candidates))

    def test_system_revelation_never_binds_anbu_to_primary_character(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            _write_session(
                vault,
                "2026-07-26_012",
                [
                    _message(30101, "(***Anbu** applies Chakra to the Chakra Paper*)"),
                    _message(30102, "(***Anbu** Your primary Element is: Fire*)"),
                ],
            )

            v321.LeafOSInterpreter(vault, StaticProvider(_base_result())).run_once()
            output = vault / "70 - LeafOS Inbox" / "Interpretations" / "2026-07-26_012.json"
            payload = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(len(payload["facts"]), 1)
            statement = payload["facts"][0]["statement"]
            self.assertNotIn("Leafos", statement)
            self.assertNotIn("Anbu", statement)
            self.assertEqual(statement, "The system reported the primary Element as Fire.")

    def test_model_fact_suppressed_by_v32_is_promoted_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            _write_session(
                vault,
                "2026-07-26_013",
                [_message(30201, "(***Anbu** Your primary Element is: Fire*)")],
            )
            model_result = _base_result()
            model_result["facts"] = [
                {
                    "statement": "The primary Element is Fire.",
                    "kind": "statement",
                    "confidence": 1.0,
                    "source_message_ids": [30201],
                }
            ]

            v321.LeafOSInterpreter(vault, StaticProvider(model_result)).run_once()
            output = vault / "70 - LeafOS Inbox" / "Interpretations" / "2026-07-26_013.json"
            payload = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(len(payload["facts"]), 1)
            self.assertEqual(
                payload["facts"][0]["statement"],
                "The system reported the primary Element as Fire.",
            )
            self.assertEqual(payload["salience"]["review_candidates"], 1)

    def test_v32_checkpoint_is_not_reused_by_v321(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            session_path = _write_session(
                vault,
                "2026-07-26_014",
                [_message(30301, "(***Anbu** Your primary Element is: Fire*)")],
            )
            session = json.loads(session_path.read_text(encoding="utf-8"))
            chunks = v3._chunk_messages(session, 9000, 2)
            fingerprint = v3._session_fingerprint(session, chunk_chars=9000, overlap_messages=2)

            checkpoint_path = vault / "80 - Interpreter" / "Checkpoints" / "2026-07-26_014.json"
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "type": "leafos_interpreter_checkpoint",
                        "schema_version": v3.CHECKPOINT_SCHEMA_VERSION,
                        "prompt_version": v32.PROMPT_VERSION,
                        "session_id": "2026-07-26_014",
                        "session_fingerprint": "old-v32-fingerprint",
                        "chunk_chars": 9000,
                        "chunk_overlap_messages": 2,
                        "total_chunks": len(chunks),
                        "chunks": {"0": {"status": "complete", "result": _base_result()}},
                    }
                ),
                encoding="utf-8",
            )

            interpreter = v321.LeafOSInterpreter(vault, StaticProvider(_base_result()))
            loaded = interpreter._load_checkpoint(
                session_id="2026-07-26_014",
                chunks=chunks,
                fingerprint=fingerprint,
            )
            self.assertEqual(loaded["prompt_version"], v321.PROMPT_VERSION)
            self.assertEqual(loaded["chunks"], {})


if __name__ == "__main__":
    unittest.main()
