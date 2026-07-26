from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import unified_entry
from pc_agent.leafos_interpreter_v31 import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    LeafOSInterpreter,
    _dedupe_summaries,
)


class DummyProvider:
    model = "test-model"


def session_with_message(
    text: str,
    *,
    speaker: str | None = "Anbu",
    primary_character: str = "Uchiha, Leafos",
) -> dict:
    return {
        "session_id": "2026-07-24_001",
        "started_at": "2026-07-24T08:12:14+00:00",
        "ended_at": "2026-07-24T08:12:15+00:00",
        "primary_character": primary_character,
        "participants": [speaker] if speaker else [],
        "message_count": 1,
        "message_ids": [7041],
        "raw_sources": ["RAW/IC/2026-07-24.md"],
        "messages": [
            {
                "id": 7041,
                "timestamp": "2026-07-24T08:12:14.343357+00:00",
                "channel": "ic",
                "speaker": speaker,
                "text": text,
                "raw_source": "RAW/IC/2026-07-24.md",
            }
        ],
    }


class LeafOSInterpreterV31Tests(unittest.TestCase):
    def test_prompt_contract_is_explicitly_evidence_only(self) -> None:
        self.assertEqual(PROMPT_VERSION, "leafos-interpreter-v3.1")
        self.assertIn("If the transcript only says that X did Y, report only that X did Y", SYSTEM_PROMPT)
        self.assertIn("Do NOT infer why an action happened", SYSTEM_PROMPT)
        self.assertIn("mission preparation", SYSTEM_PROMPT)
        self.assertIn("Do NOT explain what an item", SYSTEM_PROMPT)
        self.assertIn('"Anbu"', SYSTEM_PROMPT)
        self.assertIn("does NOT prove", SYSTEM_PROMPT)

    def test_senbon_case_removes_unsupported_purpose_and_external_definition(self) -> None:
        session = session_with_message("(***Anbu** picks up Senbon*)")
        raw = {
            "summary": (
                "Anbu repeatedly picks up Senbon, likely as part of a training exercise "
                "or mission preparation."
            ),
            "events": [
                {
                    "title": "Anbu Picking Up Senbon",
                    "description": (
                        "Anbu repeatedly picks up Senbon, likely as part of a training exercise "
                        "or mission preparation."
                    ),
                    "event_type": "ACTION",
                    "confidence": 1.0,
                    "source_message_ids": [7041],
                }
            ],
            "characters": [
                {
                    "name": "Uchiha, Leafos",
                    "observation": "Leafos is training with Senbon.",
                    "confidence": 0.9,
                    "source_message_ids": [7041],
                }
            ],
            "locations": [],
            "relationships": [],
            "facts": [
                {
                    "statement": "Senbon are weapons used in combat.",
                    "kind": "statement",
                    "confidence": 0.9,
                    "source_message_ids": [7041],
                }
            ],
            "leafos_memories": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            interpreter = LeafOSInterpreter(Path(temp_dir), DummyProvider())
            result = interpreter._normalize_result(session, raw, {7041}, truncated=False)

        self.assertEqual(result["prompt_version"], "leafos-interpreter-v3.1")
        self.assertEqual(result["summary"], "Anbu repeatedly picks up Senbon.")
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["title"], "Anbu Picking Up Senbon")
        self.assertEqual(result["events"][0]["description"], "Anbu repeatedly picks up Senbon.")
        self.assertEqual(result["events"][0]["source_message_ids"], [7041])
        self.assertEqual(result["characters"], [])
        self.assertEqual(result["facts"], [])

    def test_explicit_training_is_preserved_when_evidence_says_training(self) -> None:
        session = session_with_message("Anbu Says: I am training with Senbon.")
        raw = {
            "summary": "Anbu says he is training with Senbon.",
            "events": [
                {
                    "title": "Anbu training with Senbon",
                    "description": "Anbu says he is training with Senbon.",
                    "event_type": "statement",
                    "confidence": 1.0,
                    "source_message_ids": [7041],
                }
            ],
            "characters": [],
            "locations": [],
            "relationships": [],
            "facts": [],
            "leafos_memories": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            interpreter = LeafOSInterpreter(Path(temp_dir), DummyProvider())
            result = interpreter._normalize_result(session, raw, {7041}, truncated=False)

        self.assertEqual(result["summary"], "Anbu says he is training with Senbon.")
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["title"], "Anbu training with Senbon")

    def test_near_duplicate_chunk_summaries_collapse_but_distinct_scene_remains(self) -> None:
        summaries = [
            (
                "The transcript chunk contains a series of repeated actions where an unknown character, "
                "identified as Anbu, repeatedly picks up Senbon. These actions occur in quick succession."
            ),
            (
                "The transcript chunk contains a series of repeated actions where an unknown character "
                "(labeled as 'Anbu') repeatedly picks up 'Senbon'. There is no dialogue, only the repeated action."
            ),
            (
                "The transcript chunk contains a series of repeated actions where an Anbu agent is picking up "
                "senbon. These actions are logged in quick succession, suggesting a possible training exercise "
                "or preparation for a mission."
            ),
            (
                "The transcript describes a series of actions involving an Anbu and multiple Otogakure shinobi. "
                "The Anbu picks up several items while the other shinobi act separately."
            ),
        ]

        merged = _dedupe_summaries(summaries)

        self.assertEqual(len(merged), 2)
        self.assertIn("repeatedly picks up", merged[0].lower())
        self.assertNotIn("training", merged[0].lower())
        self.assertNotIn("mission", merged[0].lower())
        self.assertIn("otogakure", merged[1].lower())

    def test_v31_checkpoint_does_not_reuse_v3_prompt_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            interpreter = LeafOSInterpreter(vault, DummyProvider())
            checkpoint_path = vault / "80 - Interpreter" / "Checkpoints" / "2026-07-24_001.json"
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "type": "leafos_interpreter_checkpoint",
                        "schema_version": 1,
                        "prompt_version": "leafos-interpreter-v3",
                        "session_id": "2026-07-24_001",
                        "session_fingerprint": "old",
                        "chunk_chars": interpreter.max_transcript_chars,
                        "chunk_overlap_messages": interpreter.chunk_overlap_messages,
                        "total_chunks": 1,
                        "chunks": {"0": {"status": "complete"}},
                    }
                ),
                encoding="utf-8",
            )

            checkpoint = interpreter._load_checkpoint(
                session_id="2026-07-24_001",
                chunks=[[{"id": 7041}]],
                fingerprint="base-fingerprint",
            )

        self.assertEqual(checkpoint["prompt_version"], "leafos-interpreter-v3.1")
        self.assertEqual(checkpoint["chunks"], {})

    def test_packaged_unified_entry_routes_all_launcher_interpreter_globals_to_v31(self) -> None:
        self.assertIs(unified_entry.launcher.LeafOSInterpreter, LeafOSInterpreter)
        self.assertIs(unified_entry.LeafOSInterpreter, LeafOSInterpreter)
        self.assertEqual(LeafOSInterpreter.__module__, "pc_agent.leafos_interpreter_v31")


if __name__ == "__main__":
    unittest.main()
