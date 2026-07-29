from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import unified_app as base
from pc_agent.dojo_api import create_dojo_router
from pc_agent.kage_pilot import DojoTrainingService


APP_VERSION = "3.5.0"


def ensure_dojo_integration() -> DojoTrainingService:
    """Install the 3.5 Dojo service on the current canonical FastAPI app.

    The unified backend is reloaded by parts of the regression suite and may also
    be imported by packaging discovery before the production entry point runs.
    Keeping the service on ``app.state`` and checking actual route paths makes
    this operation safe for both a fresh app and repeated imports.
    """

    base.legacy.APP_VERSION = APP_VERSION
    base.app.version = APP_VERSION

    service = getattr(base.app.state, "dojo_v35_service", None)
    if not isinstance(service, DojoTrainingService):
        service = DojoTrainingService()
        base.app.state.dojo_v35_service = service

    if not any(getattr(route, "path", "") == "/api/dojo/status" for route in base.app.routes):
        base.app.include_router(
            create_dojo_router(
                service,
                base.legacy.security,
                base.legacy.game_runtime,
            )
        )

    if not bool(getattr(base.app.state, "dojo_v35_lifespan_installed", False)):
        original_lifespan = base.app.router.lifespan_context

        @asynccontextmanager
        async def dojo_lifespan(fastapi_app):
            async with original_lifespan(fastapi_app):
                try:
                    yield
                finally:
                    if service.is_running:
                        await asyncio.to_thread(service.stop, timeout=8.0)
                    await asyncio.to_thread(base.legacy.game_runtime.release_all)

        base.app.router.lifespan_context = dojo_lifespan
        base.app.state.dojo_v35_lifespan_installed = True

    return service


dojo_service = ensure_dojo_integration()
app = base.app
runtime_status = base.runtime_status

__all__ = [
    "APP_VERSION",
    "app",
    "dojo_service",
    "ensure_dojo_integration",
    "runtime_status",
]
