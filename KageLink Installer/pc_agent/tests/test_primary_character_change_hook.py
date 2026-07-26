from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from pc_agent.history import HistoryStore
from pc_agent.primary_character_api import (
    _finalize_before_character_change,
    set_character_change_hook,
)


class PrimaryCharacterChangeHookTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_character_change_hook(None)

    def test_async_hook_is_awaited_before_identity_change_path_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history = HistoryStore(Path(temp_dir) / "history.db")
            order: list[str] = []

            async def hook():
                order.append("finalize-start")
                await asyncio.sleep(0)
                order.append("finalize-end")
                return {"closed": True, "close_reason": "character_changed"}

            set_character_change_hook(hook)
            result = asyncio.run(_finalize_before_character_change(history))
            order.append("after")

            self.assertEqual(order, ["finalize-start", "finalize-end", "after"])
            self.assertTrue(result["closed"])
            self.assertEqual(result["close_reason"], "character_changed")


if __name__ == "__main__":
    unittest.main()
