from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pc_agent.leafos_interpreter import LeafOSInterpreter, _build_user_prompt


class RecordingProvider:
    model = "test-model"

    def __init__(self) -> None:
        self.session = None

    def interpret(self, session, messages, truncated):
        self.session = dict(session)
        return {
            "summary": "Summary",
            "events": [],
            "characters": [],
            "locations": [],
            "relationships": [],
            "facts": [],
            "leafos_memories": [],
        }


def _write_session(vault: Path) -> None:
    path = vault / "80 - Processor" / "Sessions" / "2026-07-24_001.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "session_id": "2026-07-24_001",
                "started_at": "2026-07-24T20:00:00+00:00",
                "ended_at": "2026-07-24T20:01:00+00:00",
                "participants": ["Matsunaya Hika", "Uzumaki, Urahara"],
                "message_ids": [101],
                "raw_sources": ["90 - KageAgent/Raw/IC/2026-07-24.md"],
                "messages": [
                    {
                        "id": 101,
                        "timestamp": "2026-07-24T20:00:00+00:00",
                        "channel": "ic",
                        "speaker": "Matsunaya Hika",
                        "text": "Matsunaya Hika Says: We should move.",
                        "raw_source": "90 - KageAgent/Raw/IC/2026-07-24.md",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class LeafOSPrimaryCharacterTests(unittest.TestCase):
    def test_prompt_exposes_primary_character(self) -> None:
        prompt = _build_user_prompt(
            {
                "session_id": "s1",
                "primary_character": "Matsunaya Hika",
                "participants": [],
            },
            [{"id": 1, "speaker": "Matsunaya Hika", "text": "Hello"}],
            False,
        )
        self.assertIn("PRIMARY_CHARACTER: Matsunaya Hika", prompt)

    def test_resolver_sets_character_before_interpretation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            _write_session(vault)
            provider = RecordingProvider()
            interpreter = LeafOSInterpreter(
                vault,
                provider,
                primary_character_resolver=lambda session: "Matsunaya Hika",
            )

            result = interpreter.run_once()

            self.assertEqual(result["interpreted"], 1)
            self.assertEqual(provider.session["primary_character"], "Matsunaya Hika")
            output = json.loads(
                (
                    vault
                    / "70 - LeafOS Inbox"
                    / "Interpretations"
                    / "2026-07-24_001.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(output["primary_character"], "Matsunaya Hika")

    def test_existing_session_character_wins_over_resolver(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "LeafOS-Vault"
            _write_session(vault)
            session_path = vault / "80 - Processor" / "Sessions" / "2026-07-24_001.json"
            payload = json.loads(session_path.read_text(encoding="utf-8"))
            payload["primary_character"] = "Uchiha, Leafos"
            session_path.write_text(json.dumps(payload), encoding="utf-8")
            provider = RecordingProvider()
            interpreter = LeafOSInterpreter(
                vault,
                provider,
                primary_character_resolver=lambda session: "Matsunaya Hika",
            )

            interpreter.run_once()

            self.assertEqual(provider.session["primary_character"], "Uchiha, Leafos")


if __name__ == "__main__":
    unittest.main()
