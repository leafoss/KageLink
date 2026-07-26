from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from pc_agent.history import HistoryStore
from pc_agent.primary_character import get_primary_character, set_primary_character
from pc_agent.primary_character_api import (
    PrimaryCharacterRequest,
    _finalize_before_character_change,
    _resume_after_character_change,
    create_primary_character_router,
    set_character_change_hook,
)
from pc_agent.security import TokenSecurity


class PrimaryCharacterChangeHookTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_character_change_hook(None, None)

    def _post_endpoint(self, history: HistoryStore):
        router = create_primary_character_router(history, TokenSecurity("x" * 32))
        for route in router.routes:
            if getattr(route, "path", None) == "/api/primary-character" and "POST" in getattr(route, "methods", set()):
                return route.endpoint
        self.fail("POST /api/primary-character route not found")

    def test_before_and_after_hooks_bracket_identity_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history = HistoryStore(Path(temp_dir) / "history.db")
            set_primary_character(history, "Uchiha, Leafos")
            order: list[str] = []

            async def before_hook():
                order.append(f"before:{get_primary_character(history)}")
                await asyncio.sleep(0)
                return {"closed": True, "close_reason": "character_changed"}

            async def after_hook():
                order.append(f"after:{get_primary_character(history)}")
                return {"resumed": True}

            set_character_change_hook(before_hook, after_hook)
            endpoint = self._post_endpoint(history)
            result = asyncio.run(endpoint(PrimaryCharacterRequest(name="Matsunaya, Raika")))

            self.assertEqual(
                order,
                ["before:Uchiha, Leafos", "after:Matsunaya, Raika"],
            )
            self.assertEqual(get_primary_character(history), "Matsunaya, Raika")
            self.assertEqual(result["primary_character"], "Matsunaya, Raika")
            self.assertTrue(result["previous_session"]["closed"])
            self.assertTrue(result["capture_resume"]["resumed"])

    def test_capture_resumes_when_before_hook_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history = HistoryStore(Path(temp_dir) / "history.db")
            set_primary_character(history, "Uchiha, Leafos")
            order: list[str] = []

            async def before_hook():
                order.append("before-failed")
                raise RuntimeError("finalize failed")

            async def after_hook():
                order.append("capture-resumed")
                return {"resumed": True}

            set_character_change_hook(before_hook, after_hook)
            endpoint = self._post_endpoint(history)

            with self.assertRaisesRegex(RuntimeError, "finalize failed"):
                asyncio.run(endpoint(PrimaryCharacterRequest(name="Matsunaya, Raika")))

            self.assertEqual(order, ["before-failed", "capture-resumed"])
            self.assertEqual(get_primary_character(history), "Uchiha, Leafos")

    def test_hook_helpers_support_async_runtime_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history = HistoryStore(Path(temp_dir) / "history.db")
            order: list[str] = []

            async def before_hook():
                order.append("paused")
                return {"closed": True}

            async def after_hook():
                order.append("resumed")
                return {"resumed": True}

            set_character_change_hook(before_hook, after_hook)

            async def scenario():
                before = await _finalize_before_character_change(history)
                after = await _resume_after_character_change()
                return before, after

            before, after = asyncio.run(scenario())
            self.assertEqual(order, ["paused", "resumed"])
            self.assertTrue(before["closed"])
            self.assertTrue(after["resumed"])


if __name__ == "__main__":
    unittest.main()
