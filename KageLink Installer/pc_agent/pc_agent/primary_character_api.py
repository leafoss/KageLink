from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pc_agent.config import load_config
from pc_agent.history import HistoryStore
from pc_agent.leafos import LeafOSRawExporter
from pc_agent.leafos_lifecycle import LifecycleLeafOSProcessor
from pc_agent.primary_character import (
    get_primary_character,
    normalize_character_name,
    resolve_primary_character,
    saved_characters,
    set_primary_character,
)
from pc_agent.security import TokenSecurity


class PrimaryCharacterRequest(BaseModel):
    name: str = Field(default="", max_length=160)


CharacterChangeHook = Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]]
_character_change_before_hook: CharacterChangeHook | None = None
_character_change_after_hook: CharacterChangeHook | None = None


def set_character_change_hook(
    before_hook: CharacterChangeHook | None,
    after_hook: CharacterChangeHook | None = None,
) -> None:
    """Install runtime hooks around an authoritative identity transition.

    The unified desktop pauses the chat monitor and closes the old session in the
    before-hook, keeps the monitor paused while the new character is committed,
    and resumes capture only in the after-hook. Legacy/source-only uses retain the
    deterministic local fallback.
    """

    global _character_change_before_hook, _character_change_after_hook
    _character_change_before_hook = before_hook
    _character_change_after_hook = after_hook


def _flush_and_close_leafos_session(history: HistoryStore) -> dict[str, Any]:
    """Fallback finalizer for runtimes without the unified async hook."""

    config = load_config()
    if (
        not config.leafos_enabled
        or not config.leafos_export_ic
        or config.leafos_vault_path is None
        or config.leafos_raw_output_path is None
    ):
        return {"closed": False, "session_id": None, "close_reason": "character_changed"}

    exporter = LeafOSRawExporter(
        config.leafos_raw_output_path,
        export_ic=config.leafos_export_ic,
        export_ooc=config.leafos_export_ooc,
    )
    exporter.sync(history)

    processor = LifecycleLeafOSProcessor(
        config.leafos_vault_path,
        config.leafos_raw_output_path,
        session_idle_seconds=config.leafos_session_idle_seconds,
        primary_character_provider=lambda: get_primary_character(history),
        primary_character_resolver=lambda session: resolve_primary_character(
            history,
            session.get("started_at"),
        ),
        require_primary_character=False,
    )
    return processor.finalize_open_session(
        "character_changed",
        closed_cleanly=True,
        consume_pending=True,
    )


async def _run_hook(hook: CharacterChangeHook | None) -> dict[str, Any]:
    if hook is None:
        return {}
    result = hook()
    if inspect.isawaitable(result):
        result = await result
    return dict(result or {})


async def _finalize_before_character_change(history: HistoryStore) -> dict[str, Any]:
    if _character_change_before_hook is None:
        return _flush_and_close_leafos_session(history)
    return await _run_hook(_character_change_before_hook)


async def _resume_after_character_change() -> dict[str, Any]:
    return await _run_hook(_character_change_after_hook)


def create_primary_character_router(
    history: HistoryStore,
    security: TokenSecurity,
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/primary-character",
        dependencies=[Depends(security.require_authorization)],
    )
    async def get_primary_character_setting() -> dict:
        return {
            "primary_character": get_primary_character(history),
            "saved_characters": saved_characters(history),
        }

    @router.post(
        "/api/primary-character",
        dependencies=[Depends(security.require_authorization)],
    )
    async def set_primary_character_setting(
        request: PrimaryCharacterRequest,
    ) -> dict:
        try:
            name = normalize_character_name(request.name)
            current = get_primary_character(history)
            close_result = None
            after_result = None
            if name != current:
                # The old identity remains authoritative until its session has
                # been fully flushed and closed. Capture stays paused until after
                # the new identity is committed below.
                try:
                    close_result = await _finalize_before_character_change(history)
                except Exception:
                    # Finalization failed before the identity changed. Restore
                    # capture so a failed transition cannot leave KageLink deaf.
                    await _resume_after_character_change()
                    raise

                try:
                    result = set_primary_character(history, name)
                finally:
                    # Once the old session is closed, capture must resume even if
                    # committing the new character unexpectedly fails.
                    after_result = await _resume_after_character_change()
            else:
                result = set_primary_character(history, name)
            if close_result is not None:
                result["previous_session"] = close_result
            if after_result:
                result["capture_resume"] = after_result
            return result
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return router
