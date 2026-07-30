from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingService


class DojoStartRequest(BaseModel):
    rounds: int = Field(default=10, ge=0, le=999)
    combat_seconds: float = Field(default=120.0, ge=5.0, le=900.0)
    post_combat_timeout: float = Field(default=240.0, ge=15.0, le=1800.0)
    dialog_delay: float = Field(default=5.0, ge=0.0, le=30.0)
    dialog_timeout: float = Field(default=6.0, ge=0.5, le=30.0)
    spawn_delay: float = Field(default=5.0, ge=0.0, le=30.0)
    trainer_search_timeout: float = Field(default=90.0, ge=5.0, le=600.0)
    recovery_hp_percent: float = Field(default=90.0, ge=90.0, le=100.0)
    recovery_chakra_percent: float = Field(default=50.0, ge=50.0, le=100.0)
    leader_threshold: float = Field(default=0.88, ge=0.50, le=0.999)
    round_startup_delay: float = Field(default=1.0, ge=0.0, le=30.0)
    chat_poll_seconds: float = Field(default=0.15, ge=0.10, le=2.0)
    h_enabled: bool = True

    def to_config(self) -> DojoTrainingConfig:
        return DojoTrainingConfig(
            rounds=self.rounds,
            combat_seconds=self.combat_seconds,
            post_combat_timeout=self.post_combat_timeout,
            dialog_delay=self.dialog_delay,
            dialog_timeout=self.dialog_timeout,
            spawn_delay=self.spawn_delay,
            trainer_search_timeout=self.trainer_search_timeout,
            recovery_hp_percent=self.recovery_hp_percent,
            recovery_chakra_percent=self.recovery_chakra_percent,
            leader_threshold=self.leader_threshold,
            round_startup_delay=self.round_startup_delay,
            chat_poll_seconds=self.chat_poll_seconds,
            disable_h=not self.h_enabled,
        ).normalized()


def dojo_status_payload(service: DojoTrainingService) -> dict[str, Any]:
    snapshot = service.snapshot()
    log_status = service.log_status() if hasattr(service, "log_status") else {}
    return {
        "available": service.runtime_available(),
        "running": snapshot.running,
        "phase": snapshot.phase.value,
        "current_round": snapshot.current_round,
        "completed_rounds": snapshot.completed_rounds,
        "last_line": snapshot.last_line,
        "last_error": snapshot.last_error,
        "return_code": snapshot.return_code,
        "position_state": str(getattr(service, "position_state", "LOST")),
        "position_x": float(getattr(service, "position_x", 0.0) or 0.0),
        "position_y": float(getattr(service, "position_y", 0.0) or 0.0),
        "position_confidence": float(getattr(service, "position_confidence", 0.0) or 0.0),
        "recent_actions": list(getattr(service, "recent_actions", ()) or ()),
        "last_log": log_status,
        "defaults": DojoTrainingConfig(rounds=10).to_public_dict(),
    }


def install_game_control_interlock(service: DojoTrainingService, game_runtime: Any) -> None:
    """Prevent manual GAME input from competing with the autonomous trainer."""

    if bool(getattr(game_runtime, "_kagelink_dojo_interlock", False)):
        return

    original_activate = game_runtime.activate_control
    original_apply = game_runtime.apply_keys
    original_click = game_runtime.click_game_center

    def require_manual_control_available() -> None:
        if service.is_running:
            raise RuntimeError("DOJO_TRAINING_ACTIVE")

    def activate_control():
        require_manual_control_available()
        return original_activate()

    def apply_keys(pressed):
        require_manual_control_available()
        return original_apply(pressed)

    def click_game_center():
        require_manual_control_available()
        return original_click()

    game_runtime.activate_control = activate_control
    game_runtime.apply_keys = apply_keys
    game_runtime.click_game_center = click_game_center
    game_runtime._kagelink_dojo_interlock = True


def create_dojo_router(
    service: DojoTrainingService,
    security: Any,
    game_runtime: Any,
) -> APIRouter:
    router = APIRouter(prefix="/api/dojo", tags=["dojo"])
    authorization = [Depends(security.require_authorization)]

    install_game_control_interlock(service, game_runtime)

    @router.get("/status", dependencies=authorization)
    async def get_dojo_status() -> dict[str, Any]:
        return dojo_status_payload(service)

    @router.get("/logs/latest", dependencies=authorization)
    async def get_latest_dojo_log() -> dict[str, Any]:
        return service.log_status() if hasattr(service, "log_status") else {"exists": False}

    @router.post("/start", dependencies=authorization)
    async def start_dojo(request: DojoStartRequest) -> dict[str, Any]:
        if service.is_running:
            raise HTTPException(status_code=409, detail="DOJO_ALREADY_RUNNING")
        if not service.runtime_available():
            raise HTTPException(status_code=503, detail="DOJO_RUNTIME_NOT_INSTALLED")

        await asyncio.to_thread(game_runtime.deactivate_control)
        await asyncio.to_thread(game_runtime.release_all)
        started = await asyncio.to_thread(service.start, request.to_config())
        if not started:
            snapshot = service.snapshot()
            raise HTTPException(
                status_code=409,
                detail=snapshot.last_error or "DOJO_START_FAILED",
            )
        return dojo_status_payload(service)

    @router.post("/stop", dependencies=authorization)
    async def stop_dojo() -> dict[str, Any]:
        if service.is_running:
            await asyncio.to_thread(service.stop, timeout=8.0)
        await asyncio.to_thread(game_runtime.release_all)
        return dojo_status_payload(service)

    return router


__all__ = [
    "DojoStartRequest",
    "create_dojo_router",
    "dojo_status_payload",
    "install_game_control_interlock",
]
