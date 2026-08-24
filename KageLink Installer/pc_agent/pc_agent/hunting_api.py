from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from pc_agent.kage_pilot.hunting_service import HuntingConfig, HuntingService


class HuntingStartRequest(BaseModel):
    walk_seconds: float = Field(default=1.40, ge=0.50, le=10.0)
    combat_timeout_seconds: float = Field(default=300.0, ge=30.0, le=900.0)
    recovery_timeout_seconds: float = Field(default=600.0, ge=30.0, le=1800.0)
    recovery_hp_percent: float = Field(default=90.0, ge=90.0, le=100.0)
    recovery_stamina_percent: float = Field(default=90.0, ge=90.0, le=100.0)

    def to_config(self) -> HuntingConfig:
        return HuntingConfig(
            walk_seconds=self.walk_seconds,
            combat_timeout_seconds=self.combat_timeout_seconds,
            recovery_timeout_seconds=self.recovery_timeout_seconds,
            recovery_hp_percent=self.recovery_hp_percent,
            recovery_stamina_percent=self.recovery_stamina_percent,
        ).normalized()


def hunting_status_payload(service: HuntingService) -> dict[str, Any]:
    snapshot = service.snapshot()
    return {
        "available": service.runtime_available(),
        "running": snapshot.running,
        "phase": snapshot.phase.value,
        "kills": snapshot.kills,
        "direction": snapshot.direction,
        "last_enemy": snapshot.last_enemy,
        "health": snapshot.health,
        "stamina": snapshot.stamina,
        "stamina_calibrated": snapshot.stamina_calibrated,
        "last_line": snapshot.last_line,
        "last_error": snapshot.last_error,
        "return_code": snapshot.return_code,
        "recovery_contract": {
            "health_percent": 90.0,
            "stamina_percent": 90.0,
            "chakra_is_not_stamina": True,
            "fail_closed_without_stamina_calibration": True,
        },
    }


def _install_manual_game_interlock(service: HuntingService, game_runtime: Any) -> None:
    if bool(getattr(game_runtime, "_kagelink_hunting_interlock", False)):
        return
    original_activate = game_runtime.activate_control
    original_apply = game_runtime.apply_keys
    original_click = game_runtime.click_game_center

    def require_available() -> None:
        if service.is_running:
            raise RuntimeError("HUNTING_ACTIVE")

    def activate_control():
        require_available()
        return original_activate()

    def apply_keys(pressed):
        require_available()
        return original_apply(pressed)

    def click_game_center():
        require_available()
        return original_click()

    game_runtime.activate_control = activate_control
    game_runtime.apply_keys = apply_keys
    game_runtime.click_game_center = click_game_center
    game_runtime._kagelink_hunting_interlock = True


def install_hunting_routes(app: Any, security: Any, game_runtime: Any, dojo_service: Any) -> HuntingService:
    existing = getattr(app.state, "hunting_service", None)
    if isinstance(existing, HuntingService):
        return existing

    service = HuntingService()
    app.state.hunting_service = service
    _install_manual_game_interlock(service, game_runtime)

    if not bool(getattr(app.state, "hunting_dojo_middleware", False)):
        @app.middleware("http")
        async def hunting_dojo_interlock(request: Request, call_next):
            if (
                request.method.upper() == "POST"
                and request.url.path == "/api/dojo/start"
                and service.is_running
            ):
                return JSONResponse(status_code=409, content={"detail": "HUNTING_ACTIVE"})
            return await call_next(request)
        app.state.hunting_dojo_middleware = True

    authorization = [Depends(security.require_authorization)]

    @app.get("/api/hunting/status", dependencies=authorization)
    async def get_hunting_status() -> dict[str, Any]:
        return hunting_status_payload(service)

    @app.post("/api/hunting/start", dependencies=authorization)
    async def start_hunting(request: HuntingStartRequest) -> dict[str, Any]:
        if service.is_running:
            raise HTTPException(status_code=409, detail="HUNTING_ALREADY_RUNNING")
        if getattr(dojo_service, "is_running", False):
            raise HTTPException(status_code=409, detail="DOJO_TRAINING_ACTIVE")
        if not service.runtime_available():
            raise HTTPException(status_code=503, detail="HUNTING_RUNTIME_NOT_INSTALLED")
        await asyncio.to_thread(game_runtime.deactivate_control)
        await asyncio.to_thread(game_runtime.release_all)
        started = await asyncio.to_thread(service.start, request.to_config())
        if not started:
            snapshot = service.snapshot()
            raise HTTPException(status_code=409, detail=snapshot.last_error or "HUNTING_START_FAILED")
        return hunting_status_payload(service)

    @app.post("/api/hunting/stop", dependencies=authorization)
    async def stop_hunting() -> dict[str, Any]:
        if service.is_running:
            await asyncio.to_thread(service.stop, timeout=8.0)
        await asyncio.to_thread(game_runtime.release_all)
        return hunting_status_payload(service)

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def hunting_lifespan(fastapi_app):
        async with previous_lifespan(fastapi_app):
            try:
                yield
            finally:
                if service.is_running:
                    await asyncio.to_thread(service.stop, timeout=8.0)
                await asyncio.to_thread(game_runtime.release_all)

    app.router.lifespan_context = hunting_lifespan
    return service


__all__ = [
    "HuntingStartRequest",
    "hunting_status_payload",
    "install_hunting_routes",
]
