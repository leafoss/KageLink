from __future__ import annotations

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


def _flush_and_close_leafos_session(history: HistoryStore) -> dict:
    """Flush RAW and close the current session before changing characters.

    This keeps two configured player characters out of the same Processor session
    and preserves a deterministic close reason for audit/recovery.
    """

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
            if name != current:
                close_result = _flush_and_close_leafos_session(history)
            result = set_primary_character(history, name)
            if close_result is not None:
                result["previous_session"] = close_result
            return result
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return router
