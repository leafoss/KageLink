from __future__ import annotations

# Compatibility module for KageLink 3.5 packaging and older entry points.
# The canonical unified_app owns the Dojo service, authenticated start/stop routes,
# GAME interlock and shutdown lifecycle. This wrapper adds external user-owned
# Trainer-template management without duplicating the combat runtime.
import unified_app as _canonical

from pc_agent.dojo_templates_api_v35 import install_dojo_template_routes

APP_VERSION = _canonical.APP_VERSION
app = _canonical.app
dojo_service = _canonical.dojo_service
runtime_status = _canonical.runtime_status

install_dojo_template_routes(app, _canonical.legacy.security, dojo_service)

__all__ = ["APP_VERSION", "app", "dojo_service", "runtime_status"]
