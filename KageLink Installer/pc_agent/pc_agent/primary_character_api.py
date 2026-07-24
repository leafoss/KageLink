from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pc_agent.history import HistoryStore
from pc_agent.primary_character import (
    get_primary_character,
    saved_characters,
    set_primary_character,
)
from pc_agent.security import TokenSecurity


class PrimaryCharacterRequest(BaseModel):
    name: str = Field(default="", max_length=160)


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
            return set_primary_character(history, request.name)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return router
