from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from pc_agent.history import HistoryStore
from pc_agent.primary_character_api import (
    _finalize_before_character_change,
    _resume_after_character_change,
    set_character_change_hook,
)


class PrimaryCharacterChangeHookTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_character_change_hook(None, None)

    def test_before_and_after_hooks_bracket_identity_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history = HistoryStore(Path(temp_dir) / "history.db")
            order: list[str] = []

            async def before_hook():
                order.append("capture-paused")
                await asyncio.sleep(0)
                order.append("old-session-closed")
                return {"closed": True, "close_reason": "character_changed"}

            async def after_hook():
                order.append("capture-resumed")
                return {"resumed": True}

            set_character_change_hook(before_hook, after_hook)

            async def scenario():
                before = await _finalize_before_character_change(history)
                order.append("new-character-committed")
                after = await _resume_after_character_change()
                return before, after

            before, after = asyncio.run(scenario())

            self.assertEqual(
                order,
                [
                    "capture-paused",
                    "old-session-closed",
                    "new-character-committed",
                    "capture-resumed",
                ],
            )
            self.assertTrue(before["closed"])
            self.assertEqual(before["close_reason"], "character_changed")
            self.assertTrue(after["resumed"])


if __name__ == "__main__":
    unittest.main()
