from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingService


DebugLevel = Literal["basic", "detections", "processed"]


class DojoDebugRequest(BaseModel):
    enabled: bool = False
    level: DebugLevel = "detections"
    opacity: float = Field(default=0.82, ge=0.25, le=1.0)
    fps: float = Field(default=15.0, ge=5.0, le=30.0)
    meditation_enter_delay_seconds: float = Field(default=5.5, ge=5.0, le=30.0)
    meditation_exit_delay_seconds: float = Field(default=5.5, ge=5.0, le=30.0)
    meditation_timeout_seconds: float = Field(default=120.0, ge=15.0, le=1800.0)

    def apply(self, service: DojoTrainingService):
        return service.configure_debug(
            enabled=self.enabled,
            level=self.level,
            opacity=self.opacity,
            fps=self.fps,
            meditation_enter_delay_seconds=self.meditation_enter_delay_seconds,
            meditation_exit_delay_seconds=self.meditation_exit_delay_seconds,
            meditation_timeout_seconds=self.meditation_timeout_seconds,
        )


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
    debug_visual: bool = False
    debug_level: DebugLevel = "detections"
    debug_overlay_opacity: float = Field(default=0.82, ge=0.25, le=1.0)
    debug_overlay_fps: float = Field(default=15.0, ge=5.0, le=30.0)
    meditation_enter_delay_seconds: float = Field(default=5.5, ge=5.0, le=30.0)
    meditation_exit_delay_seconds: float = Field(default=5.5, ge=5.0, le=30.0)
    meditation_timeout_seconds: float = Field(default=120.0, ge=15.0, le=1800.0)

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

    def apply_debug(self, service: DojoTrainingService):
        return service.configure_debug(
            enabled=self.debug_visual,
            level=self.debug_level,
            opacity=self.debug_overlay_opacity,
            fps=self.debug_overlay_fps,
            meditation_enter_delay_seconds=self.meditation_enter_delay_seconds,
            meditation_exit_delay_seconds=self.meditation_exit_delay_seconds,
            meditation_timeout_seconds=self.meditation_timeout_seconds,
        )


def dojo_status_payload(service: DojoTrainingService) -> dict[str, Any]:
    snapshot = service.snapshot()
    log_status = service.log_status() if hasattr(service, "log_status") else {}
    if hasattr(service, "current_debug_settings"):
        debug = service.current_debug_settings()
    else:
        debug = getattr(service, "debug_settings", None)
    debug_payload = debug.to_dict() if debug is not None else {}
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
        "meditation_state": str(getattr(service, "meditation_state", "IDLE")),
        "meditation_elapsed": float(getattr(service, "meditation_elapsed", 0.0) or 0.0),
        "meditation_hp": getattr(service, "meditation_hp", None),
        "meditation_chakra": getattr(service, "meditation_chakra", None),
        "v_cooldown_remaining": float(
            getattr(service, "v_cooldown_remaining", 0.0) or 0.0
        ),
        "combat_start_blocked": bool(
            getattr(service, "combat_start_blocked", False)
        ),
        "debug": debug_payload,
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

    @router.post("/debug", dependencies=authorization)
    async def configure_dojo_debug(request: DojoDebugRequest) -> dict[str, Any]:
        await asyncio.to_thread(request.apply, service)
        return dojo_status_payload(service)

    @router.post("/start", dependencies=authorization)
    async def start_dojo(request: DojoStartRequest) -> dict[str, Any]:
        if service.is_running:
            raise HTTPException(status_code=409, detail="DOJO_ALREADY_RUNNING")
        if not service.runtime_available():
            raise HTTPException(status_code=503, detail="DOJO_RUNTIME_NOT_INSTALLED")

        await asyncio.to_thread(request.apply_debug, service)
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
    "DojoDebugRequest",
    "DojoStartRequest",
    "create_dojo_router",
    "dojo_status_payload",
    "install_game_control_interlock",
]
