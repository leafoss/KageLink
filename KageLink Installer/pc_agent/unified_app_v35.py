from __future__ import annotations

import asyncio

from fastapi import Depends

# Compatibility module retained for installed 3.5.x entry points. The canonical
# runtime owns the Dojo service and start/stop routes; this wrapper installs the
# user-template, protected debug and 3.5.1 reliability routes without duplicating
# combat logic.
import unified_app as _canonical

from pc_agent.dojo_api import DojoDebugRequest, DojoStartRequest
from pc_agent.dojo_templates_api_v35 import install_dojo_template_routes


APP_VERSION = "3.5.1"
_canonical.APP_VERSION = APP_VERSION
_canonical.legacy.APP_VERSION = APP_VERSION
_canonical.legacy.app.version = APP_VERSION

app = _canonical.app
dojo_service = _canonical.dojo_service
runtime_status = _canonical.runtime_status


if not any(getattr(route, "path", "") == "/api/dojo/debug" for route in app.routes):

    @app.post(
        "/api/dojo/debug",
        dependencies=[Depends(_canonical.legacy.security.require_authorization)],
    )
    async def configure_dojo_debug(request: DojoDebugRequest):
        await asyncio.to_thread(request.apply, dojo_service)
        return _canonical.dojo_status_payload(dojo_service)


# The canonical 3.5.0 route already owns GAME interlock and process startup.
# Bridge only the new 3.5.1 settings into that route before it starts. The
# original route still receives the same request and remains process authority.
for route in app.routes:
    if getattr(route, "path", "") != "/api/dojo/start":
        continue
    if "POST" not in set(getattr(route, "methods", set())):
        continue
    original_start = getattr(route, "endpoint", None)
    if original_start is None or bool(getattr(original_start, "_kagelink_debug_bridge", False)):
        break

    async def start_dojo_with_debug(request: DojoStartRequest, _original=original_start):
        config = request.to_config()
        await asyncio.to_thread(request.apply_debug, dojo_service)
        dojo_service.recovery_hp_percent = config.recovery_hp_percent
        dojo_service.recovery_chakra_percent = config.recovery_chakra_percent
        return await _original(request)

    start_dojo_with_debug._kagelink_debug_bridge = True
    route.endpoint = start_dojo_with_debug
    route.dependant.call = start_dojo_with_debug
    break


install_dojo_template_routes(app, _canonical.legacy.security, dojo_service)


__all__ = ["APP_VERSION", "app", "dojo_service", "runtime_status"]
