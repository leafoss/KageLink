from __future__ import annotations

import base64
import binascii
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from pc_agent.kage_pilot.dojo_templates_v35 import (
    DEFAULT_DOJO_TEMPLATE_STORE,
    DojoTemplateStore,
    normalize_template_mode,
)
from pc_agent.kage_pilot.dojo_training import DojoTrainingPhase


class DojoTemplateUploadRequest(BaseModel):
    filename: str = Field(default="template.png", min_length=1, max_length=260)
    image_base64: str = Field(min_length=1, max_length=8_000_000)


def _decode_upload(request: DojoTemplateUploadRequest) -> bytes:
    try:
        return base64.b64decode(request.image_base64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise HTTPException(status_code=400, detail="DOJO_TEMPLATE_BASE64_INVALID") from error


def _route_exists(app: FastAPI, path: str, method: str) -> bool:
    wanted = method.upper()
    return any(
        str(getattr(route, "path", "")) == path
        and wanted in set(getattr(route, "methods", set()) or set())
        for route in app.routes
    )


def install_template_start_guard(service: Any, store: DojoTemplateStore) -> None:
    """Fail closed before launching helpers when no user template is configured."""

    if bool(getattr(service, "_kagelink_template_guard", False)):
        return
    original_start = service.start

    def guarded_start(config):
        if not store.has_any():
            setter = getattr(service, "_set_phase", None)
            if callable(setter):
                setter(
                    DojoTrainingPhase.ERROR,
                    running=False,
                    last_error="DOJO_TRAINER_TEMPLATE_REQUIRED",
                )
            return False
        return original_start(config)

    service.start = guarded_start
    service._kagelink_template_guard = True


def install_dojo_template_routes(
    app: FastAPI,
    security: Any,
    dojo_service: Any,
    *,
    store: DojoTemplateStore = DEFAULT_DOJO_TEMPLATE_STORE,
) -> None:
    authorization = [Depends(security.require_authorization)]
    install_template_start_guard(dojo_service, store)

    def require_template_mutation_available() -> None:
        if bool(getattr(dojo_service, "is_running", False)):
            raise HTTPException(status_code=409, detail="DOJO_TRAINING_ACTIVE")

    if not _route_exists(app, "/api/dojo/templates", "GET"):

        @app.get("/api/dojo/templates", dependencies=authorization)
        async def get_dojo_templates() -> dict:
            return store.public_status()

    if not _route_exists(app, "/api/dojo/templates/{mode}/image", "GET"):

        @app.get("/api/dojo/templates/{mode}/image", dependencies=authorization)
        async def get_dojo_template_image(mode: str) -> dict:
            try:
                value = normalize_template_mode(mode)
                record = store.record(value)
                if not record.configured:
                    raise FileNotFoundError
                return {
                    "mode": value,
                    "sha256": record.sha256,
                    "image_base64": store.image_base64(value),
                }
            except ValueError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            except FileNotFoundError as error:
                raise HTTPException(status_code=404, detail="DOJO_TEMPLATE_NOT_CONFIGURED") from error

    if not _route_exists(app, "/api/dojo/templates/{mode}", "POST"):

        @app.post("/api/dojo/templates/{mode}", dependencies=authorization)
        async def upload_dojo_template(mode: str, request: DojoTemplateUploadRequest) -> dict:
            require_template_mutation_available()
            try:
                value = normalize_template_mode(mode)
                record = store.save(
                    value,
                    _decode_upload(request),
                    original_filename=request.filename,
                )
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            payload = store.public_status()
            payload["saved"] = record.to_public_dict()
            return payload

    if not _route_exists(app, "/api/dojo/templates/{mode}", "DELETE"):

        @app.delete("/api/dojo/templates/{mode}", dependencies=authorization)
        async def delete_dojo_template(mode: str) -> dict:
            require_template_mutation_available()
            try:
                value = normalize_template_mode(mode)
                store.remove(value)
            except ValueError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            return store.public_status()


__all__ = [
    "DojoTemplateUploadRequest",
    "install_dojo_template_routes",
    "install_template_start_guard",
]
