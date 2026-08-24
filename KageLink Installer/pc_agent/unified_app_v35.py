from __future__ import annotations

# Compatibility module for KageLink 3.5 packaging and older entry points.
# The canonical unified_app owns the Dojo service and the shared application.
# Hunting is installed here as a sibling autonomous mode so it can reuse the
# canonical KagePilotRound executable without modifying the legacy base Agent.
import unified_app as _canonical

from pc_agent.dojo_templates_api_v35 import install_dojo_template_routes
from pc_agent.game_numpad_diagonal import install_numpad_diagonal_controller
from pc_agent.hunting_api import install_hunting_routes

APP_VERSION = _canonical.APP_VERSION
app = _canonical.app
dojo_service = _canonical.dojo_service
runtime_status = _canonical.runtime_status

# Shinobi Story does not consume two arrow-key holds as true diagonal movement.
# Keep the Flutter joystick contract unchanged (two-axis cardinal set) and adapt
# it at the Windows input boundary to native numpad diagonals: 1/3/7/9.
install_numpad_diagonal_controller(_canonical.legacy.game_runtime)

install_dojo_template_routes(app, _canonical.legacy.security, dojo_service)
hunting_service = install_hunting_routes(
    app,
    _canonical.legacy.security,
    _canonical.legacy.game_runtime,
    dojo_service,
)

__all__ = ["APP_VERSION", "app", "dojo_service", "hunting_service", "runtime_status"]
