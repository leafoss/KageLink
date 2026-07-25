from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pc_agent.config import load_config
from pc_agent.history import HistoryStore
from pc_agent.leafos import LeafOSProcessor
from pc_agent.primary_character import (
    get_primary_character,
    normalize_character_name,
    saved_characters,
    set_primary_character,
)
from pc_agent.security import TokenSecurity


class PrimaryCharacterRequest(BaseModel):
    name: str = Field(default="", max_length=160)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _flush_and_close_leafos_session() -> None:
    """Keep two configured player characters out of the same Processor session."""

    config = load_config()
    if (
        not config.leafos_enabled
        or not config.leafos_export_ic
        or config.leafos_vault_path is None
        or config.leafos_raw_output_path is None
    ):
        return

    processor = LeafOSProcessor(
        config.leafos_vault_path,
        config.leafos_raw_output_path,
        session_idle_seconds=config.leafos_session_idle_seconds,
    )
    now = datetime.now(timezone.utc)

    # First consume RAW records that were already captured under the old
    # character. Then close the resulting open session before the new character
    # becomes authoritative.
    processor.run_once(now=now)

    paths = processor._paths()
    state = processor._load_json(
        paths["state"],
        {
            "last_processed_id": 0,
            "last_run": "",
            "raw_source": "",
            "open_session": None,
            "session_counters": {},
        },
    )
    session = state.get("open_session")
    if not isinstance(session, dict) or not session.get("messages"):
        return

    processor._close_session(paths, session)
    state["open_session"] = None
    state["last_run"] = now.isoformat()
    _atomic_json(paths["state"], state)


def create_primary_character_router(
    history: HistoryStore,
    security: TokenSecurity,
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/primary-character",
        dependencies=[Depends(security.require_authorization)],
    )
    async def get_primary_character_setting() -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        try:
            name = normalize_character_name(request.name)
            if name != get_primary_character(history):
                _flush_and_close_leafos_session()
            return set_primary_character(history, name)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return router
