from __future__ import annotations

# Compatibility module for KageLink 3.5 packaging and older entry points.
# The canonical unified_app owns the Dojo service and the shared application.
# Hunting is installed here as a sibling autonomous mode so it can reuse the
# canonical KagePilotRound executable without modifying the legacy base Agent.
import unified_app as _canonical

from pc_agent.dojo_templates_api_v35 import install_dojo_template_routes
from pc_agent.hunting_api import install_hunting_routes

APP_VERSION = _canonical.APP_VERSION
app = _canonical.app
dojo_service = _canonical.dojo_service
runtime_status = _canonical.runtime_status

install_dojo_template_routes(app, _canonical.legacy.security, dojo_service)
hunting_service = install_hunting_routes(
    app,
    _canonical.legacy.security,
    _canonical.legacy.game_runtime,
    dojo_service,
)

__all__ = ["APP_VERSION", "app", "dojo_service", "hunting_service", "runtime_status"]
