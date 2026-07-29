from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import sys

import unified_app as base
from pc_agent.dojo_api import create_dojo_router
from pc_agent.kage_pilot import DojoTrainingService


APP_VERSION = "3.5.0"
app = base.app
runtime_status = base.runtime_status
dojo_service: DojoTrainingService


def ensure_dojo_integration() -> DojoTrainingService:
    """Install the 3.5 Dojo service on the active canonical FastAPI app.

    Packaging discovery and some regression fixtures may replace ``unified_app``
    in ``sys.modules``. Rebinding here keeps the product wrapper attached to the
    backend that will actually be served, while app-state guards prevent route
    and lifespan duplication.
    """

    global app, base, dojo_service, runtime_status

    active_base = sys.modules.get("unified_app")
    if active_base is not None and active_base is not base:
        base = active_base

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

    app = base.app
    runtime_status = base.runtime_status
    dojo_service = service
    return service


dojo_service = ensure_dojo_integration()

__all__ = [
    "APP_VERSION",
    "app",
    "dojo_service",
    "ensure_dojo_integration",
    "runtime_status",
]
