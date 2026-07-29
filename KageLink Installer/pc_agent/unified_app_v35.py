from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import unified_app as base
from pc_agent.dojo_api import create_dojo_router
from pc_agent.kage_pilot import DojoTrainingService


APP_VERSION = "3.5.0"
dojo_service = DojoTrainingService()

base.legacy.APP_VERSION = APP_VERSION
base.app.version = APP_VERSION

if not bool(getattr(base.app.state, "dojo_v35_installed", False)):
    base.app.include_router(
        create_dojo_router(
            dojo_service,
            base.legacy.security,
            base.legacy.game_runtime,
        )
    )
    base.app.state.dojo_v35_installed = True

_original_lifespan = base.app.router.lifespan_context


@asynccontextmanager
async def dojo_lifespan(fastapi_app):
    async with _original_lifespan(fastapi_app):
        try:
            yield
        finally:
            if dojo_service.is_running:
                await asyncio.to_thread(dojo_service.stop, timeout=8.0)
            await asyncio.to_thread(base.legacy.game_runtime.release_all)


base.app.router.lifespan_context = dojo_lifespan

app = base.app
runtime_status = base.runtime_status

__all__ = ["APP_VERSION", "app", "dojo_service", "runtime_status"]
